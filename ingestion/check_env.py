from dotenv import load_dotenv; load_dotenv()
import csv, os, sys
print("Python:", sys.version)
print("ENV:", os.environ.get("ENV"))
try:
    with open("docs/sku_list.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    print("SKU rows:", len(rows))
    print("First row:", rows[0] if rows else "None")
except FileNotFoundError:
    print("docs/sku_list.csv not found")
