import csv, pathlib, re, time
import requests
from bs4 import BeautifulSoup

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "dbt/seeds/sku_registry.csv"
OUT = ROOT / "data/sephora_url_audit.csv"
OUT.parent.mkdir(parents=True, exist_ok=True)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
TIMEOUT = 12
DELAY_S = 1.5

def canonical_from_html(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    link = soup.find("link", attrs={"rel": "canonical"})
    if link and link.get("href"):
        return link["href"]
    return None

def main():
    rows = list(csv.DictReader(SRC.open(encoding="utf-8")))
    bad = 0
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["sku_id","brand","product_name","old_url","status","final_url","canonical_url","note"])
        for r in rows:
            if r["retailer"].strip().lower() != "sephora_fr":
                continue
            url = r["product_url"].strip()
            note = ""
            try:
                rs = requests.get(
                    url,
                    headers={"User-Agent": UA, "Referer":"https://www.google.com/"},
                    timeout=TIMEOUT,
                    allow_redirects=True,
                )
                status = rs.status_code
                final_url = rs.url
                canon = None
                if status == 200 and "text/html" in rs.headers.get("Content-Type",""):
                    try:
                        canon = canonical_from_html(rs.text)
                    except Exception:
                        pass
                # heuristics for problems
                if status == 404:
                    note = "404"
                    bad += 1
                elif status in (301,302,303,307,308):
                    note = "redirect"
                elif status >= 400:
                    note = f"http_{status}"
                # flag mobile or non-FR domains
                if "m.sephora" in final_url:
                    note = (note + "; " if note else "") + "mobile_url"
                if "sephora.fr" not in final_url:
                    note = (note + "; " if note else "") + "non_fr_domain"
                # tidy canonical (strip query)
                if canon and "?" in canon:
                    canon = canon.split("?",1)[0]
                w.writerow([r["sku_id"], r["brand"], r["product_name"], url, status, final_url, canon or "", note])
            except Exception as e:
                w.writerow([r["sku_id"], r["brand"], r["product_name"], url, "ERR", "", "", f"error:{e}"])
            time.sleep(DELAY_S)
    print(f"Wrote audit → {OUT}  (bad={bad})")

if __name__ == "__main__":
    main()
