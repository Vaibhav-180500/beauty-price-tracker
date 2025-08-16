# tools/test_selectors.py
# Selector smoke test with JSON-LD + microdata availability fallback
# and disabled-button handling.

import time, re, csv, json, pathlib, requests, yaml
from bs4 import BeautifulSoup

ROOT = pathlib.Path(__file__).resolve().parents[1]
SEED = ROOT / "dbt/seeds/sku_registry.csv"
SEL  = ROOT / "ingestion/selectors.yml"

def headers(ua: str | None) -> dict:
    return {
        "User-Agent": ua or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Connection": "close",
        "Referer": "https://www.google.com/",
    }

def norm_price(text: str | None) -> float | None:
    m = re.search(r"(\d+[.,]\d{2})", text or "")
    return float(m.group(1).replace(",", ".")) if m else None

def parse_discount_text(text: str | None) -> float | None:
    m = re.search(r"(-?\d{1,3})\s*%", text or "")
    return abs(int(m.group(1))) / 100.0 if m else None

def is_in_stock(text: str, in_pat: str, oos_pat: str) -> bool | None:
    if in_pat and re.search(in_pat, text or "", flags=re.I): return True
    if oos_pat and re.search(oos_pat, text or "", flags=re.I): return False
    return None

def examples_from_seed() -> dict[str, list[str]]:
    by: dict[str, list[str]] = {}
    with SEED.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            r = row["retailer"].strip()
            by.setdefault(r, [])
            if len(by[r]) < 3:
                by[r].append(row["product_url"])
    return by

# -------- JSON-LD availability/price --------

def jsonld_offers(soup: BeautifulSoup) -> tuple[float | None, str | None, bool | None]:
    def collect(node, bag):
        if isinstance(node, dict):
            if "offers" in node: bag.append(node["offers"])
            for v in node.values(): collect(v, bag)
        elif isinstance(node, list):
            for v in node: collect(v, bag)

    offers_nodes = []
    for s in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(s.string or "")
        except Exception:
            continue
        collect(data, offers_nodes)

    flat = []
    for o in offers_nodes:
        if isinstance(o, list):
            flat.extend([x for x in o if isinstance(x, dict)])
        elif isinstance(o, dict):
            flat.append(o)

    price = currency = None
    instock = None
    for o in flat:
        avail = o.get("availability") or o.get("itemAvailability")
        if isinstance(avail, str):
            if "InStock" in avail: instock = True
            elif "OutOfStock" in avail: instock = False
        p = o.get("price") or o.get("lowPrice") or o.get("highPrice")
        if p is not None and price is None:
            try: price = float(str(p).replace(",", "."))
            except Exception: pass
        c = o.get("priceCurrency")
        if c and not currency: currency = c
    return price, currency, instock

# -------- Microdata/meta availability --------

def microdata_availability(soup: BeautifulSoup) -> bool | None:
    # itemprop availability
    el = soup.select_one('link[itemprop="availability"], meta[itemprop="availability"], [itemprop="availability"]')
    if el:
        val = el.get("href") or el.get("content") or el.get_text(" ", strip=True)
        val = (val or "").strip()
        if "InStock" in val: return True
        if "OutOfStock" in val: return False

    # og/product availability style
    el = soup.select_one('meta[property="product:availability"], meta[name="availability"]')
    if el:
        val = (el.get("content") or "").lower()
        if "instock" in val or "in stock" in val: return True
        if "out of stock" in val or "oos" in val: return False

    return None

# -------- Core extraction --------

def extract_with_fallback(soup: BeautifulSoup, sel: dict) -> tuple[float | None, float | None, float | None, bool | None]:
    # price
    price = None
    if sel.get("price_selector"):
        el = soup.select_one(sel["price_selector"])
        if el: price = norm_price(el.get_text(" ", strip=True))
    if price is None:
        price = norm_price(soup.get_text(" ", strip=True))
        if price is None:
            jl_price, _, _ = jsonld_offers(soup)
            if jl_price is not None: price = jl_price

    # list price
    list_price = None
    list_sel = sel.get("list_price_selector") or sel.get("sale_price_selector")
    if list_sel:
        el = soup.select_one(list_sel)
        if el: list_price = norm_price(el.get_text(" ", strip=True))

    # discount
    disc = None
    if sel.get("discount_selector"):
        el = soup.select_one(sel["discount_selector"])
        if el: disc = parse_discount_text(el.get_text(" ", strip=True))
    if disc is None and (price is not None) and (list_price and list_price > 0):
        disc = max(0.0, min(1.0, (list_price - price) / list_price))

    # availability: selector → button attrs → text → JSON-LD → microdata
    instock = None
    if sel.get("availability_selector"):
        el = soup.select_one(sel["availability_selector"])
        if el and el.name != "button":
            btn = el.select_one(
                "button#add-to-cart, button[name='add'], button[data-event='addToCart'], button[type='submit']"
            )
            if btn: el = btn

        txt = el.get_text(" ", strip=True) if el else ""

        if el and el.name == "button":
            classes = " ".join(el.get("class", [])).lower()
            disabled_attr = (
                el.has_attr("disabled")
                or el.get("aria-disabled") == "true"
                or el.get("data-disabled") == "true"
                or "disabled" in classes
                or "add-to-cart-disabled" in classes
                or "notify" in classes
            )
            if disabled_attr:
                instock = False

        if instock is None:
            instock = is_in_stock(txt, sel.get("in_stock_text",""), sel.get("oos_text",""))

    if instock is None:
        _, _, jl_in = jsonld_offers(soup)
        if jl_in is not None:
            instock = jl_in

    if instock is None:
        md_in = microdata_availability(soup)
        if md_in is not None:
            instock = md_in

    return price, list_price, disc, instock

# -------- Runner --------

def main():
    cfg_all = yaml.safe_load(SEL.read_text(encoding="utf-8"))
    examples = {r: (cfg_all[r].get("examples") or [])[:3]
                for r in cfg_all if isinstance(cfg_all[r], dict)}
    seed_ex = examples_from_seed()
    for r, urls in seed_ex.items():
        if not examples.get(r): examples[r] = urls

    for retailer, urls in sorted(examples.items()):
        sel = cfg_all.get(retailer, {})
        if not isinstance(sel, dict) or not sel.get("enabled", True): continue
        rate = int(sel.get("rate_limit_seconds", 20))
        ua = sel.get("user_agent")

        print(f"\n=== {retailer} (rate_limit={rate}s) ===")
        for url in urls:
            try:
                rs = requests.get(url, headers=headers(ua), timeout=15)
                print(f"- {url}\n  status={rs.status_code} len={len(rs.text)}")
                rs.raise_for_status()
                soup = BeautifulSoup(rs.text, "html.parser")
                price, list_price, disc, instock = extract_with_fallback(soup, sel)
                print(f"  price={price} list={list_price} disc={disc} in_stock={instock}")
                # Optional: write debug if availability still None
                if instock is None:
                    dbgdir = ROOT / "debug"
                    dbgdir.mkdir(exist_ok=True)
                    fn = dbgdir / f"{retailer}_{int(time.time())}.html"
                    fn.write_text(rs.text, encoding="utf-8")
                    print(f"  (saved HTML for inspection → {fn})")
            except Exception as e:
                print(f"  ERROR: {e}")
            time.sleep(rate)

if __name__ == "__main__":
    main()
