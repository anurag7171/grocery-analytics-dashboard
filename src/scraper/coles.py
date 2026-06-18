"""Scraper for Coles online grocery catalogue using Next.js data endpoints."""

import re
import time
import random
import logging
from typing import List, Dict, Optional

import requests

logger = logging.getLogger(__name__)

CATEGORIES = [
    {"name": "Fruit & Veg",     "slug": "fruit-vegetables"},
    {"name": "Meat & Seafood",  "slug": "meat-seafood"},
    {"name": "Dairy & Eggs",    "slug": "dairy-eggs-fridge"},
    {"name": "Bakery",          "slug": "bakery"},
    {"name": "Pantry",          "slug": "pantry"},
    {"name": "Snacks",          "slug": "snacks-confectionery"},
    {"name": "Drinks",          "slug": "drinks"},
    {"name": "Frozen",          "slug": "frozen"},
    {"name": "Health & Beauty", "slug": "health-beauty"},
    {"name": "Household",       "slug": "household"},
]

BASE_URL = "https://www.coles.com.au"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-AU,en;q=0.9",
}


def _get_build_id(session: requests.Session) -> Optional[str]:
    try:
        r = session.get(
            f"{BASE_URL}/browse/fruit-vegetables",
            headers={**HEADERS, "Accept": "text/html,application/xhtml+xml"},
            timeout=15,
        )
        match = re.search(r'"buildId":"([^"]+)"', r.text)
        if match:
            return match.group(1)
    except Exception as e:
        logger.warning(f"Failed to get Coles build ID: {e}")
    return None


def _parse_product(raw: dict, category: str) -> Optional[Dict]:
    try:
        if raw.get("_type") != "PRODUCT":
            return None

        pricing = raw.get("pricing", {})
        price = pricing.get("now")
        if price is None or float(price) == 0:
            return None

        was_price = pricing.get("was") or 0
        is_special = bool(pricing.get("onlineSpecial", False)) or (was_price and float(was_price) > float(price))
        if not is_special:
            was_price = price
        discount_pct = (
            round((float(was_price) - float(price)) / float(was_price) * 100, 1)
            if is_special and float(was_price) > 0 else 0.0
        )

        unit_info = pricing.get("unit", {})
        cup_price = unit_info.get("price")
        cup_measure = unit_info.get("ofMeasureType")

        return {
            "source": "coles",
            "product_id": f"co_{raw.get('id', '')}",
            "name": raw.get("name", "").strip(),
            "brand": (raw.get("brand") or "").strip() or None,
            "category": category,
            "price": float(price),
            "was_price": float(was_price) if was_price else float(price),
            "is_on_special": is_special,
            "discount_pct": discount_pct,
            "unit_size": raw.get("size") or None,
            "cup_price": float(cup_price) if cup_price else None,
            "cup_measure": cup_measure,
            "avg_rating": None,
            "review_count": 0,
        }
    except Exception as e:
        logger.debug(f"Failed to parse Coles product: {e}")
        return None


def scrape_category(
    session: requests.Session,
    build_id: str,
    category_name: str,
    slug: str,
    max_pages: int = 5,
) -> List[Dict]:
    products = []
    json_headers = {**HEADERS, "Accept": "application/json"}

    for page in range(1, max_pages + 1):
        url = f"{BASE_URL}/_next/data/{build_id}/en/browse/{slug}.json"
        params = {"slug": ["browse", slug], "page": page}

        try:
            resp = session.get(url, params=params, headers=json_headers, timeout=20)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning(f"Coles page {page} failed for {category_name}: {e}")
            break

        search = data.get("pageProps", {}).get("searchResults", {})
        results = search.get("results", [])
        if not results:
            break

        page_products = []
        for raw in results:
            parsed = _parse_product(raw, category_name)
            if parsed:
                page_products.append(parsed)

        products.extend(page_products)

        total = search.get("noOfResults", 0)
        page_size = search.get("pageSize", 48)
        logger.info(
            f"  Coles | {category_name:<20} | page {page}/{-(-total // page_size)} "
            f"→ {len(page_products)} products (running total: {len(products)})"
        )

        if page * page_size >= total:
            break

        time.sleep(random.uniform(1.5, 3.0))

    return products


def scrape_all(max_pages_per_category: int = 5) -> List[Dict]:
    session = requests.Session()

    build_id = _get_build_id(session)
    if not build_id:
        logger.error("Could not get Coles build ID — skipping Coles scrape.")
        return []

    logger.info(f"Coles build ID: {build_id}")
    time.sleep(random.uniform(1.0, 2.0))

    all_products = []
    for cat in CATEGORIES:
        logger.info(f"Scraping Coles: {cat['name']}")
        products = scrape_category(
            session, build_id, cat["name"], cat["slug"],
            max_pages=max_pages_per_category,
        )
        all_products.extend(products)
        time.sleep(random.uniform(2.0, 4.0))

    logger.info(f"Coles total: {len(all_products)} products")
    return all_products
