"""
Roll the dataset forward so the dashboard never looks back-dated.

Re-anchors the 52-week synthetic price history to *today* and re-exports the
Tableau CSVs. Run on a schedule by .github/workflows/refresh-data.yml.

Usage (from repo root):
    python scripts/refresh_data.py
"""

import os
import sys
import datetime

import pandas as pd

# make `src` importable when run as a plain script
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.scraper.init_db import build_if_missing
from src.scraper.generate_history import generate_and_save
from src.analysis.export_tableau import export_all

DB_PATH       = os.path.join(ROOT, "data", "retail.db")
PRODUCTS_CSV  = os.path.join(ROOT, "data", "raw", "products.csv")


def main() -> None:
    today = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    # 1. Move the product snapshot's "as of" date to today so the current
    #    snapshot stays coherent with the freshly rolled history window.
    products = pd.read_csv(PRODUCTS_CSV)
    products["scraped_at"] = today
    products.to_csv(PRODUCTS_CSV, index=False)
    print(f"products.csv snapshot date set to {today}")

    # 2. Rebuild the DB from the committed CSVs.
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    build_if_missing(DB_PATH)

    # 3. Regenerate the 52-week history ending *today* (rewrites price_history.csv
    #    and the price_history_weekly table) — this is what rolls the 8-week
    #    forecast forward.
    generate_and_save(DB_PATH)

    # 4. Re-export the Tableau CSVs from the refreshed data.
    export_all(DB_PATH)

    print("Data refresh complete — history and exports re-anchored to today.")


if __name__ == "__main__":
    main()
