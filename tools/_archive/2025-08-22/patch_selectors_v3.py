import yaml, re, sys
from pathlib import Path

p = Path("ingestion/selectors.yml")
data = yaml.safe_load(p.read_text(encoding="utf-8"))

def set_block(d, key, updates):
    if key not in d or not isinstance(d[key], dict):
        d[key] = {}
    d[key].update(updates)

# ---------------------------
# AMAZON.FR (hardened)
# ---------------------------
amazon_updates = {
    "enabled": True,
    "rate_limit_seconds": 22,
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Primary live price (Buy Box area first, then sane fallbacks)
    "price_selector": (
        "#corePrice_feature_div .a-price .a-offscreen, "
        "#apex_desktop_feature_div .a-price .a-offscreen, "
        ".reinventPriceToPayBadgePrice .a-price .a-offscreen, "
        ".a-price .a-offscreen"
    ),
    # List/strike price (used for discount calc)
    "sale_price_selector": (
        "#corePrice_feature_div .a-text-price .a-offscreen, "
        "#apex_desktop_feature_div .a-text-price .a-offscreen, "
        ".a-price .a-text-price .a-offscreen, "
        "span[data-a-strike='true'] .a-offscreen"
    ),
    # Discount badge or basis price text if present
    "discount_selector": (
        ".savingsPercentage, "
        ".basisPriceLegalMessage, "
        ".a-size-base.a-color-secondary .aok-inline-block"
    ),
    # Availability: any of these present means likely purchasable
    "availability_selector": (
        "#availability, "
        "#availability .a-color-success, "
        "#add-to-cart-button, "
        "#buy-now-button"
    ),
    # FR/EN signals
    "in_stock_text": "En stock|In stock|Add to Basket|Buy Now|Ajouter au panier",
    "oos_text": "Actuellement indisponible|Currently unavailable|Temporarily out of stock",
    # parsing regexes
    "price_regex": r"(\\d+[\\.,]\\d{2})",
    "discount_regex": r"(-?\\d{1,3})\\s*%",
    "currency_hint": "EUR",
    "notes": "Amazon DOM varies by seller; ensure URL pins the correct variant/size.",
}

# ---------------------------
# SEPHORA.FR (hardened)
# ---------------------------
sephora_updates = {
    "enabled": True,
    "rate_limit_seconds": 22,
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "price_selector": (
        ".product-price .price-sales, "
        "[data-comp='Price'] [data-testid='price-value'], "
        ".Price .Text, "
        "[itemprop='price']"
    ),
    "sale_price_selector": (
        ".product-price .price-standard, "
        ".Price .is-crossed, "
        "[data-testid='price-was'], "
        "[class*='strike']"
    ),
    "discount_selector": (
        "[data-testid='promo-badge'], "
        ".Badge--discount, "
        "[class*='discount'], "
        "[class*='promotion']"
    ),
    "unit_price_selector": (
        ".unit-price, "
        "[data-testid='unit-price'], "
        "[class*='unit-price']"
    ),
    "availability_selector": (
        "button#add-to-cart, "
        "form[id^='dwfrm_product_addtocart'], "
        ".product-stock-content, "
        ".product__stock, "
        ".product-info, "
        ".product-purchase, "
        "[class*='availability'], "
        "[data-test*='availability'], "
        "[data-test*='stock']"
    ),
    "in_stock_text": "Ajouter au panier|En stock|Disponible|In stock|Available",
    "oos_text": "Rupture|Victime de son succès|Indisponible|Out of stock|Unavailable|Sold out|Me prévenir|Notify me",
    "price_regex": r"(\\d+[\\.,]\\d{2})",
    "discount_regex": r"(-?\\d{1,3})\\s*%",
    "unit_price_regex": r"(\\d+[\\.,]\\d{2})\\s*€?\\s*/\\s*(\\d+)\\s*(ml|g)",
    "currency_hint": "EUR",
    "notes": "Sephora often has multiple sizes/variants on the same PDP; keep URL + variant_id consistent.",
}

set_block(data, "amazon_fr", amazon_updates)
set_block(data, "sephora_fr", sephora_updates)

p.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
print("Patch applied to:", p)
