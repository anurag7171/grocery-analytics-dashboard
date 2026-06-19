"""
Exploratory Data Analysis for the Australian Grocery dataset.

Covers:
- Statistical summary by category
- Price distribution & outlier detection
- On-special patterns
- Brand vs own-brand analysis
- Unit price analysis
- Price correlation across categories
- Weekly trend analysis
- Saves all figures to results/figures/
"""

import os
import sqlite3
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import seaborn as sns
from scipy import stats

DB_PATH    = os.path.join(os.path.dirname(__file__), "..", "..", "data", "retail.db")
FIG_DIR    = os.path.join(os.path.dirname(__file__), "..", "..", "results", "figures")
REPORT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "results")

PALETTE = sns.color_palette("Set2", 10)
sns.set_theme(style="whitegrid", palette="Set2", font_scale=1.05)
os.makedirs(FIG_DIR, exist_ok=True)


# ── Load data ──────────────────────────────────────────────────────────────────
def load(db_path: str = DB_PATH):
    conn = sqlite3.connect(db_path)
    products = pd.read_sql(
        "SELECT * FROM products WHERE scraped_at=(SELECT MAX(scraped_at) FROM products)", conn
    )
    history = pd.read_sql("SELECT * FROM price_history_weekly", conn)
    conn.close()
    history["week_date"] = pd.to_datetime(history["week_date"])
    products["brand_type"] = products["brand"].apply(
        lambda b: "Own Brand"
        if pd.isna(b) or any(x in str(b).lower() for x in ["woolworths", "macro", "w select"])
        else "National Brand"
    )
    return products, history


def savefig(name: str):
    path = os.path.join(FIG_DIR, f"{name}.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved → {path}")


# ── 1. Statistical summary ─────────────────────────────────────────────────────
def statistical_summary(df: pd.DataFrame) -> pd.DataFrame:
    summary = df.groupby("category")["price"].agg(
        count="count",
        mean="mean",
        median="median",
        std="std",
        min="min",
        max="max",
        q25=lambda x: x.quantile(0.25),
        q75=lambda x: x.quantile(0.75),
    ).round(2)
    summary["iqr"]  = summary["q75"] - summary["q25"]
    summary["cv_%"] = (summary["std"] / summary["mean"] * 100).round(1)
    print("\n── Statistical Summary by Category ──")
    print(summary.to_string())
    path = os.path.join(REPORT_DIR, "statistical_summary.csv")
    summary.to_csv(path)
    print(f"  Saved → {path}")
    return summary


# ── 2. Price distributions ─────────────────────────────────────────────────────
def plot_price_distributions(df: pd.DataFrame):
    categories = sorted(df["category"].unique())
    fig, axes = plt.subplots(2, 5, figsize=(20, 8))
    axes = axes.flatten()

    for i, cat in enumerate(categories):
        data = df[df["category"] == cat]["price"]
        axes[i].hist(data, bins=25, color=PALETTE[i], edgecolor="white", alpha=0.85)
        axes[i].axvline(data.median(), color="#ef4444", linestyle="--", linewidth=1.5, label=f"Median ${data.median():.2f}")
        axes[i].axvline(data.mean(), color="#3b82f6", linestyle=":", linewidth=1.5, label=f"Mean ${data.mean():.2f}")
        axes[i].set_title(cat, fontweight="bold", fontsize=10)
        axes[i].set_xlabel("Price ($)")
        axes[i].set_ylabel("Products")
        axes[i].legend(fontsize=7)
        axes[i].xaxis.set_major_formatter(mticker.FormatStrFormatter("$%.0f"))

    plt.suptitle("Price Distribution by Category", fontsize=14, fontweight="bold", y=1.01)
    plt.tight_layout()
    savefig("01_price_distributions")


# ── 3. Box plots — price spread per category ───────────────────────────────────
def plot_price_boxplot(df: pd.DataFrame):
    fig, ax = plt.subplots(figsize=(14, 6))
    order = df.groupby("category")["price"].median().sort_values().index
    sns.boxplot(data=df, x="category", y="price", order=order,
                palette="Set2", flierprops=dict(marker="o", markersize=3, alpha=0.4), ax=ax)
    ax.set_xticklabels(ax.get_xticklabels(), rotation=25, ha="right")
    ax.set_xlabel("")
    ax.set_ylabel("Price ($)")
    ax.set_title("Price Spread by Category (Median Sorted)", fontweight="bold")
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("$%.0f"))
    plt.tight_layout()
    savefig("02_price_boxplot")


