import asyncio, csv, json, pathlib, re, yaml, time
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]
SEED = ROOT/"dbt/seeds/sku_registry.csv"
SEL  = ROOT/"ingestion/selectors.yml"
DBG  = ROOT/"debug"
DBG.mkdir(exist_ok=True)

def norm_price(t):
    m = re.search(r"(\d+[.,]\d{2})", t or "")
    return float(m.group(1).replace(",", ".")) if m else None

def parse_discount_text(t):
    m = re.search(r"(-?\d{1,3})\s*%", t or "")
    return abs(int(m.group(1)))/100.0 if m else None

def is_in_stock(text, in_pat, oos_pat):
    if in_pat and re.search(in_pat, text or "", flags=re.I): return True
    if oos_pat and re.search(oos_pat, text or "", flags=re.I): return False
    return None

def first_two_urls(retailer):
    urls=[]
    with SEED.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["retailer"].strip()==retailer and len(urls)<2:
                urls.append(row["product_url"])
    return urls

def jsonld_price(soup):
    """Try to extract price from schema.org JSON-LD."""
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string)
        except Exception:
            continue
        stack = [data]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                # offers: { price, priceCurrency }, or priceSpecification
                offers = node.get("offers")
                if isinstance(offers, dict):
                    price = offers.get("price") or offers.get("lowPrice")
                    curr  = offers.get("priceCurrency")
                    if price: 
                        try:
                            return float(str(price).replace(",", ".")), curr
                        except Exception:
                            pass
                spec = node.get("priceSpecification")
                if isinstance(spec, dict):
                    price = spec.get("price")
                    curr  = spec.get("priceCurrency")
                    if price:
                        try:
                            return float(str(price).replace(",", ".")), curr
                        except Exception:
                            pass
                stack.extend(node.values())
            elif isinstance(node, list):
                stack.extend(node)
    return None, None

async def fetch_html(pw, url, ua, wait_css, timeout=30000):
    browser = await pw.chromium.launch(headless=True)
    ctx = await browser.new_context(user_agent=ua, locale="fr-FR")
    page = await ctx.new_page()
    resp = await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
    status = resp.status if resp else 0
    # wait a bit for dynamic price nodes if selector given
    if wait_css:
        try:
            await page.wait_for_selector(wait_css, timeout=15000)
        except Exception:
            pass
    html = await page.content()
    await ctx.close(); await browser.close()
    return status, html

async def run_for(retailer):
    cfg_all = yaml.safe_load(SEL.read_text(encoding="utf-8"))
    cfg = cfg_all[retailer]
    ua = cfg.get("user_agent") or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
    rate = int(cfg.get("rate_limit_seconds",20))
    urls = first_two_urls(retailer)
    wait_css = cfg.get("price_selector")

    print(f"\n=== {retailer} (browser mode) ===")
    async with async_playwright() as pw:
        for u in urls:
            try:
                st, html = await fetch_html(pw, u, ua, wait_css)
                print(f"- {u}\n  status={st} len={len(html)}")
                soup = BeautifulSoup(html, "html.parser")

                # 1) CSS price
                price = None
                if cfg.get("price_selector"):
                    el = soup.select_one(cfg["price_selector"])
                    if el: price = norm_price(el.get_text(" ", strip=True))
                # 2) JSON-LD fallback
                currency = None
                if price is None:
                    p, c = jsonld_price(soup)
                    if p is not None:
                        price, currency = p, c
                # 3) Full-text regex fallback (paranoid)
                if price is None:
                    price = norm_price(soup.get_text(" ", strip=True))

                # list price, discount
                list_price = None
                if cfg.get("list_price_selector"):
                    el = soup.select_one(cfg["list_price_selector"])
                    if el: list_price = norm_price(el.get_text(" ", strip=True))
                disc = None
                if cfg.get("discount_selector"):
                    el = soup.select_one(cfg["discount_selector"])
                    if el: disc = parse_discount_text(el.get_text(" ", strip=True))
                if disc is None and (price is not None) and (list_price and list_price>0):
                    disc = max(0.0, min(1.0, (list_price-price)/list_price))

                # availability
                instock = None
                if cfg.get("availability_selector"):
                    el = soup.select_one(cfg["availability_selector"])
                    txt = el.get_text(" ", strip=True) if el else ""
                    instock = is_in_stock(txt, cfg.get("in_stock_text",""), cfg.get("oos_text",""))

                print(f"  price={price} list={list_price} disc={disc} in_stock={instock} currency={currency or cfg.get('currency_hint','')}")
                # dump debug if price still None
                if price is None:
                    out = DBG / f"{retailer}_{int(time.time())}.html"
                    out.write_text(html, encoding="utf-8")
                    print(f"  (saved HTML for inspection → {out})")
            except Exception as e:
                print(f"  ERROR: {e}")
            await asyncio.sleep(rate)

if __name__ == "__main__":
    asyncio.run(run_for("carrefour_fr"))
