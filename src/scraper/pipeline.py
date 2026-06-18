"""
Scraping pipeline — runs Woolworths + Coles scrapers, saves to SQLite and CSV.

Usage:
    python -m src.scraper.pipeline
    python -m src.scraper.pipeline --max-pages 3
    python -m src.scraper.pipeline --source woolworths
"""

import argparse
import logging
import os
import sqlite3
from datetime import datetime
from typing import List, Dict

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "retail.db")
CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "raw", "products.csv")

CREATE_PRODUCTS_SQL = """
CREATE TABLE IF NOT EXISTS products (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id      TEXT NOT NULL,
    source          TEXT NOT NULL,
    name            TEXT NOT NULL,
    brand           TEXT,
    category        TEXT NOT NULL,
    price           REAL NOT NULL,
    was_price       REAL,
    is_on_special   INTEGER DEFAULT 0,
    discount_pct    REAL DEFAULT 0,
    unit_size       TEXT,
    cup_price       REAL,
    cup_measure     TEXT,
    avg_rating      REAL,
    review_count    INTEGER DEFAULT 0,
    scraped_at      TEXT NOT NULL
);
"""

CREATE_PRICE_HISTORY_SQL = """
CREATE TABLE IF NOT EXISTS price_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id  TEXT NOT NULL,
    source      TEXT NOT NULL,
    price       REAL NOT NULL,
    was_price   REAL,
    is_special  INTEGER DEFAULT 0,
    scraped_at  TEXT NOT NULL
);
"""

CREATE_INDEXES_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);",
    "CREATE INDEX IF NOT EXISTS idx_products_source ON products(source);",
    "CREATE INDEX IF NOT EXISTS idx_price_history_pid ON price_history(product_id);",
]


def init_db(db_path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(CREATE_PRODUCTS_SQL)
    conn.execute(CREATE_PRICE_HISTORY_SQL)
    for idx_sql in CREATE_INDEXES_SQL:
        conn.execute(idx_sql)
    conn.commit()
    return conn


def save_to_db(conn: sqlite3.Connection, products: List[Dict], scraped_at: str) -> int:
    cursor = conn.cursor()
    inserted = 0

    for p in products:
        cursor.execute(
            """
            INSERT INTO products
                (product_id, source, name, brand, category, price, was_price,
                 is_on_special, discount_pct, unit_size, cup_price, cup_measure,
                 avg_rating, review_count, scraped_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                p["product_id"], p["source"], p["name"], p.get("brand"),
                p["category"], p["price"], p.get("was_price"),
                int(p.get("is_on_special", False)), p.get("discount_pct", 0),
                p.get("unit_size"), p.get("cup_price"), p.get("cup_measure"),
                p.get("avg_rating"), p.get("review_count", 0),
                scraped_at,
            ),
        )
        cursor.execute(
            """
            INSERT INTO price_history (product_id, source, price, was_price, is_special, scraped_at)
            VALUES (?,?,?,?,?,?)
            """,
            (
                p["product_id"], p["source"], p["price"], p.get("was_price"),
                int(p.get("is_on_special", False)), scraped_at,
            ),
        )
        inserted += 1

    conn.commit()
    return inserted


def run(sources: List[str], max_pages: int) -> pd.DataFrame:
    all_products = []
    scraped_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    if "woolworths" in sources:
        from src.scraper.woolworths import scrape_all as ww_scrape
        logger.info("=== Woolworths ===")
        ww_products = ww_scrape(max_pages_per_category=max_pages)
        all_products.extend(ww_products)

    if "coles" in sources:
        from src.scraper.coles import scrape_all as co_scrape
        logger.info("=== Coles ===")
        co_products = co_scrape(max_pages_per_category=max_pages)
        all_products.extend(co_products)

    if not all_products:
        logger.warning("No products scraped.")
        return pd.DataFrame()

    df = pd.DataFrame(all_products)
    df["scraped_at"] = scraped_at

    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
    df.to_csv(CSV_PATH, index=False)
    logger.info(f"CSV saved: {CSV_PATH}  ({len(df)} rows)")

    conn = init_db(DB_PATH)
    inserted = save_to_db(conn, all_products, scraped_at)
    conn.close()
    logger.info(f"DB saved: {DB_PATH}  ({inserted} rows inserted)")

    print(f"\n{'='*50}")
    print(f"  Total products scraped : {len(df)}")
    print(f"  Sources                : {', '.join(sources)}")
    print(f"  Categories             : {df['category'].nunique()}")
    print(f"  On special             : {df['is_on_special'].sum()} ({df['is_on_special'].mean()*100:.1f}%)")
    print(f"  Avg price              : ${df['price'].mean():.2f}")
    print(f"{'='*50}\n")

    return df


def main():
    parser = argparse.ArgumentParser(description="Scrape Woolworths and Coles product data")
    parser.add_argument(
        "--source",
        choices=["woolworths", "coles", "both"],
        default="both",
    )
    parser.add_argument("--max-pages", type=int, default=5)
    args = parser.parse_args()

    sources = ["woolworths", "coles"] if args.source == "both" else [args.source]
    run(sources=sources, max_pages=args.max_pages)


if __name__ == "__main__":
    main()
