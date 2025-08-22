import re, csv, json, time, argparse
from pathlib import Path
from bs4 import BeautifulSoup
import yaml, requests

ROOT = Path(__file__).resolve().parents[1]
SEL = ROOT / "ingestion" / "selectors.yml"
SEED = ROOT / "dbt" / "seeds" / "sku_registry.csv"
DBG  = ROOT / "debug"
DBG.mkdir(exist_ok=True, parents=True)

def load_yaml(p: Path):
    with p.open(encoding="utf-8") as f:
        return yaml.safe_load(f)

def first_n_urls(retailer: str, n: int):
    rows = []
    with SEED.open(encoding="utf-8", errors="replace") as f:
        r = csv.DictReader(f)
        for row in r:
            if row.get("retailer","").strip() == retailer:
                rows.append(row["product_url"])
    return rows[:n]

def fetch(url: str, ua: str, timeout: int = 30):
    h = {"User-Agent": ua, "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8"}
    resp = requests.get(url, headers=h, timeout=timeout)
    return resp.status_code, resp.text

def norm_price_text(txt: str):
    m = re.search(r"(\d+[\.,]\d{2})", txt or "")
    if not m: return None
    return float(m.group(1).replace(",", "."))
def norm_discount_text(txt: str):
    m = re.search(r"(-?\d{1,3})\s*%", txt or "")
    if not m: return None
    return abs(int(m.group(1))) / 100.0

def jsonld_stock(html: str):
    """Parse all JSON-LD blocks; return True/False if availability found, else None."""
    try:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup.find_all("script", attrs={"type":"application/ld+json"}):
            txt = tag.get_text(" ", strip=True)
            if not txt: 
                continue
            # JSON-LD can be a single object or a list; also often minified
            try:
                data = json.loads(txt)
            except Exception:
                # Some sites concatenate multiple JSON objects; try loose parsing
                # Extract simple availability hints as a last resort
                if "InStock" in txt:
                    return True
                if "OutOfStock" in txt:
                    return False
                continue
            stack = [data]
            while stack:
                cur = stack.pop()
                if isinstance(cur, dict):
                    # Direct availability
                    av = cur.get("availability") or cur.get("itemAvailability")
                    if isinstance(av, str):
                        if "InStock" in av:
                            return True
                        if "OutOfStock" in av:
                            return False
                    # Offers may be nested
                    off = cur.get("offers")
                    if isinstance(off, dict):
                        stack.append(off)
                    elif isinstance(off, list):
                        stack.extend(off)
                    # Walk all keys
                    for v in cur.values():
                        if isinstance(v, (dict,list)):
                            stack.append(v)
                elif isinstance(cur, list):
                    stack.extend(cur)
        return None
    except Exception:
        return None

def detect_stock(soup: BeautifulSoup, html: str, cfg: dict):
    """
    Decide in_stock using three checks (in order):
      1) availability_selector: if a matching button exists and is disabled -> False;
         if exists and not disabled -> True; else fall through.
      2) JSON-LD availability: InStock/OutOfStock.
      3) Text scan using in_stock_text / oos_text across the page.
    """
    # 1) button/selector logic
    sel = cfg.get("availability_selector")
    if sel:
        el = soup.select_one(sel)
        if el:
            # if it's a button and has disabled || aria-disabled true -> out of stock
            attr = (el.get("disabled") is not None) or (str(el.get("aria-disabled","")).lower() in ("1","true","disabled"))
            if attr:
                return False
            # some sites wrap the real button: try to dive into child button
            child_btn = el if el.name == "button" else el.find("button")
            if child_btn:
                if (child_btn.get("disabled") is not None) or (str(child_btn.get("aria-disabled","")).lower() in ("1","true","disabled")):
                    return False
                return True
            # if element exists and no disabled flags -> optimistic True
            return True

    # 2) JSON-LD availability
    jl = jsonld_stock(html)
    if jl is True:  return True
    if jl is False: return False

    # 3) text scan
    text = soup.get_text(" ", strip=True)
    in_pat  = cfg.get("in_stock_text", "")
    oos_pat = cfg.get("oos_text", "")
    if in_pat and re.search(in_pat, text, flags=re.I):
        return True
    if oos_pat and re.search(oos_pat, text, flags=re.I):
        return False
    return None

def parse_one(html: str, cfg: dict):
    soup = BeautifulSoup(html, "html.parser")
    price = list_price = disc = None

    # price (current)
    if cfg.get("price_selector"):
        el = soup.select_one(cfg["price_selector"])
        if el: price = norm_price_text(el.get_text(" ", strip=True))
    # list/strike
    if cfg.get("sale_price_selector"):
        el = soup.select_one(cfg["sale_price_selector"])
        if el: list_price = norm_price_text(el.get_text(" ", strip=True))
    # discount badge
    if cfg.get("discount_selector"):
        el = soup.select_one(cfg["discount_selector"])
        if el: disc = norm_discount_text(el.get_text(" ", strip=True))

    # stock
    in_stock = detect_stock(soup, html, cfg)

    # sanity: derive discount if not given but we have list & price
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
        status, html = fetch(u, ua)
        print(f"- {u}")
        print(f"  status={status} len={len(html)}")
        price, listp, disc, instock = parse_one(html, cfg)
        print(f"  price={price} list={listp} disc={disc} in_stock={instock}")
        # always save HTML so we can inspect when something fails
        ts = int(time.time())
        out = DBG / f"{retailer}_{ts}_{i}.html"
        out.write_text(html, encoding="utf-8")
        print(f"  [saved {out.name}]")
        time.sleep(delay)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--retailers", nargs="+", default=["amazon_fr", "sephora_fr"])
    ap.add_argument("--limit", type=int, default=2)
    ap.add_argument("--rate", type=int, default=22)
    args = ap.parse_args()

    for r in args.retailers:
        run_for(r, args.limit, args.rate)

if __name__ == "__main__":
    main()
