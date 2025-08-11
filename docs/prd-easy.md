# Day 1 — PRD (Non‑Technical, Easy Mode)
*Version:* v1.0  •  *Date:* 2025-08-11

## One‑liner
Track prices and “in/out of stock” for **Top‑30 beauty SKUs** (10 **Haircare**, 10 **Skincare**, 10 **Makeup**) across **Amazon FR, Carrefour FR, Sephora FR** so teams can react fast and avoid lost sales.

## Problem → Solution → Result
- **Problem:** Prices change and items go out of stock without anyone noticing in time.  
- **Solution:** A small tool that checks selected product pages, records price/stock, and highlights changes.  
- **Result:** Faster actions (fix listings, adjust promos), fewer lost sales, cleaner weekly reporting.

## Who is this for?
- **Category Managers:** alerts when hero SKUs go OOS or prices jump.  
- **E‑commerce / Business Analysts:** reliable change logs and simple charts.  
- **Data PM / Product Analyst:** a small, stable, low‑cost pipeline.

---

## What we’ll track (Retail coverage)
- **Top‑30 SKUs**: **10 Haircare, 10 Skincare, 10 Makeup**.  
- **Retailers:** **Amazon FR, Carrefour FR, Sephora FR** → **90 priority pages**.  
- **Broader basket:** up to **≈300 pages** total for daily context.

**Refresh schedule**
- **Priority (90 pages):** every **6 hours** at **00:30, 06:30, 12:30, 18:30 Europe/Paris**, with **±20% jitter**.  
- **Rest (~210 pages):** **daily** at **03:00 Europe/Paris**, with **±20% jitter**.

**Load & cost (BigQuery Sandbox, free)**
- **Requests/day:** `4×90 + 1×(300−90) = 570` total (≈ **190 per retailer/day**).  
- **Storage:** tiny — ~**34 MB** raw checks over 60 days.  
- **Queries:** comfortably within **1 TB/month** free tier.

**Freshness & detection**
- **Priority:** median **≈3h**, worst‑case **≤6h**.  
- **Daily set:** median **≈12h**, worst‑case **≤24h**.  
- **SLO:** ≥95% of pages **fresh ≤24h**; priority pages **≤6h**.

**Politeness & safety**
- **1 request every 12–20s** per retailer, **single thread**, **timeout 10s**, **2 retries** (2s→4s), clear **User‑Agent**, stop/back off on **403/429**.  
- Dev mode: cache HTML locally; avoid refetch loops.

---

## What data we store (simple)
- For each page check: **sku, retailer, url, price, currency, in_stock (yes/no), timestamp, status**.  
- We compute **change events**: **price up/down (≥1%)** and **out‑of‑stock/restock**.

## Success measures
- **Coverage:** ~300 pages tracked; Top‑30 refreshed **4×/day**.  
- **Freshness:** Top‑30 **≤6h**, others **≤24h** (≥95%).  
- **Accuracy:** ≥ **98%** correct price/availability.  
- **Reliability:** ≥ **90%** of runs succeed.

## Risks & how we stay safe
- **Website blocking (esp. Amazon):** low request rate, random jitter, single thread, clear UA; reduce cadence if needed.  
- **Pages change layout:** per‑retailer rules and weekly smoke checks.  
- **Free‑tier limits:** batch loads (no streaming/DML), small data footprint.

## Timeline (4 weeks)
- **W1:** Finalize PRD & Top‑30 list; build sample parser; first test data.  
- **W2:** Clean data tables and tests; generate change events.  
- **W3:** Simple dashboard (KPIs + changes table + OOS hours).  
- **W4:** Monitoring, small runbook, demo.

## Not in scope (for now)
- Logged‑in/paywalled pages; real‑time tracking; recommendations; “all products” for all brands.

## Glossary (plain words)
- **SKU:** a specific product (e.g., BrandA Shampoo 300ml).  
- **Change event:** when price or stock differs from last check.  
- **Freshness:** how recent the latest data is.
