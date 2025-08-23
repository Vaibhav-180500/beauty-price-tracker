# tools/test_selectors_hardened_v2.py
import re, csv, json, time, argparse, random
from pathlib import Path
from bs4 import BeautifulSoup
import yaml, requests

ROOT = Path(__file__).resolve().parents[1]
SEL  = ROOT / "ingestion" / "selectors.yml"
SEED = ROOT / "dbt" / "seeds" / "sku_registry.csv"
DBG  = ROOT / "debug"
DBG.mkdir(exist_ok=True, parents=True)

# --- Amazon block-page heuristics (tiny HTML + classic strings) ---
AMZ_BLOCK_NEEDLES = [
    "Robot Check", "/errors/validateCaptcha", "api-services-support@amazon",
    "To discuss automated access to Amazon data"
]
AMZ_MIN_HTML_LEN = 30000  # typical real PDP is >100kB, block pages are ~5–12kB


# -------------------- helpers --------------------
def load_yaml(p: Path):
    with p.open(encoding="utf-8") as f:
        return yaml.safe_load(f)

def first_n_urls(retailer: str, n: int):
    rows = []
    with SEED.open(encoding="utf-8", errors="replace") as f:
        r = csv.DictReader(f)
        for row in r:
            if row.get("retailer", "").strip() == retailer:
                rows.append(row["product_url"])
    return rows[:n]

def amazon_headers(ua: str) -> dict:
    return {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "DNT": "1",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
    }

def is_blocked_amazon(status: int, html: str) -> bool:
    if status != 200:
        return True
    if len(html) < AMZ_MIN_HTML_LEN:
        return True
    h = html[:200000]  # cap scan
    return any(s in h for s in AMZ_BLOCK_NEEDLES)

# single persistent session (connection reuse)
_SESSION = requests.Session()

def fetch(url: str, ua: str, retailer: str, timeout: int = 30):
    """
    Fetch a URL with realistic headers and one gentle retry for Amazon if blocked.
    """
    if "amazon" in retailer:
        headers = amazon_headers(ua)
    else:
        headers = {"User-Agent": ua, "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8"}

    resp = _SESSION.get(url, headers=headers, timeout=timeout)
    status, html = resp.status_code, resp.text

    # one retry for Amazon if we hit a block page
    if "amazon" in retailer and is_blocked_amazon(status, html):
        # polite wait before retry (gives CloudFront a chance to cool down)
        time.sleep(35 + random.uniform(0, 5))
        resp = _SESSION.get(url, headers=headers, timeout=timeout)
        status, html = resp.status_code, resp.text
    return status, html


def norm_price_text(txt: str):
    m = re.search(r"(\d+[\.,]\d{2})", txt or "")
    if not m:
        return None
    return float(m.group(1).replace(",", "."))

def norm_discount_text(txt: str):
    m = re.search(r"(-?\d{1,3})\s*%", txt or "")
    if not m:
        return None
    return abs(int(m.group(1))) / 100.0


def jsonld_stock(html: str):
    """Parse all JSON-LD blocks; return True/False if availability found, else None."""
    try:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
            txt = tag.get_text(" ", strip=True)
            if not txt:
                continue
            try:
                data = json.loads(txt)
            except Exception:
                if "InStock" in txt:
                    return True
                if "OutOfStock" in txt:
                    return False
                continue
            stack = [data]
            while stack:
                cur = stack.pop()
                if isinstance(cur, dict):
                    av = cur.get("availability") or cur.get("itemAvailability")
                    if isinstance(av, str):
                        if "InStock" in av:
                            return True
                        if "OutOfStock" in av:
                            return False
                    off = cur.get("offers")
                    if isinstance(off, dict):
                        stack.append(off)
                    elif isinstance(off, list):
                        stack.extend(off)
                    for v in cur.values():
                        if isinstance(v, (dict, list)):
                            stack.append(v)
                elif isinstance(cur, list):
                    stack.extend(cur)
        return None
    except Exception:
        return None


