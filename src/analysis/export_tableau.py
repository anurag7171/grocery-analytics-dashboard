"""Export clean CSVs for Tableau Public visualisations."""

import os
import sqlite3
import pandas as pd

DB_PATH    = os.path.join(os.path.dirname(__file__), "..", "..", "data", "retail.db")
EXPORT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "tableau")
os.makedirs(EXPORT_DIR, exist_ok=True)


def export_all(db_path: str = DB_PATH):
    conn = sqlite3.connect(db_path)

    # 1. Product snapshot — for price comparison & category charts
    products = pd.read_sql(
        "SELECT * FROM products WHERE scraped_at=(SELECT MAX(scraped_at) FROM products)", conn
    )
    products["brand_type"] = products["brand"].apply(
        lambda b: "Own Brand"
        if pd.isna(b) or any(x in str(b).lower() for x in ["woolworths", "macro", "w select"])
        else "National Brand"
    )
    products.to_csv(f"{EXPORT_DIR}/products_snapshot.csv", index=False)
    print(f"products_snapshot.csv — {len(products):,} rows")

    # 2. Weekly category averages — for trend line charts
    weekly_avg = pd.read_sql("""
        SELECT category, week_date,
               ROUND(AVG(price),2)         AS avg_price,
               ROUND(AVG(regular_price),2) AS avg_regular_price,
               SUM(is_on_special)          AS specials_count,
               COUNT(*)                    AS product_count,
               ROUND(100.0*SUM(is_on_special)/COUNT(*),1) AS special_pct
        FROM price_history_weekly
        GROUP BY category, week_date
        ORDER BY category, week_date
    """, conn)
    weekly_avg.to_csv(f"{EXPORT_DIR}/weekly_category_avg.csv", index=False)
    print(f"weekly_category_avg.csv — {len(weekly_avg):,} rows")

    # 3. Brand comparison — for grouped bar charts
    brand_comp = pd.read_sql("""
        SELECT category, brand_type,
               COUNT(*)             AS product_count,
               ROUND(AVG(price),2)  AS avg_price,
               ROUND(AVG(CASE WHEN is_on_special=1 THEN discount_pct END),1) AS avg_discount,
               ROUND(100.0*SUM(is_on_special)/COUNT(*),1) AS special_pct
        FROM (
            SELECT *,
                CASE WHEN LOWER(COALESCE(brand,'')) LIKE '%woolworths%'
                          OR LOWER(COALESCE(brand,'')) LIKE '%macro%'
                          OR brand IS NULL
                     THEN 'Own Brand' ELSE 'National Brand' END AS brand_type
            FROM products
            WHERE scraped_at=(SELECT MAX(scraped_at) FROM products)
        )
        GROUP BY category, brand_type
        ORDER BY category, brand_type
    """, conn)
    brand_comp.to_csv(f"{EXPORT_DIR}/brand_comparison.csv", index=False)
    print(f"brand_comparison.csv — {len(brand_comp):,} rows")

    # 4. Category KPI summary — for KPI cards / treemap
    kpi = pd.read_sql("""
        SELECT category,
               COUNT(*)                                   AS product_count,
               ROUND(AVG(price),2)                        AS avg_price,
               ROUND(MIN(price),2)                        AS min_price,
               ROUND(MAX(price),2)                        AS max_price,
               ROUND(100.0*SUM(is_on_special)/COUNT(*),1) AS special_pct,
               ROUND(AVG(CASE WHEN is_on_special=1 THEN discount_pct END),1) AS avg_discount_pct
        FROM products
        WHERE scraped_at=(SELECT MAX(scraped_at) FROM products)
        GROUP BY category
        ORDER BY avg_price DESC
    """, conn)
    kpi.to_csv(f"{EXPORT_DIR}/category_kpi.csv", index=False)
    print(f"category_kpi.csv — {len(kpi):,} rows")

    conn.close()
    print(f"\n✅  All Tableau CSVs saved to {EXPORT_DIR}")


if __name__ == "__main__":
    export_all()
