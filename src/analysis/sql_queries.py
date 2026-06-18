"""Pre-defined SQL business queries with pandas execution layer."""

import sqlite3
import pandas as pd


def run(conn: sqlite3.Connection, sql: str, **kwargs) -> pd.DataFrame:
    return pd.read_sql(sql, conn, params=kwargs or None)


# ── Snapshot queries (current prices) ─────────────────────────────────────────

KPI_SUMMARY = """
SELECT
    COUNT(*)                                              AS total_products,
    ROUND(AVG(price), 2)                                  AS avg_price,
    ROUND(MIN(price), 2)                                  AS min_price,
    ROUND(MAX(price), 2)                                  AS max_price,
    SUM(is_on_special)                                    AS on_special_count,
    ROUND(100.0 * SUM(is_on_special) / COUNT(*), 1)       AS special_pct,
    COUNT(DISTINCT category)                              AS categories,
    COUNT(DISTINCT brand)                                 AS brands
FROM products
WHERE scraped_at = (SELECT MAX(scraped_at) FROM products);
"""

CATEGORY_SUMMARY = """
SELECT
    category,
    COUNT(*)                                              AS product_count,
    ROUND(AVG(price), 2)                                  AS avg_price,
    ROUND(MIN(price), 2)                                  AS min_price,
    ROUND(MAX(price), 2)                                  AS max_price,
    ROUND(AVG(CASE WHEN is_on_special=1 THEN discount_pct END), 1)
                                                          AS avg_discount_pct,
    ROUND(100.0 * SUM(is_on_special) / COUNT(*), 1)       AS special_pct
FROM products
WHERE scraped_at = (SELECT MAX(scraped_at) FROM products)
GROUP BY category
ORDER BY avg_price DESC;
"""

TOP_DISCOUNTED = """
SELECT
    name, brand, category,
    price, was_price,
    discount_pct,
    unit_size
FROM products
WHERE is_on_special = 1
  AND scraped_at = (SELECT MAX(scraped_at) FROM products)
ORDER BY discount_pct DESC
LIMIT 25;
"""

BEST_UNIT_VALUE = """
SELECT
    name, brand, category,
    price, cup_price, cup_measure, unit_size
FROM products
WHERE cup_price IS NOT NULL
  AND scraped_at = (SELECT MAX(scraped_at) FROM products)
ORDER BY cup_price ASC
LIMIT 25;
"""

BRAND_VS_OWNBRAND = """
SELECT
    category,
    CASE
        WHEN LOWER(COALESCE(brand,'')) LIKE '%woolworths%'
          OR LOWER(COALESCE(brand,'')) LIKE '%macro%'
          OR LOWER(COALESCE(brand,'')) LIKE '%w select%'
          OR brand IS NULL
        THEN 'Own Brand'
        ELSE 'National Brand'
    END                                                    AS brand_type,
    COUNT(*)                                               AS product_count,
    ROUND(AVG(price), 2)                                   AS avg_price,
    ROUND(100.0 * SUM(is_on_special) / COUNT(*), 1)        AS special_pct
FROM products
WHERE scraped_at = (SELECT MAX(scraped_at) FROM products)
GROUP BY category, brand_type
ORDER BY category, brand_type;
"""

PRICE_BUCKETS = """
SELECT
    category,
    SUM(CASE WHEN price < 2              THEN 1 ELSE 0 END) AS under_2,
    SUM(CASE WHEN price BETWEEN 2 AND 5  THEN 1 ELSE 0 END) AS btw_2_5,
    SUM(CASE WHEN price BETWEEN 5 AND 10 THEN 1 ELSE 0 END) AS btw_5_10,
    SUM(CASE WHEN price BETWEEN 10 AND 20 THEN 1 ELSE 0 END) AS btw_10_20,
    SUM(CASE WHEN price > 20             THEN 1 ELSE 0 END) AS over_20
FROM products
WHERE scraped_at = (SELECT MAX(scraped_at) FROM products)
GROUP BY category
ORDER BY category;
"""