# ── 4. Outlier detection (IQR method) ─────────────────────────────────────────
def detect_outliers(df: pd.DataFrame) -> pd.DataFrame:
    outliers = []
    for cat, group in df.groupby("category"):
        q1, q3 = group["price"].quantile([0.25, 0.75])
        iqr = q3 - q1
        mask = (group["price"] < q1 - 1.5 * iqr) | (group["price"] > q3 + 1.5 * iqr)
        out = group[mask][["name", "brand", "category", "price"]].copy()
        out["q1"], out["q3"], out["iqr"] = q1, q3, iqr
        outliers.append(out)

    outlier_df = pd.concat(outliers, ignore_index=True)
    print(f"\n── Outliers detected: {len(outlier_df)} products ──")

    fig, ax = plt.subplots(figsize=(10, 5))
    outlier_counts = outlier_df["category"].value_counts()
    outlier_counts.plot(kind="bar", color=PALETTE, ax=ax, edgecolor="white")
    ax.set_title("Outlier Count by Category (IQR method)", fontweight="bold")
    ax.set_xlabel("")
    ax.set_ylabel("# Outliers")
    ax.set_xticklabels(ax.get_xticklabels(), rotation=25, ha="right")
    plt.tight_layout()
    savefig("03_outliers_by_category")

    path = os.path.join(REPORT_DIR, "outliers.csv")
    outlier_df.to_csv(path, index=False)
    print(f"  Saved → {path}")
    return outlier_df


# ── 5. On-special analysis ─────────────────────────────────────────────────────
def plot_specials_analysis(df: pd.DataFrame):
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))

    # Special rate per category
    special_rate = df.groupby("category")["is_on_special"].mean().mul(100).sort_values(ascending=False)
    special_rate.plot(kind="bar", ax=axes[0], color=PALETTE, edgecolor="white")
    axes[0].set_title("% Products On Special", fontweight="bold")
    axes[0].set_ylabel("%")
    axes[0].set_xticklabels(axes[0].get_xticklabels(), rotation=30, ha="right")

    # Average discount depth
    discount = df[df["is_on_special"] == 1].groupby("category")["discount_pct"].mean().sort_values(ascending=False)
    discount.plot(kind="bar", ax=axes[1], color=PALETTE, edgecolor="white")
    axes[1].set_title("Avg Discount % (On Special Items)", fontweight="bold")
    axes[1].set_ylabel("Discount %")
    axes[1].set_xticklabels(axes[1].get_xticklabels(), rotation=30, ha="right")

    # Discount distribution
    df_special = df[df["is_on_special"] == 1]["discount_pct"]
    axes[2].hist(df_special, bins=20, color="#16a34a", edgecolor="white", alpha=0.85)
    axes[2].axvline(df_special.mean(), color="#ef4444", linestyle="--", linewidth=2, label=f"Mean {df_special.mean():.1f}%")
    axes[2].set_title("Distribution of Discount Sizes", fontweight="bold")
    axes[2].set_xlabel("Discount %")
    axes[2].set_ylabel("Products")
    axes[2].legend()

    plt.suptitle("On-Special Analysis", fontsize=14, fontweight="bold")
    plt.tight_layout()
    savefig("04_specials_analysis")


# ── 6. Brand vs own-brand ──────────────────────────────────────────────────────
def plot_brand_vs_ownbrand(df: pd.DataFrame):
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))

    brand_cat = df.groupby(["category", "brand_type"])["price"].mean().unstack("brand_type")
    brand_cat.plot(kind="bar", ax=axes[0], color=["#16a34a", "#0ea5e9"], edgecolor="white", width=0.7)
    axes[0].set_title("Own Brand vs National Brand — Avg Price", fontweight="bold")
    axes[0].set_ylabel("Avg Price ($)")
    axes[0].set_xlabel("")
    axes[0].set_xticklabels(axes[0].get_xticklabels(), rotation=30, ha="right")
    axes[0].legend(title="")
    axes[0].yaxis.set_major_formatter(mticker.FormatStrFormatter("$%.2f"))

    savings = (brand_cat["National Brand"] - brand_cat.get("Own Brand", brand_cat["National Brand"])).dropna()
    savings_pct = (savings / brand_cat["National Brand"] * 100).sort_values(ascending=False)
    colors = ["#16a34a" if v >= 0 else "#ef4444" for v in savings_pct]
    savings_pct.plot(kind="bar", ax=axes[1], color=colors, edgecolor="white")
    axes[1].set_title("Avg Savings by Choosing Own Brand (%)", fontweight="bold")
    axes[1].set_ylabel("Savings %")
    axes[1].set_xlabel("")
    axes[1].set_xticklabels(axes[1].get_xticklabels(), rotation=30, ha="right")
    axes[1].axhline(0, color="black", linewidth=0.8)

    plt.suptitle("Brand Analysis", fontsize=14, fontweight="bold")
    plt.tight_layout()
    savefig("05_brand_vs_ownbrand")