def detect_stock(soup: BeautifulSoup, html: str, cfg: dict):
    """
    Decide in_stock using three checks (in order):
      1) availability_selector: disabled => False, enabled => True (if present)
      2) JSON-LD availability
      3) Text scan using in_stock_text / oos_text
    """
    sel = cfg.get("availability_selector")
    if sel:
        el = soup.select_one(sel)
        if el:
            disabled = (el.get("disabled") is not None) or (str(el.get("aria-disabled", "")).lower() in ("1", "true", "disabled"))
            if disabled:
                return False
            child_btn = el if el.name == "button" else el.find("button")
            if child_btn:
                if (child_btn.get("disabled") is not None) or (str(child_btn.get("aria-disabled", "")).lower() in ("1", "true", "disabled")):
                    return False
                return True
            return True

    jl = jsonld_stock(html)
    if jl is True:
        return True
    if jl is False:
        return False

    text = soup.get_text(" ", strip=True)
    in_pat = cfg.get("in_stock_text", "")
    oos_pat = cfg.get("oos_text", "")
    if in_pat and re.search(in_pat, text, flags=re.I):
        return True
    if oos_pat and re.search(oos_pat, text, flags=re.I):
        return False
    return None


def parse_one(html: str, cfg: dict, retailer: str):
    soup = BeautifulSoup(html, "html.parser")
    price = list_price = disc = None

    # 1) use selectors from YAML
    if cfg.get("price_selector"):
        el = soup.select_one(cfg["price_selector"])
        if el:
            price = norm_price_text(el.get_text(" ", strip=True))

    if cfg.get("sale_price_selector"):
        el = soup.select_one(cfg["sale_price_selector"])
        if el:
            list_price = norm_price_text(el.get_text(" ", strip=True))

    if cfg.get("discount_selector"):
        el = soup.select_one(cfg["discount_selector"])
        if el:
            disc = norm_discount_text(el.get_text(" ", strip=True))

    # 2) AMAZON fallbacks (robust across multiple PDP templates)
    if "amazon" in retailer:
        # price fallback
        if price is None:
            for css in [
                "#corePrice_feature_div .a-price .a-offscreen",
                ".a-section .a-price .a-offscreen",
                ".a-price .a-offscreen",
            ]:
                el = soup.select_one(css)
                if el:
                    price = norm_price_text(el.get_text(" ", strip=True))
                    if price:
                        break
        # list/strike fallback
        if list_price is None:
            el = soup.select_one(".a-text-price .a-offscreen")
            if el:
                list_price = norm_price_text(el.get_text(" ", strip=True))
        # discount fallback (badge like “-22%”)
        if disc is None:
            for css in [
                "#apex_desktop .savingsPercentage",
                "#corePrice_feature_div .savingsPercentage",
                ".a-section .savingsPercentage",
            ]:
                el = soup.select_one(css)
                if el:
                    disc = norm_discount_text(el.get_text(" ", strip=True))
                    if disc is not None:
                        break

    # stock
    in_stock = detect_stock(soup, html, cfg)

    # derive discount if not given but list<->price available
    if disc is None and list_price and price and list_price > price:
        disc = round((list_price - price) / list_price, 2)

    return price, list_price, disc, in_stock


def run_for(retailer: str, limit: int, rate: int):
    cfg = load_yaml(SEL)[retailer]
    ua = cfg.get("user_agent") or "Mozilla/5.0"
    delay = int(cfg.get("rate_limit_seconds", rate))
    urls = first_n_urls(retailer, limit)
    print(f"=== {retailer} (rate≈{delay}s) ===")
    for i, u in enumerate(urls, 1):
        # polite jitter BEFORE each fetch
        time.sleep(max(0.0, delay + random.uniform(-2.0, 2.0)))

        status, html = fetch(u, ua, retailer)
        print(f"- {u}")
        print(f"  status={status} len={len(html)}")

        price, listp, disc, instock = parse_one(html, cfg, retailer)
        print(f"  price={price} list={listp} disc={disc} in_stock={instock}")

        # always save HTML so we can inspect when something fails
        ts = int(time.time())
        out = DBG / f"{retailer}_{ts}_{i}.html"
        out.write_text(html, encoding="utf-8")
        print(f"  [saved {out.name}]")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--retailers", nargs="+", default=["amazon_fr", "sephora_fr"])
    ap.add_argument("--limit", type=int, default=2)
    ap.add_argument("--rate", type=int, default=26)  # a bit slower by default
    args = ap.parse_args()

    for r in args.retailers:
        run_for(r, args.limit, args.rate)

if __name__ == "__main__":
    main()
