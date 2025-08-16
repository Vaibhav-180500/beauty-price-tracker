# Day 03 — Selector Prototyping & Smoke Tests (Technical)

**Objective:** robust per‑retailer extraction of `price`, `list_price`, `discount_pct`, and `in_stock`.

**Files updated**
- `ingestion/selectors.yml` (v2 promoted)
- `tools/test_selectors.py` (v2 tester promoted; saves debug HTML on ambiguity)
- `.gitignore` ensures `debug/` is ignored

Branch flow: `feat/discount-parsing-v2 → rebase on main → promote v2 → merge --no-ff to main`

---

## Retailer coverage (highlights)

### Amazon FR
Key selectors / logic (v2):
```yaml
price_selector: "#corePrice_feature_div .a-price .a-offscreen"
list_price_selector: >
  #corePrice_feature_div span.a-price.a-text-price span.a-offscreen,
  #corePrice_feature_div [data-a-strike='true'] span.a-offscreen
discount_selector: >
  #corePrice_feature_div .savingsPercentage,
  #apex_desktop .savingsPercentage,
  .reinventPriceSavingsPercentageMargin .savingsPercentage
availability_selector: >
  #availabilityInsideBuyBox_feature_div,
  #availability,
  #availability span,
  #add-to-cart-button,
  #buy-now-button
in_stock_text: "In stock|En stock"
oos_text: "Currently unavailable|Actuellement indisponible|Temporarily out of stock"
```
- **Unit‑price guard**: ignore texts like “€/l” or “€/100 ml” for `list_price`.
- If badge exists but `list_price` is missing/implausible, recompute from price & badge:
  `list_price = round(price / (1 - discount), 2)`.

### Sephora FR
```yaml
price_selector: >
  .product-price .price-sales,
  [data-comp='Price'] .Text,
  .Price .Text,
  [itemprop='price']
list_price_selector: >
  .product-price .price-standard,
  .Price .is-crossed,
  [data-testid='price-was'],
  [class*='strike']
discount_selector: >
  [data-testid='promo-badge'],
  .Badge--discount,
  [class*='discount'],
  [class*='promotion']
compute_discount_from_list_price: false
availability_selector: >
  button#add-to-cart,
  button[name="add"],
  button[data-event="addToCart"],
  form[id^="dwfrm_product_addtocart"] button[type="submit"],
  .product-stock-content,
  .product__stock,
  .product-purchase
in_stock_text: "Ajouter au panier|En stock|Disponible|In stock|Available"
oos_text: "Rupture|Victime de son succès|Indisponible|Out of stock|Unavailable|Sold out|Me prévenir|Notify me"
```
- **Discount policy**: only badge/strike; do **not** infer from list price (avoids unit‑price bleed).
- Availability via button presence/disabled/ARIA; then full‑page text scan.

### Carrefour FR (paused)
- Scripted fetch leads to 404/blocked pages.
- Plan: Playwright with humane cadence, cookies, extra waits.

---

## Tester behaviour (v2)

- Visibility filter for hidden nodes (`display:none`, `aria-hidden`, etc.).
- Unit‑price guard for `list_price`.
- JSON‑LD (`offers.price`, `offers.availability`) and microdata fallbacks.
- Availability from button disabled/ARIA **or** page‑wide text matching.
- Saves the fetched HTML into `debug/` when something is `None` or suspicious.

Run:
```bash
source .venv/Scripts/activate
python tools/test_selectors.py
```

Expected for `https://www.amazon.fr/dp/B08TWTQDCX`:
```
price=23.0  list=29.5  disc=0.22  in_stock=True
```

---

## Issues & fixes

1) **YAML regex escaped incorrectly** → Use **single quotes** around patterns in YAML.  
2) **Amazon list captured as unit price** → Restrict to strike containers; recompute from badge if needed.  
3) **Amazon `in_stock=None`** → Add `#availabilityInsideBuyBox_feature_div` + page‑text fallback.  
4) **Sephora false discounts** → `compute_discount_from_list_price: false` and visible badge/strike only.  
5) **Carrefour blocking** → Park retailer; move to headless browser approach later.

---

## Definition of Done (D03)

- Stable selectors for **Amazon FR** and **Sephora FR** with correct `price`, `list_price`, `discount_pct`, `in_stock`.
- Tester prints expected values; debug artifacts saved on demand.
- Changes merged to **main**; Carrefour plan documented.

---

## Next steps

- Implement `extract.py` that reads `dbt/seeds/sku_registry.csv`, respects `retail_coverage.yml`,
  parses with these selectors and appends to CSV → load to **BigQuery** (`raw_prices`, `raw_availability`).
- Create dbt staging models to normalize price history and stock events.
