import csv, pathlib, re

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "dbt/seeds/sku_registry.csv"
BAK = ROOT / "dbt/seeds/sku_registry.bak_urls.csv"

AMZ_DP = re.compile(r"https?://(?:www\.)?amazon\.fr/.{0,120}?/dp/([A-Z0-9]{10})", re.I)
AMZ_ASIN = re.compile(r"https?://(?:www\.)?amazon\.fr/(?:gp/product|dp)/([A-Z0-9]{10})", re.I)

def canon_amz(url: str) -> str | None:
    for rx in (AMZ_DP, AMZ_ASIN):
        m = rx.search(url)
        if m:
            asin = m.group(1).upper()
            return f"https://www.amazon.fr/dp/{asin}"
    return None

def main():
    rows = list(csv.DictReader(SRC.open(encoding="utf-8")))
    headers = rows[0].keys() if rows else []
    changes = 0
    SRC.replace(BAK)  # backup
    with SRC.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        for r in rows:
            if r["retailer"].strip().lower() == "amazon_fr":
                new = canon_amz(r["product_url"])
                if new and new != r["product_url"]:
                    r["product_url"] = new
                    changes += 1
            w.writerow(r)
    print(f"Normalized {changes} Amazon URLs. Backup → {BAK}")

if __name__ == "__main__":
    main()
