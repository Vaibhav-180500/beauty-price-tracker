# Tools

**Active tools (supported):**
- `test_selectors.py` — default selector tester (prints price/list/discount/stock)
- `test_selectors_hardened.py` — tester with rate/retailer flags  
  Example: `python tools/test_selectors_hardened.py --retailers amazon_fr sephora_fr --limit 2 --rate 22`
- `url_checker.py` — audit URLs for 200/404/redirects
- `normalize_amazon_urls.py` — normalize Amazon FR URLs

**Archived tools:** see `tools/_archive/` for older or one-off scripts we keep for reference.
