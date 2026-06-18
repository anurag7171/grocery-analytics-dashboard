"""
Prophet-based weekly price forecasting per category.

For each grocery category, aggregates weekly average prices from the
52-week history and fits a Prophet model to forecast 8 weeks ahead.
"""

import logging
import sqlite3
import warnings
from typing import Dict

import pandas as pd

warnings.filterwarnings("ignore")
logger = logging.getLogger(__name__)


def _load_weekly_category(db_path: str) -> pd.DataFrame:
    conn = sqlite3.connect(db_path)
    df = pd.read_sql(
        """
        SELECT category, week_date, AVG(price) AS avg_price
        FROM price_history_weekly
        GROUP BY category, week_date
        ORDER BY category, week_date
        """,
        conn,
    )
    conn.close()
    df["week_date"] = pd.to_datetime(df["week_date"])
    return df


def forecast_all(db_path: str, periods: int = 8) -> Dict[str, pd.DataFrame]:
    """Return a dict of {category: forecast_df} with columns ds, yhat, yhat_lower, yhat_upper."""
    try:
        from prophet import Prophet
    except ImportError:
        logger.error("prophet not installed. Run: pip install prophet")
        return {}

    weekly = _load_weekly_category(db_path)
    results = {}

    for category in weekly["category"].unique():
        cat_df = weekly[weekly["category"] == category][["week_date", "avg_price"]].copy()
        cat_df.columns = ["ds", "y"]
        cat_df = cat_df.sort_values("ds").dropna()

        if len(cat_df) < 10:
            logger.warning(f"Not enough data for {category}, skipping.")
            continue

        try:
            model = Prophet(
                yearly_seasonality=True,
                weekly_seasonality=False,
                daily_seasonality=False,
                changepoint_prior_scale=0.05,
                seasonality_prior_scale=10,
                interval_width=0.90,
                uncertainty_samples=500,
            )
            model.fit(cat_df, iter=300)
            future = model.make_future_dataframe(periods=periods, freq="W")
            forecast = model.predict(future)
            forecast["category"] = category
            results[category] = forecast[["ds", "yhat", "yhat_lower", "yhat_upper", "trend", "category"]]
            logger.info(f"Forecast complete: {category}")
        except Exception as e:
            logger.warning(f"Forecast failed for {category}: {e}")

    return results


def forecast_df_combined(db_path: str, periods: int = 8) -> pd.DataFrame:
    forecasts = forecast_all(db_path, periods)
    if not forecasts:
        return pd.DataFrame()
    return pd.concat(forecasts.values(), ignore_index=True)
