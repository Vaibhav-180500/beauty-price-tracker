# ingestion/runner.py
# D05: minimal ingestion runner (requests + bs4)
# - reads sku_registry.csv
# - uses selectors.yml per retailer
# - rate-limits per retailer
# - parses price/list/discount/in_stock
# - writes to data/observations/<date>/obs_<ts>.csv and (optional) dbt/seeds/obs_latest.csv

import re, csv, json, time, uuid, argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Tuple, Optional, List

import requests
import yaml
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
SEL  = ROOT / "ingestion" / "selectors.yml"
SEED = ROOT / "dbt" / "seeds" / "sku_registry.csv"
OUTD = ROOT / "data" / "observations"
DBG  = ROOT / "debug"
OUTD.mkdir(parents=True, exist_ok=True)
DBG.mkdir(parents=True,  exist_ok=True)

# ---------- helpers ----------

def load_yaml(p: Path) -> Dict[str, Any]:
    with p.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def first_n_rows_by_retailer(seed_csv: Path, retailers: List[str], limit_per: int) -> Dict[str, List[Dict[str,str]]]:
    buckets = {r: [] for r in retailers}
    with seed_csv.open(encoding="utf-8", errors="replace", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            ret = (row.get("retailer") or "").strip()
            if ret in buckets and len(buckets[ret]) < limit_per:
                buckets[ret].append(row)
    return buckets

def fetch(url: str, ua: str, timeout: int = 30) -> Tuple[int, str]:
    headers = {
        "User-Agent": ua or "Mozilla/5.0",
        "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Connection": "close",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        return resp.status_code, resp.text
    except Exception as e:
        return 0, f"__ERROR__{e}"

_price_pat   = re.compile(r"(\d+[\.,]\d{2})")
_disc_pat    = re.compile(r"(-?\d{1,3})\s*%")
_instock_any = re.compile(r"(en stock|in stock|disponible|usually ships|available)", re.I)
_oos_any     = re.compile(r"(rupture|indisponible|out of stock|unavailable|sold out|notify me)", re.I)

def norm_price_text(txt: Optional[str]) -> Optional[float]:
    if not txt: return None
    m = _price_pat.search(txt)
    return float(m.group(1).replace(",", ".")) if m else None

def norm_discount_text(txt: Optional[str]) -> Optional[float]:
    if not txt: return None
    m = _disc_pat.search(txt)
    return abs(int(m.group(1))) / 100.0 if m else None

def jsonld_stock(html: str) -> Optional[bool]:
    """Try JSON-LD first (fast & reliable when present)."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        txt = tag.get_text(" ", strip=True)
        if not txt:
            continue
        try:
            data = json.loads(txt)
        except Exception:
            if "InStock" in txt: return True
            if "OutOfStock" in txt: return False
            continue

        stack = [data]
        while stack:
            cur = stack.pop()
            if isinstance(cur, dict):
                av = cur.get("availability") or cur.get("itemAvailability")
                if isinstance(av, str):
                    if "InStock" in av: return True
                    if "OutOfStock" in av: return False
                off = cur.get("offers")
                if isinstance(off, dict): stack.append(off)
                elif isinstance(off, list): stack.extend(off)
                for v in cur.values():
                    if isinstance(v, (dict, list)):
                        stack.append(v)
            elif isinstance(cur, list):
                stack.extend(cur)
    return None

def detect_stock(soup: BeautifulSoup, html: str, cfg: Dict[str, Any]) -> Optional[bool]:
    # 1) Button/selector heuristic
    sel = cfg.get("availability_selector")
    if sel:
        el = soup.select_one(sel)
        if el:
            disabled = (el.get("disabled") is not None) or (str(el.get("aria-disabled","")).lower() in ("1","true","disabled"))
            if disabled:
                return False
            btn = el if el.name == "button" else el.find("button")
            if btn:
                if (btn.get("disabled") is not None) or (str(btn.get("aria-disabled","")).lower() in ("1","true","disabled")):
                    return False
                return True
            return True

    # 2) JSON-LD
    jl = jsonld_stock(html)
    if jl is True:  return True
    if jl is False: return False

    # 3) Full-page text
    text = soup.get_text(" ", strip=True)
    if _instock_any.search(text): return True
    if _oos_any.search(text):     return False
    # Config-specific text (if provided)
    in_pat  = cfg.get("in_stock_text")
    oos_pat = cfg.get("oos_text")
    if in_pat  and re.search(in_pat, text, flags=re.I): return True
    if oos_pat and re.search(oos_pat, text, flags=re.I): return False
    return None

def parse_html(html: str, cfg: Dict[str, Any]) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[bool]]:
    soup = BeautifulSoup(html, "html.parser")
    price = listp = disc = None

    if cfg.get("price_selector"):
        el = soup.select_one(cfg["price_selector"])
        if el: price = norm_price_text(el.get_text(" ", strip=True))

    if cfg.get("sale_price_selector"):
        el = soup.select_one(cfg["sale_price_selector"])
        if el: listp = norm_price_text(el.get_text(" ", strip=True))

    if cfg.get("discount_selector"):
        el = soup.select_one(cfg["discount_selector"])
        if el: disc = norm_discount_text(el.get_text(" ", strip=True))

    instock = detect_stock(soup, html, cfg)

    # derive discount if list price present
    if disc is None and listp and price and listp > price:
        disc = round((listp - price) / listp, 2)

    return price, listp, disc, instock

# ---------- runner ----------

def run(retailers: List[str], limit_per: int, copy_seed: bool):
    selectors = load_yaml(SEL)
    now = datetime.now(timezone.utc)
    run_id = uuid.uuid4().hex[:12]
    day_dir = OUTD / now.strftime("%Y-%m-%d")
    day_dir.mkdir(parents=True, exist_ok=True)
    out_path = day_dir / f"obs_{now.strftime('%Y%m%dT%H%M%SZ')}_{run_id}.csv"

    # prepare CSV
    header = [
        "run_id", "observed_at_utc",
        "sku_id", "retailer", "brand", "product_name", "category", "subcategory",
        "size_value", "size_unit",
        "price", "list_price", "discount_pct", "in_stock",
        "currency", "http_status", "product_url", "parse_error"
    ]
    out_f = out_path.open("w", encoding="utf-8", newline="")
    writer = csv.DictWriter(out_f, fieldnames=header)
    writer.writeheader()

    # split by retailer and rate-limit per config
    buckets = first_n_rows_by_retailer(SEED, retailers, limit_per)

    for retailer in retailers:
        cfg = selectors.get(retailer) or {}
        rl_s = int(cfg.get("rate_limit_seconds", 20))
        ua   = cfg.get("user_agent") or "Mozilla/5.0"
        timeout_s = int(cfg.get("timeout_seconds", 30))

        last_ts = 0.0
        rows = buckets.get(retailer, [])
        print(f"\n=== {retailer} — {len(rows)} items (rate≈{rl_s}s) ===")

        for i, row in enumerate(rows, 1):
            # rate-limit
            now_s = time.time()
            to_wait = rl_s - (now_s - last_ts)
            if to_wait > 0:
                time.sleep(to_wait)
            last_ts = time.time()

            url = (row.get("product_url") or "").strip()
            status, html = fetch(url, ua, timeout=timeout_s)

            # always save html (useful for debugging)
            dbg_name = f"{retailer}_{int(time.time())}_{i}.html"
            (DBG / dbg_name).write_text(html, encoding="utf-8", errors="ignore")

            price = listp = disc = None
            instock = None
            err = ""
            if status == 200 and not html.startswith("__ERROR__"):
                try:
                    price, listp, disc, instock = parse_html(html, cfg)
                except Exception as e:
                    err = f"parse_error:{type(e).__name__}"
            else:
                err = f"http_error:{status}" if status else html

            writer.writerow({
                "run_id": run_id,
                "observed_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "sku_id": row.get("sku_id"),
                "retailer": retailer,
                "brand": row.get("brand"),
                "product_name": row.get("product_name"),
                "category": row.get("category"),
                "subcategory": row.get("subcategory"),
                "size_value": row.get("size_value"),
                "size_unit": row.get("size_unit"),
                "price": price,
                "list_price": listp,
                "discount_pct": disc,
                "in_stock": instock,
                "currency": row.get("currency") or cfg.get("currency_hint") or "EUR",
                "http_status": status,
                "product_url": url,
                "parse_error": err
            })

            print(f"- {retailer} [{i}/{len(rows)}] status={status} price={price} list={listp} disc={disc} in_stock={instock} -> {dbg_name}")

    out_f.close()
    print(f"\n✅ Wrote {out_path}")

    if copy_seed:
        seed_out = ROOT / "dbt" / "seeds" / "obs_latest.csv"
        seed_out.write_text(out_path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"✅ Copied to {seed_out} (dbt seed ready)")

def main():
    ap = argparse.ArgumentParser(description="D05 ingestion runner")
    ap.add_argument("--retailers", nargs="+", default=["amazon_fr", "sephora_fr"], help="subset to run")
    ap.add_argument("--limit-per", type=int, default=10, help="max SKUs per retailer")
    ap.add_argument("--seed-copy", action="store_true", help="copy output to dbt/seeds/obs_latest.csv")
    args = ap.parse_args()
    run(args.retailers, args.limit_per, args.seed_copy)

if __name__ == "__main__":
    main()
