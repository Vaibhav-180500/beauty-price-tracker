# Day 0 — Setup (Non‑Technical, Easy Mode)

This guide is written for **first‑timers**. No jargon. Follow the steps and tick the boxes ✅.

---

## What we’re making
- A **workspace** on your laptop for this project.
- A free **Google BigQuery** database in the cloud (Sandbox).
- A tiny test called **“hello”** to prove everything works.
- We’ll keep notes so others can repeat your steps.

---

## Tools you need (all free)
- A Google account (Gmail is fine)
- Git + Git Bash (already installed if you followed earlier steps)
- Python 3.11+
- A text editor (VS Code or Notepad works)
- Your GitHub repo: `beauty-price-tracker`

> Think of this like setting up a new kitchen: we’re putting in cupboards (folders), buying a few tools (software), and boiling water once (“hello”) to confirm the stove works.

---

## Step A — Create your cloud project (Google Cloud)
1. Open **https://console.cloud.google.com** and sign in.
2. Top bar → **Project picker** → **New Project** → name it `beauty-price-tracker` → **Create**.
3. Select your new project. Copy the **Project ID** (looks like `beauty-price-tracker-123456`).
4. Left search → **BigQuery** → open **BigQuery Studio** → if asked, click **Enable**.
5. In the left panel, next to your project, click **⋮ → Create dataset**:
   - **Dataset ID:** `bpt_dbt`
   - **Location:** **EU**
   - Click **Create**.

**Why:** A *project* is your workspace. A *dataset* is a folder for the tables we’ll make.

---

## Step B — Prepare your laptop (once)
1. Open **Git Bash** and go to your project folder:
   ```bash
   cd ~/beauty-price-tracker
   ```
2. Turn on your private Python “toolbox” (virtual environment):
   ```bash
   python -m venv .venv
   source .venv/Scripts/activate
   ```
3. Install the few tools we’ll use:
   ```bash
   pip install --upgrade pip
   pip install dbt-bigquery requests beautifulsoup4 pandas pydantic pytest python-dotenv
   ```

**Why:** The virtual environment keeps this project separate from everything else on your computer.

---

## Step C — Tell dbt how to reach Google (one small file)
1. Open your profile file:
   ```bash
   nano ~/.dbt/profiles.yml
   ```
2. Paste this (change the **project** line to your real Project ID), then save:
   ```yaml
   beauty_price_tracker:
     target: dev
     outputs:
       dev:
         type: bigquery
         method: oauth
         project: YOUR_GCP_PROJECT_ID   # change this
         dataset: bpt_dbt
         location: EU
         threads: 4
         priority: interactive
   ```
3. Log in so your laptop can talk to Google:
   ```bash
   gcloud auth login
   gcloud config set project YOUR_GCP_PROJECT_ID
   gcloud services enable bigquery.googleapis.com
   gcloud auth application-default login
   ```

**Why:** This is the “key” that lets your laptop access your BigQuery folder.

---

## Step D — Make the tiny test (“hello”)
1. Create the dbt project file at the **repo root**:
   ```bash
   cat > dbt_project.yml <<'YAML'
   name: 'beauty_price_tracker'
   version: '1.0.0'
   config-version: 2
   profile: 'beauty_price_tracker'
   model-paths: ['dbt/models']
   models:
     beauty_price_tracker:
       +materialized: view
   YAML
   ```
2. Add a simple model:
   ```bash
   mkdir -p dbt/models/staging
   cat > dbt/models/staging/hello.sql <<'SQL'
   select 1 as ok
   SQL
   ```
3. Run checks and build the test:
   ```bash
   dbt debug
   dbt run --select hello
   ```
   You should now see a table/view named **`hello`** in BigQuery → dataset **`bpt_dbt`**.

---

## Step E — Save your settings and notes
1. Create a small settings file:
   ```bash
   cat > .env <<'ENV'
   ENV=dev
   BPT_DEFAULT_CURRENCY=EUR
   ENV
   ```
2. Start your SKU list (you can edit later in Notepad):
   ```bash
   mkdir -p docs
   notepad docs/sku_list.csv
   ```
   Put a header row like:  
   `sku_id,brand,product_name,retailer,product_url,currency`

3. Make a short policy note:  
   `notepad docs/legal-notes.md` → write 3 bullets:
   - Respect robots.txt / Terms
   - ≤1 request every 10–15s per retailer
   - No personal data

---

## Step F — Save your work to GitHub
```bash
git add -A
git commit -m "day0: setup + hello model + docs"
git push
```

---

## Common bumps (and quick fixes)
- **dbt: command not found** → Turn on your toolbox: `source .venv/Scripts/activate`. Then `pip install dbt-bigquery`.
- **dbt_project.yml not found** → Create the file at the **repo root** (see Step D‑1).
- **Google login didn’t open** → Run: `gcloud auth application-default login --no-launch-browser` and follow the link.
- **Git wants name/email** → `git config --global user.name "Your Name"` and `git config --global user.email "you@example.com"`.

---

## You’re done when
- `dbt debug` says **All checks passed** ✅
- `hello` appears in BigQuery dataset `bpt_dbt` ✅
- Your GitHub repo shows today’s commit ✅

Great job! Next you’ll write a simple **PRD** (what we’re building, who it helps, how we’ll measure success).