# ── 7. Unit price (best value) analysis ───────────────────────────────────────
def plot_unit_price_analysis(df: pd.DataFrame):
    has_cup = df.dropna(subset=["cup_price"])
    if has_cup.empty:
        return

    fig, axes = plt.subplots(1, 2, figsize=(16, 6))

    cup_by_cat = has_cup.groupby("category")["cup_price"].median().sort_values()
    cup_by_cat.plot(kind="barh", ax=axes[0], color=PALETTE, edgecolor="white")
    axes[0].set_title("Median Unit Price by Category ($/100g or /100ml)", fontweight="bold")
    axes[0].set_xlabel("Median Unit Price ($)")

    top_value = has_cup.nsmallest(15, "cup_price")[["name", "category", "cup_price"]]
    colors = [PALETTE[sorted(has_cup["category"].unique().tolist()).index(c) % len(PALETTE)]
              for c in top_value["category"]]
    axes[1].barh(top_value["name"], top_value["cup_price"], color=colors, edgecolor="white")
    axes[1].set_title("Top 15 Best Unit Value Products", fontweight="bold")
    axes[1].set_xlabel("Unit Price ($)")

    plt.suptitle("Unit Price Analysis", fontsize=14, fontweight="bold")
    plt.tight_layout()
    savefig("06_unit_price_analysis")


# ── 8. Price correlation heatmap across categories ─────────────────────────────
def plot_correlation_heatmap(df: pd.DataFrame):
    pivot = df.groupby("category")["price"].apply(list)
    min_len = min(len(v) for v in pivot)
    corr_data = pd.DataFrame({cat: vals[:min_len] for cat, vals in pivot.items()})
    corr = corr_data.corr()

    fig, ax = plt.subplots(figsize=(11, 9))
    mask = np.triu(np.ones_like(corr, dtype=bool))
    sns.heatmap(corr, mask=mask, annot=True, fmt=".2f", cmap="RdYlGn",
                vmin=-1, vmax=1, square=True, linewidths=0.5,
                cbar_kws={"shrink": 0.75}, ax=ax)
    ax.set_title("Price Correlation Between Categories\n(do high-priced categories co-move?)",
                 fontweight="bold", pad=15)
    plt.tight_layout()
    savefig("07_price_correlation_heatmap")


# ── 9. Weekly price trends by category ────────────────────────────────────────
def plot_weekly_trends(history: pd.DataFrame):
    weekly = history.groupby(["category", "week_date"])["price"].mean().reset_index()

    fig, ax = plt.subplots(figsize=(15, 6))
    cats = sorted(weekly["category"].unique())
    for i, cat in enumerate(cats):
        cat_data = weekly[weekly["category"] == cat].sort_values("week_date")
        ax.plot(cat_data["week_date"], cat_data["price"],
                label=cat, color=PALETTE[i % len(PALETTE)], linewidth=1.8, alpha=0.85)

    ax.set_title("52-Week Average Price Trend by Category", fontweight="bold")
    ax.set_xlabel("Week")
    ax.set_ylabel("Avg Price ($)")
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("$%.2f"))
    ax.legend(loc="upper left", fontsize=8, ncol=2)
    plt.tight_layout()
    savefig("08_weekly_price_trends")


# ── 10. Seasonality — special rate over time ───────────────────────────────────
def plot_special_rate_over_time(history: pd.DataFrame):
    weekly = history.groupby(["category", "week_date"])["is_on_special"].mean().mul(100).reset_index()

    fig, ax = plt.subplots(figsize=(15, 6))
    cats = sorted(weekly["category"].unique())
    for i, cat in enumerate(cats):
        cat_data = weekly[weekly["category"] == cat].sort_values("week_date")
        # Smooth with 4-week rolling average
        cat_data = cat_data.set_index("week_date")
        cat_data["smoothed"] = cat_data["is_on_special"].rolling(4, center=True).mean()
        ax.plot(cat_data.index, cat_data["smoothed"],
                label=cat, color=PALETTE[i % len(PALETTE)], linewidth=1.8, alpha=0.85)

    ax.set_title("Weekly % Products On Special (4-week rolling avg)", fontweight="bold")
    ax.set_xlabel("Week")
    ax.set_ylabel("% On Special")
    ax.legend(loc="upper right", fontsize=8, ncol=2)
    plt.tight_layout()
    savefig("09_special_rate_over_time")


