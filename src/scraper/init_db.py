"""
Build the SQLite database from CSV files if it doesn't already exist.
Called on Streamlit app startup so HuggingFace Spaces work without pre-built DB.
"""

import os
import sqlite3
import logging

import pandas as pd

logger = logging.getLogger(__name__)

BASE = os.path.join(os.path.dirname(__file__), "..", "..")
DB_PATH      = os.path.join(BASE, "data", "retail.db")
PRODUCTS_CSV = os.path.join(BASE, "data", "raw", "products.csv")
HISTORY_CSV  = os.path.join(BASE, "data", "raw", "price_history.csv")


def build_if_missing(db_path: str = DB_PATH) -> bool:
    if os.path.exists(db_path):
        return False

    logger.info("DB not found — building from CSV files…")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)

    products = pd.read_csv(PRODUCTS_CSV)
    products.to_sql("products", conn, if_exists="replace", index=False)
    logger.info(f"  products table: {len(products):,} rows")

    history = pd.read_csv(HISTORY_CSV)
    history.to_sql("price_history_weekly", conn, if_exists="replace", index=False)
    logger.info(f"  price_history_weekly table: {len(history):,} rows")

    conn.execute("CREATE INDEX IF NOT EXISTS idx_prod_scraped ON products(scraped_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_hist_cat ON price_history_weekly(category)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_hist_pid ON price_history_weekly(product_id)")
    conn.commit()
    conn.close()
    logger.info("DB build complete.")
    return True
