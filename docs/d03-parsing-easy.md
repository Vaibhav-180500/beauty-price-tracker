# Day 03 — Making the Price Robot “See” (Non‑Technical)

**Goal today:** teach the tracker how to read a product page and tell us:
- the **current price**
- the **old/strike price** (if any)
- the **discount %** (if any)
- whether the item is **in stock**

We tested this for **Amazon France** and **Sephora France**.  
(**Carrefour** is paused for now because their site blocks robots aggressively.)

---

## What we changed

### ✅ Amazon FR
- Finds the **current price** reliably.
- Grabs the **old/strike price** instead of the per‑litre/100ml unit price.
- Reads the green **“In stock”** message even when it appears in different places.
- If Amazon shows a **“‑22%”** type badge, we compute the implied old price to double‑check.

### ✅ Sephora FR
- Uses the **Add to cart** button state to determine **“in stock”** or **“sold out”**.
- Ignores hidden/unit‑price numbers so it doesn’t “invent” discounts.
- Only reports a discount if there’s a **real badge or strike‑through** on the page.

### ⏸️ Carrefour FR (parked)
- The page that loads in a browser returns **blocked/404** to scripts.
- We’ll revisit with a slower, respectful headless browser (Playwright) and cookies.

---

## How you can try it now

Open **Git Bash** in your project folder and run:

```bash
cd ~/beauty-price-tracker
source .venv/Scripts/activate
python tools/test_selectors.py
```

You’ll see lines like:

```
price=23.0  list=29.5  disc=0.22  in_stock=True   # Amazon example
price=29.9  list=None  disc=None  in_stock=True   # Sephora example
```

- **price** = current price  
- **list** = old/struck price (if shown)  
- **disc** = discount as a decimal (0.22 = 22%)  
- **in_stock** = True/False

---

## What was hard (and how we solved it)

- **Sites show multiple numbers** in the same area (e.g., “€230.00 / l”).  
  → We look only at the **strike‑through** container for old price, not unit price.

- **“In stock” moves around** (especially on Amazon).  
  → We check several common spots and finally scan the page text for “In stock / En stock”.

- **Some retailers block scripts** (Carrefour).  
  → We’ll come back with a lightweight browser that behaves more like a human.

---

## Today’s outcome

- Amazon + Sephora parsing is **stable enough** for the MVP.
- The testing script prints **price / old price / discount / in‑stock** for sample pages.
- Work has been merged to **main** so we can build the actual data extractor next.

---

## What’s next (tomorrow)

- A small command that reads our **SKU list**, applies these rules to many pages,
  and saves the results (first locally, then to **BigQuery**).
- Create raw tables in **BigQuery**, and first **dbt** cleaning models.
