import argparse, csv, re, time, pathlib, yaml, requests
from bs4 import BeautifulSoup

ROOT = pathlib.Path(__file__).resolve().parents[1]
SEED = ROOT / "dbt" / "seeds" / "sku_registry.csv"
SEL = ROOT / "ingestion" / "selectors.yml"
DEBUG_DIR = ROOT / "debug"
DEBUG_DIR.mkdir(exist_ok=True)

# ------------------------
# Helpers
# ------------------------
def norm_price(text):
    if not text: return None
    m = re.search(r"(\d+[\.,]\d{2})", text.replace("\xa0"," ").replace(" "," "))
    return float(m.group(1).replace(",", ".")) if m else None

def parse_percent(text):
    if not text: return None
    m = re.search(r"(-?\d{1,3})\s*%", text)
    return abs(int(m.group(1))) / 100.0 if m else None

def text_has_any(text, patterns):
    if not patterns: return False
    return re.search(patterns, text, flags=re.I) is not None

def fetch(url, ua, rate):
    headers = {
        "User-Agent": ua,
        "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Accept": "text/html,application/xhtml+xml",
        "Connection": "close",
    }
    time.sleep(rate)
    resp = requests.get(url, headers=headers, timeout=25)
    return resp.status_code, resp.text

def first_two_urls(retailer):
    urls = []
    with SEED.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("retailer","").strip()==retailer and row.get("product_url"):
                urls.append(row["product_url"])
            if len(urls)>=2: break
    return urls

# ------------------------
# Core parsing per retailer with fallback logic
# ------------------------
def parse_amazon(html, cfg):
    soup = BeautifulSoup(html, "html.parser")
    # price (current)
    price = None
    for sel in [cfg.get("price_selector"), "#apex_desktop .a-price .a-offscreen, #corePrice_feature_div .a-price .a-offscreen"]:
        if not sel: continue
        el = soup.select_one(sel)
        price = norm_price(el.get_text(" ", strip=True)) if el else None
        if price: break
    # list price (strike)
    listp = None
    for sel in [cfg.get("sale_price_selector"), "#apex_desktop .a-price.a-text-price .a-offscreen, #corePrice_feature_div .a-price.a-text-price .a-offscreen, .a-price .a-text-price .a-offscreen"]:
        if not sel: continue
        el = soup.select_one(sel)
        listp = norm_price(el.get_text(" ", strip=True)) if el else None
        if listp: break
    # discount
    disc = None
    for sel in [cfg.get("discount_selector"), "#apex_desktop .savingsPercentage, #corePrice_feature_div .savingsPercentage, .reinventPriceToPayMargin .savingsPercentage"]:
        if not sel: continue
        el = soup.select_one(sel)
        disc = parse_percent(el.get_text(" ", strip=True)) if el else None
        if disc: break
    # fallback discount if list & price known
    if disc is None and listp and price:
        try:
            d = round((listp - price) / listp, 4)
            if d > 0.0: disc = d
        except Exception: pass
    # stock
    in_stock = None
    avail_sel = cfg.get("availability_selector") or "#availability, #add-to-cart-button, #buy-now-button"
    avail_el = soup.select_one(avail_sel)
    text = avail_el.get_text(" ", strip=True) if avail_el else soup.get_text(" ", strip=True)

    if text_has_any(text, cfg.get("oos_text", "")):
        in_stock = False
    elif text_has_any(text, cfg.get("in_stock_text", "")):
        in_stock = True

    # button disabled check
    btn = soup.select_one("#add-to-cart-button")
    if btn and "disabled" in (btn.get("class") or []) or btn and btn.has_attr("disabled"):
        in_stock = False
    if in_stock is None:
        # final heuristic
        in_stock = bool(soup.select_one("#add-to-cart-button") or soup.select_one("#buy-now-button"))

    return price, listp, disc, in_stock

def parse_sephora(html, cfg):
    soup = BeautifulSoup(html, "html.parser")
    # price
    price = None
    for sel in [cfg.get("price_selector"),
                ".product-price .price-sales, [itemprop='price'], .Price .Text"]:
        if not sel: continue
        el = soup.select_one(sel)
        price = norm_price(el.get_text(" ", strip=True)) if el else None
        if price: break
    # list
    listp = None
    for sel in [cfg.get("sale_price_selector"),
                ".product-price .price-standard, .Price .is-crossed, [class*='strike']"]:
        if not sel: continue
        el = soup.select_one(sel)
        listp = norm_price(el.get_text(" ", strip=True)) if el else None
        if listp: break
    # discount
    disc = None
    for sel in [cfg.get("discount_selector"),
                "[data-testid='promo-badge'], .Badge--discount, [class*='discount']"]:
        if not sel: continue
        el = soup.select_one(sel)
        disc = parse_percent(el.get_text(" ", strip=True)) if el else None
        if disc: break
    if disc is None and listp and price:
        try:
            d = round((listp - price) / listp, 4)
            if d > 0.0: disc = d
        except Exception: pass
    # stock
    in_stock = None
    avail_sel = cfg.get("availability_selector") or "form[id^='dwfrm_product_addtocart'], button#add-to-cart, .product-stock-content, .product__stock"
    avail_el = soup.select_one(avail_sel)
    text = avail_el.get_text(" ", strip=True) if avail_el else soup.get_text(" ", strip=True)
    if text_has_any(text, cfg.get("oos_text", "")):
        in_stock = False
    elif text_has_any(text, cfg.get("in_stock_text", "")):
        in_stock = True
    # disabled add-to-cart
    btn = soup.select_one("button#add-to-cart")
    if btn and (btn.has_attr("disabled") or "disabled" in (btn.get("class") or [])):
        in_stock = False
    return price, listp, disc, in_stock

PARSERS = {
    "amazon_fr": parse_amazon,
    "sephora_fr": parse_sephora,
}

def run_for(retailer, limit=None, rate=22):
    cfg_all = yaml.safe_load(SEL.read_text(encoding="utf-8"))
    if retailer not in cfg_all:
        print(f"!! no config for {retailer}")
        return
    cfg = cfg_all[retailer]
    ua = cfg.get("user_agent") or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome Safari"
    urls = first_two_urls(retailer) if limit is None else first_two_urls(retailer)[:limit]

    print(f"\n=== {retailer} (rate={rate}s) ===")
    for u in urls:
        status, html = fetch(u, ua, rate)
        soup_len = len(html or "")
        price=listp=disc=in_stock=None
        parser = PARSERS.get(retailer)
        if parser:
            price, listp, disc, in_stock = parser(html, cfg)
        print(f"- {u}\n  status={status} len={soup_len} price={price} list={listp} disc={disc} in_stock={in_stock}")
        # save debug on missing values
        if status!=200 or price is None:
            ts = int(time.time())
            out = DEBUG_DIR / f"{retailer}_{ts}.html"
            out.write_text(html or "", encoding="utf-8", errors="ignore")
            print(f"  [saved {out.name}]")

if __name__=="__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--retailers", nargs="+", default=["amazon_fr","sephora_fr"])
    ap.add_argument("--limit", type=int, default=2)
    ap.add_argument("--rate", type=int, default=22)
    args = ap.parse_args()
    for r in args.retailers:
        run_for(r, limit=args.limit, rate=args.rate)
