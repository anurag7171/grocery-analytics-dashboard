"""Scraper for Woolworths online grocery catalogue."""

import json
import time
import random
import logging
from typing import List, Dict, Optional

import requests

logger = logging.getLogger(__name__)

CATEGORIES = [
    {"id": "1-E5BEE36E", "name": "Fruit & Veg",        "url": "/shop/browse/fruit-veg",          "label": "Fruit & Veg"},
    {"id": "1_D5A2236",  "name": "Meat & Seafood",      "url": "/shop/browse/poultry-meat-seafood","label": "Poultry, Meat & Seafood"},
    {"id": "1_6E4F4E4",  "name": "Dairy & Eggs",        "url": "/shop/browse/dairy-eggs-fridge",  "label": "Dairy, Eggs & Fridge"},
    {"id": "1_DEB537E",  "name": "Bakery",               "url": "/shop/browse/bakery",             "label": "Bakery"},
    {"id": "1_39FD49C",  "name": "Pantry",               "url": "/shop/browse/pantry",             "label": "Pantry"},
    {"id": "1_717445A",  "name": "Snacks",               "url": "/shop/browse/snacks-confectionery","label": "Snacks & Confectionery"},
    {"id": "1_5AF3A0A",  "name": "Drinks",               "url": "/shop/browse/drinks",             "label": "Drinks"},
    {"id": "1_ACA2FC2",  "name": "Frozen",               "url": "/shop/browse/freezer",            "label": "Freezer"},
    {"id": "1_9851658",  "name": "Health & Wellness",    "url": "/shop/browse/health-wellness",    "label": "Health & Wellness"},
    {"id": "1_2432B58",  "name": "Household",            "url": "/shop/browse/cleaning-maintenance","label": "Cleaning & Maintenance"},
]

BROWSE_URL = "https://www.woolworths.com.au/apis/ui/browse/category"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-AU,en;q=0.9",
}


def _parse_product(raw: dict, category: str) -> Optional[Dict]:
    try:
        price = raw.get("Price")
        if price is None or float(price) == 0:
            return None

        was_price = raw.get("WasPrice") or price
        is_special = bool(raw.get("IsOnSpecial", False))
        savings = raw.get("SavingsAmount") or 0
        discount_pct = round(float(savings) / float(was_price) * 100, 1) if is_special and float(was_price) > 0 else 0.0

        rating_raw = raw.get("Rating", {})
        avg_rating = None
        review_count = 0
        if isinstance(rating_raw, dict):
            avg_rating = rating_raw.get("Average") or rating_raw.get("RatingAverage")
            review_count = rating_raw.get("ReviewCount") or rating_raw.get("RatingCount") or 0
        elif isinstance(rating_raw, (int, float)) and rating_raw > 0:
            avg_rating = float(rating_raw)

        return {
            "source": "woolworths",
            "product_id": f"ww_{raw.get('Stockcode', '')}",
            "name": raw.get("Name", "").strip(),
            "brand": (raw.get("Brand") or "").strip() or None,
            "category": category,
            "price": float(price),
            "was_price": float(was_price),
            "is_on_special": is_special,
            "discount_pct": discount_pct,
            "unit_size": raw.get("PackageSize") or None,
            "cup_price": raw.get("CupPrice") or None,
            "cup_measure": raw.get("CupMeasure") or None,
            "avg_rating": float(avg_rating) if avg_rating else None,
            "review_count": int(review_count),
        }
    except Exception as e:
        logger.debug(f"Failed to parse product: {e}")
        return None


def scrape_category(
    session: requests.Session,
    cat: dict,
    page_size: int = 36,
    max_pages: int = 5,
) -> List[Dict]:
    products = []
    referer_headers = {**HEADERS, "Referer": f"https://www.woolworths.com.au{cat['url']}"}

    for page in range(1, max_pages + 1):
        params = {
            "categoryId": cat["id"],
            "pageNumber": page,
            "pageSize": page_size,
            "sortType": "TraderRelevance",
            "url": cat["url"],
            "formatObject": json.dumps({"name": cat["label"]}),
            "isMobile": "false",
            "filters": "[]",
            "token": "",
            "gpBoost": 0,
            "isHideUnavailableProducts": "false",
            "isRegisteredRewardCardPromotion": "false",
            "enableAdReRanking": "false",
        }

        try:
            resp = session.get(BROWSE_URL, params=params, headers=referer_headers, timeout=20)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning(f"Woolworths page {page} failed for {cat['name']}: {e}")
            break

        bundles = data.get("Bundles", [])
        if not bundles:
            break

        page_products = []
        for bundle in bundles:
            for raw in bundle.get("Products", [bundle]):
                parsed = _parse_product(raw, cat["name"])
                if parsed:
                    page_products.append(parsed)

        products.extend(page_products)
        total = data.get("TotalRecordCount", 0)
        logger.info(
            f"  Woolworths | {cat['name']:<20} | page {page}/{-(-total // page_size)} "
            f"→ {len(page_products)} products (running total: {len(products)})"
        )

        if page * page_size >= total:
            break

        time.sleep(random.uniform(1.5, 3.0))

    return products


def scrape_all(max_pages_per_category: int = 5) -> List[Dict]:
    session = requests.Session()
    try:
        session.get("https://www.woolworths.com.au", headers=HEADERS, timeout=15)
        time.sleep(random.uniform(1.0, 2.0))
    except Exception as e:
        logger.warning(f"Session warm-up failed: {e}")

    all_products = []
    for cat in CATEGORIES:
        logger.info(f"Scraping Woolworths: {cat['name']}")
        products = scrape_category(session, cat, max_pages=max_pages_per_category)
        all_products.extend(products)
        time.sleep(random.uniform(2.0, 4.0))

    logger.info(f"Woolworths total: {len(all_products)} products")
    return all_products
