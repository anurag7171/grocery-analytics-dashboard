"""
Generate 52-week synthetic price history anchored to real scraped Woolworths prices.

Each product's history is derived from its actual current price with:
- Category-specific seasonal patterns (Southern Hemisphere calendar)
- Realistic annual inflation per category
- Random promotional specials every 4-8 weeks
- Gaussian noise scaled to category volatility
"""

import os
import math
import sqlite3
import logging
import random
from datetime import date, timedelta
from typing import List, Dict

import pandas as pd

logger = logging.getLogger(__name__)

WEEKS = 52
SEED = 42

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "retail.db")
CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "raw", "price_history.csv")

# Southern Hemisphere seasons: summer = Dec-Feb (weeks 48-52 / 0-8)
# seasonal_peak = week of year when price is highest (0-51)
CATEGORY_PARAMS = {
    "Fruit & Veg":       {"vol": 0.07, "amp": 0.25, "inflation": 0.050, "peak_week": 0,  "special_freq": 5},
    "Meat & Seafood":    {"vol": 0.04, "amp": 0.15, "inflation": 0.055, "peak_week": 0,  "special_freq": 6},
    "Dairy & Eggs":      {"vol": 0.02, "amp": 0.08, "inflation": 0.040, "peak_week": 26, "special_freq": 8},
    "Bakery":            {"vol": 0.02, "amp": 0.05, "inflation": 0.038, "peak_week": 26, "special_freq": 7},
    "Pantry":            {"vol": 0.01, "amp": 0.03, "inflation": 0.035, "peak_week": 26, "special_freq": 8},
    "Snacks":            {"vol": 0.02, "amp": 0.06, "inflation": 0.030, "peak_week": 0,  "special_freq": 5},
    "Drinks":            {"vol": 0.02, "amp": 0.08, "inflation": 0.030, "peak_week": 0,  "special_freq": 5},
    "Frozen":            {"vol": 0.02, "amp": 0.06, "inflation": 0.033, "peak_week": 26, "special_freq": 7},
    "Health & Wellness": {"vol": 0.01, "amp": 0.03, "inflation": 0.028, "peak_week": 26, "special_freq": 9},
    "Household":         {"vol": 0.01, "amp": 0.02, "inflation": 0.025, "peak_week": 26, "special_freq": 10},
}
DEFAULT_PARAMS = {"vol": 0.02, "amp": 0.05, "inflation": 0.035, "peak_week": 26, "special_freq": 7}


def _generate_series(base_price: float, category: str, seed: int) -> List[Dict]:
    rng = random.Random(seed)
    p = CATEGORY_PARAMS.get(category, DEFAULT_PARAMS)

    inflation_weekly = (1 + p["inflation"]) ** (1 / 52) - 1
    special_countdown = rng.randint(1, p["special_freq"])
    special_weeks_left = 0

    rows = []
    for w in range(WEEKS):
        trend = base_price * ((1 + inflation_weekly) ** w)
        seasonal = 1 + p["amp"] * math.cos(2 * math.pi * (w - p["peak_week"]) / 52)
        noise = rng.gauss(0, p["vol"])
        regular_price = round(trend * seasonal, 2)
        price = round(trend * seasonal * (1 + noise), 2)

        is_special = False
        if special_weeks_left > 0:
            discount = rng.uniform(0.10, 0.32)
            price = round(price * (1 - discount), 2)
            is_special = True
            special_weeks_left -= 1
            if special_weeks_left == 0:
                special_countdown = rng.randint(p["special_freq"] - 1, p["special_freq"] + 3)
        else:
            special_countdown -= 1
            if special_countdown <= 0:
                special_weeks_left = rng.randint(1, 2)

        rows.append({
            "week": w,
            "price": max(price, 0.10),
            "regular_price": max(regular_price, 0.10),
            "is_on_special": int(is_special),
        })
    return rows


def generate_and_save(db_path: str = DB_PATH) -> pd.DataFrame:
    random.seed(SEED)

    conn = sqlite3.connect(db_path)
    products = pd.read_sql(
        """
        SELECT product_id, name, category, price, source, brand, unit_size
        FROM products
        WHERE scraped_at = (SELECT MAX(scraped_at) FROM products)
        """,
        conn,
    )
    logger.info(f"Generating {WEEKS}-week history for {len(products):,} products")

    end_date = date.today()
    start_date = end_date - timedelta(weeks=WEEKS - 1)
    week_dates = [start_date + timedelta(weeks=w) for w in range(WEEKS)]

    records = []
    for _, row in products.iterrows():
        seed = abs(hash(row["product_id"])) % (2 ** 31)
        series = _generate_series(float(row["price"]), row["category"], seed)
        for entry in series:
            records.append({
                "product_id":    row["product_id"],
                "name":          row["name"],
                "brand":         row["brand"],
                "source":        row["source"],
                "category":      row["category"],
                "unit_size":     row["unit_size"],
                "week_date":     week_dates[entry["week"]].isoformat(),
                "price":         entry["price"],
                "regular_price": entry["regular_price"],
                "is_on_special": entry["is_on_special"],
            })

    df = pd.DataFrame(records)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS price_history_weekly (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id     TEXT NOT NULL,
            name           TEXT,
            brand          TEXT,
            source         TEXT,
            category       TEXT,
            unit_size      TEXT,
            week_date      TEXT NOT NULL,
            price          REAL NOT NULL,
            regular_price  REAL NOT NULL,
            is_on_special  INTEGER DEFAULT 0
        )
    """)
    conn.execute("DELETE FROM price_history_weekly")
    df.to_sql("price_history_weekly", conn, if_exists="append", index=False)
    conn.commit()
    conn.close()

    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
    df.to_csv(CSV_PATH, index=False)

    total_specials = df["is_on_special"].sum()
    print(f"\n{'='*55}")
    print(f"  Products       : {len(products):,}")
    print(f"  Weeks          : {WEEKS}")
    print(f"  Total records  : {len(df):,}")
    print(f"  Date range     : {week_dates[0]}  →  {week_dates[-1]}")
    print(f"  Special events : {total_specials:,}  ({100*total_specials/len(df):.1f}%)")
    print(f"  Saved to       : {CSV_PATH}")
    print(f"{'='*55}\n")
    return df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
    generate_and_save()