# ── 11. Price volatility distribution ─────────────────────────────────────────
def plot_price_volatility(history: pd.DataFrame):
    vol = history.groupby(["product_id", "category"])["price"].std().reset_index()
    vol.columns = ["product_id", "category", "price_std"]

    fig, axes = plt.subplots(1, 2, figsize=(16, 6))

    order = vol.groupby("category")["price_std"].median().sort_values(ascending=False).index
    sns.boxplot(data=vol, x="category", y="price_std", order=order,
                palette="Set2", ax=axes[0],
                flierprops=dict(marker="o", markersize=3, alpha=0.4))
    axes[0].set_title("Price Volatility (Std Dev) by Category", fontweight="bold")
    axes[0].set_ylabel("Price Std Dev ($)")
    axes[0].set_xlabel("")
    axes[0].set_xticklabels(axes[0].get_xticklabels(), rotation=30, ha="right")

    axes[1].hist(vol["price_std"], bins=40, color="#16a34a", edgecolor="white", alpha=0.85)
    axes[1].axvline(vol["price_std"].median(), color="#ef4444", linestyle="--",
                    linewidth=2, label=f"Median ${vol['price_std'].median():.2f}")
    axes[1].set_title("Distribution of Product Price Volatility", fontweight="bold")
    axes[1].set_xlabel("Price Std Dev ($)")
    axes[1].set_ylabel("Products")
    axes[1].legend()

    plt.suptitle("Price Volatility Analysis", fontsize=14, fontweight="bold")
    plt.tight_layout()
    savefig("10_price_volatility")


# ── 12. Top brands by product count ───────────────────────────────────────────
def plot_top_brands(df: pd.DataFrame):
    top_brands = (
        df.dropna(subset=["brand"])
        .groupby("brand")
        .agg(product_count=("name", "count"), avg_price=("price", "mean"))
        .nlargest(20, "product_count")
        .reset_index()
    )

    fig, ax = plt.subplots(figsize=(12, 7))
    bars = ax.barh(top_brands["brand"], top_brands["product_count"],
                   color=sns.color_palette("Greens_d", len(top_brands)), edgecolor="white")
    for bar, price in zip(bars, top_brands["avg_price"]):
        ax.text(bar.get_width() + 0.3, bar.get_y() + bar.get_height() / 2,
                f"  avg ${price:.2f}", va="center", fontsize=8, color="#64748b")
    ax.set_title("Top 20 Brands by Number of Products", fontweight="bold")
    ax.set_xlabel("Number of Products")
    plt.tight_layout()
    savefig("11_top_brands")


# ── Master runner ──────────────────────────────────────────────────────────────
def run_full_eda(db_path: str = DB_PATH):
    print("Loading data…")
    products, history = load(db_path)
    print(f"  Products : {len(products):,}  |  History rows : {len(history):,}")

    print("\n[1/11] Statistical summary")
    statistical_summary(products)

    print("\n[2/11] Price distributions")
    plot_price_distributions(products)

    print("\n[3/11] Price boxplot")
    plot_price_boxplot(products)

    print("\n[4/11] Outlier detection")
    detect_outliers(products)

    print("\n[5/11] Specials analysis")
    plot_specials_analysis(products)

    print("\n[6/11] Brand vs own-brand")
    plot_brand_vs_ownbrand(products)

    print("\n[7/11] Unit price analysis")
    plot_unit_price_analysis(products)

    print("\n[8/11] Price correlation heatmap")
    plot_correlation_heatmap(products)

    print("\n[9/11] Weekly price trends")
    plot_weekly_trends(history)

    print("\n[10/11] Special rate over time")
    plot_special_rate_over_time(history)

    print("\n[11/11] Price volatility")
    plot_price_volatility(history)

    plot_top_brands(products)

    print(f"\n✅  EDA complete — {len(os.listdir(FIG_DIR))} figures saved to {FIG_DIR}")


if __name__ == "__main__":
    run_full_eda()