TOP_BRANDS_BY_CATEGORY = """
SELECT
    category, brand,
    COUNT(*)              AS product_count,
    ROUND(AVG(price), 2)  AS avg_price
FROM products
WHERE brand IS NOT NULL
  AND scraped_at = (SELECT MAX(scraped_at) FROM products)
GROUP BY category, brand
HAVING COUNT(*) >= 3
ORDER BY category, product_count DESC;
"""

SPECIAL_RATE_BY_CATEGORY = """
SELECT
    category,
    COUNT(*)                                         AS total,
    SUM(is_on_special)                               AS on_special,
    ROUND(100.0*SUM(is_on_special)/COUNT(*), 1)      AS special_pct,
    ROUND(AVG(CASE WHEN is_on_special=1 THEN discount_pct END), 1) AS avg_discount
FROM products
WHERE scraped_at = (SELECT MAX(scraped_at) FROM products)
GROUP BY category
ORDER BY special_pct DESC;
"""

# ── History queries (52-week synthetic) ───────────────────────────────────────

CATEGORY_WEEKLY_AVG = """
SELECT
    category,
    week_date,
    ROUND(AVG(price), 2)          AS avg_price,
    ROUND(AVG(regular_price), 2)  AS avg_regular,
    SUM(is_on_special)            AS specials_count
FROM price_history_weekly
GROUP BY category, week_date
ORDER BY category, week_date;
"""

PRODUCT_PRICE_TREND = """
SELECT
    product_id, name, category, week_date,
    price, regular_price, is_on_special
FROM price_history_weekly
WHERE product_id = :product_id
ORDER BY week_date;
"""

PRICE_VOLATILITY = """
SELECT
    p.product_id,
    p.name,
    p.category,
    p.price               AS current_price,
    ROUND(h.avg_price,2)  AS hist_avg_price,
    ROUND(h.price_std,2)  AS price_std,
    ROUND(100.0*h.price_std/h.avg_price,1) AS coeff_variation_pct
FROM products p
JOIN (
    SELECT product_id,
           AVG(price)                         AS avg_price,
           SQRT(AVG(price*price)-AVG(price)*AVG(price)) AS price_std
    FROM price_history_weekly
    GROUP BY product_id
) h ON p.product_id = h.product_id
WHERE scraped_at = (SELECT MAX(scraped_at) FROM products)
ORDER BY coeff_variation_pct DESC
LIMIT 30;
"""

WEEKLY_SPECIAL_RATE = """
SELECT
    week_date,
    category,
    ROUND(100.0*SUM(is_on_special)/COUNT(*),1) AS special_pct
FROM price_history_weekly
GROUP BY week_date, category
ORDER BY week_date, category;
"""


def load_all(db_path: str) -> dict:
    conn = sqlite3.connect(db_path)
    data = {
        "kpi":            pd.read_sql(KPI_SUMMARY, conn),
        "category":       pd.read_sql(CATEGORY_SUMMARY, conn),
        "top_discounted": pd.read_sql(TOP_DISCOUNTED, conn),
        "best_value":     pd.read_sql(BEST_UNIT_VALUE, conn),
        "brand_own":      pd.read_sql(BRAND_VS_OWNBRAND, conn),
        "buckets":        pd.read_sql(PRICE_BUCKETS, conn),
        "top_brands":     pd.read_sql(TOP_BRANDS_BY_CATEGORY, conn),
        "special_rate":   pd.read_sql(SPECIAL_RATE_BY_CATEGORY, conn),
        "weekly_avg":     pd.read_sql(CATEGORY_WEEKLY_AVG, conn),
        "volatility":     pd.read_sql(PRICE_VOLATILITY, conn),
        "weekly_specials":pd.read_sql(WEEKLY_SPECIAL_RATE, conn),
        "products":       pd.read_sql("SELECT * FROM products WHERE scraped_at=(SELECT MAX(scraped_at) FROM products)", conn),
    }
    conn.close()
    return data
