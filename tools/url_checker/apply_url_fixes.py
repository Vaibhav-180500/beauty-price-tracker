import csv, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "dbt/seeds/sku_registry.csv"
FIX = ROOT / "data/sephora_url_fixes.csv"
BAK = ROOT / "dbt/seeds/sku_registry.bak.csv"

def main():
    fixes = {}
    with FIX.open(encoding="utf-8") as f:
        rd = csv.DictReader(f)
        for r in rd:
            fixes[r["sku_id"].strip()] = r["new_url"].strip()

    rows = list(csv.DictReader(SRC.open(encoding="utf-8")))
    headers = rows[0].keys() if rows else []

    changed = 0
    SRC.replace(BAK)  # backup original
    with SRC.open("w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=headers)
        wr.writeheader()
        for r in rows:
            if r["retailer"].strip().lower()=="sephora_fr" and r["sku_id"].strip() in fixes:
                r["product_url"] = fixes[r["sku_id"].strip()]
                changed += 1
            wr.writerow(r)
    print(f"Applied {changed} fixes. Backup saved → {BAK}")

if __name__ == "__main__":
    main()
