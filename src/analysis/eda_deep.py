"""
Deep EDA — statistical testing, segmentation, and advanced insights.

Builds on eda.py with:
1.  Normality testing (Shapiro-Wilk per category)
2.  Skewness & kurtosis analysis
3.  Own-brand vs national brand t-test (statistical significance)
4.  Spearman correlation: price vs discount rate
5.  Price tier segmentation (KMeans — budget / mid / premium)
6.  Promotional cycle analysis (avg weeks between specials)
7.  Implied annual inflation rate per category (52-week OLS trend)
8.  Brand premium/discount index (brand avg vs category avg)
9.  Price elasticity proxy (discount depth vs special frequency)
10. Saves all figures + a combined insights CSV
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


def load(db_path=DB_PATH):
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


def savefig(name):
    path = os.path.join(FIG_DIR, f"{name}.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved → {path}")


# ── 1. Normality & distribution shape ─────────────────────────────────────────
def test_normality(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for cat, group in df.groupby("category"):
        prices = group["price"].dropna()
        stat, p = stats.shapiro(prices[:5000])        # Shapiro-Wilk
        skew  = float(prices.skew())
        kurt  = float(prices.kurtosis())
        rows.append({
            "category": cat,
            "n": len(prices),
            "shapiro_stat": round(stat, 4),
            "shapiro_p": round(p, 4),
            "is_normal": p > 0.05,
            "skewness": round(skew, 3),
            "kurtosis": round(kurt, 3),
            "shape": "right-skewed" if skew > 0.5 else "left-skewed" if skew < -0.5 else "symmetric",
        })
    result = pd.DataFrame(rows)

    fig, axes = plt.subplots(2, 5, figsize=(20, 8))
    axes = axes.flatten()
    cats = sorted(df["category"].unique())
    for i, cat in enumerate(cats):
        prices = df[df["category"] == cat]["price"].dropna()
        stats.probplot(prices, dist="norm", plot=axes[i])
        axes[i].set_title(cat, fontweight="bold", fontsize=9)
        axes[i].get_lines()[0].set(markersize=2, alpha=0.5)

    plt.suptitle("Q-Q Plots — Price Normality Test per Category\n(points on line = normally distributed)",
                 fontsize=13, fontweight="bold", y=1.01)
    plt.tight_layout()
    savefig("12_qq_plots_normality")

    # Skewness & kurtosis bar chart
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    result_sorted = result.sort_values("skewness", ascending=False)
    colors_skew = ["#ef4444" if s > 0 else "#3b82f6" for s in result_sorted["skewness"]]
    axes[0].bar(result_sorted["category"], result_sorted["skewness"], color=colors_skew, edgecolor="white")
    axes[0].axhline(0, color="black", linewidth=0.8)
    axes[0].axhline(0.5, color="#ef4444", linewidth=1, linestyle="--", alpha=0.5, label="Right-skew threshold")
    axes[0].axhline(-0.5, color="#3b82f6", linewidth=1, linestyle="--", alpha=0.5, label="Left-skew threshold")
    axes[0].set_title("Price Distribution Skewness by Category", fontweight="bold")
    axes[0].set_ylabel("Skewness")
    axes[0].set_xticklabels(result_sorted["category"], rotation=30, ha="right")
    axes[0].legend(fontsize=8)

    result_sorted2 = result.sort_values("kurtosis", ascending=False)
    axes[1].bar(result_sorted2["category"], result_sorted2["kurtosis"],
                color=PALETTE, edgecolor="white")
    axes[1].axhline(0, color="black", linewidth=0.8, label="Normal kurtosis = 0")
    axes[1].set_title("Excess Kurtosis by Category\n(>0 = heavy tails, <0 = light tails)", fontweight="bold")
    axes[1].set_ylabel("Excess Kurtosis")
    axes[1].set_xticklabels(result_sorted2["category"], rotation=30, ha="right")
    axes[1].legend(fontsize=8)

    plt.tight_layout()
    savefig("13_skewness_kurtosis")

    print("\n── Normality Test Results ──")
    print(result[["category", "n", "shapiro_p", "is_normal", "skewness", "kurtosis", "shape"]].to_string(index=False))
    result.to_csv(os.path.join(REPORT_DIR, "normality_test.csv"), index=False)
    return result


# ── 2. Own-brand vs national brand t-test ────────────────────────────────────
def brand_ttest(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for cat, group in df.groupby("category"):
        own    = group[group["brand_type"] == "Own Brand"]["price"].dropna()
        nation = group[group["brand_type"] == "National Brand"]["price"].dropna()
        if len(own) < 3 or len(nation) < 3:
            continue
        t, p = stats.ttest_ind(own, nation, equal_var=False)  # Welch's t-test
        cohen_d = (nation.mean() - own.mean()) / np.sqrt((own.std()**2 + nation.std()**2) / 2)
        rows.append({
            "category":     cat,
            "own_mean":     round(own.mean(), 2),
            "national_mean":round(nation.mean(), 2),
            "price_gap":    round(nation.mean() - own.mean(), 2),
            "gap_pct":      round(100 * (nation.mean() - own.mean()) / own.mean(), 1),
            "t_stat":       round(t, 3),
            "p_value":      round(p, 4),
            "significant":  p < 0.05,
            "cohens_d":     round(cohen_d, 3),
            "effect_size":  "large" if abs(cohen_d) > 0.8 else "medium" if abs(cohen_d) > 0.5 else "small",
        })

    result = pd.DataFrame(rows)

    fig, axes = plt.subplots(1, 2, figsize=(16, 6))

    colors = ["#16a34a" if s else "#94a3b8" for s in result["significant"]]
    axes[0].bar(result["category"], result["gap_pct"], color=colors, edgecolor="white")
    axes[0].axhline(0, color="black", linewidth=0.8)
    axes[0].set_title("National Brand Premium over Own Brand (%)\n(green = statistically significant, p<0.05)",
                       fontweight="bold")
    axes[0].set_ylabel("Price Premium %")
    axes[0].set_xticklabels(result["category"], rotation=30, ha="right")
    for i, (_, row) in enumerate(result.iterrows()):
        axes[0].text(i, row["gap_pct"] + 0.5, f"p={row['p_value']:.3f}", ha="center", fontsize=7, color="#64748b")

    axes[1].bar(result["category"], result["cohens_d"].abs(), color=colors, edgecolor="white")
    axes[1].axhline(0.2, linestyle="--", color="#94a3b8", linewidth=1, label="Small effect (0.2)")
    axes[1].axhline(0.5, linestyle="--", color="#f59e0b", linewidth=1, label="Medium effect (0.5)")
    axes[1].axhline(0.8, linestyle="--", color="#ef4444", linewidth=1, label="Large effect (0.8)")
    axes[1].set_title("Effect Size (Cohen's d)\nOwn Brand vs National Brand", fontweight="bold")
    axes[1].set_ylabel("|Cohen's d|")
    axes[1].set_xticklabels(result["category"], rotation=30, ha="right")
    axes[1].legend(fontsize=8)

    plt.suptitle("Statistical Significance: Own Brand vs National Brand Price Difference",
                 fontsize=13, fontweight="bold")
    plt.tight_layout()
    savefig("14_brand_ttest")

    print("\n── Own Brand vs National Brand — Welch's t-test ──")
    print(result[["category", "own_mean", "national_mean", "gap_pct", "p_value", "significant", "effect_size"]].to_string(index=False))
    result.to_csv(os.path.join(REPORT_DIR, "brand_ttest.csv"), index=False)
    return result


# ── 3. Price tier segmentation (KMeans) ───────────────────────────────────────
def price_tier_segmentation(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # Percentile-based tiers per category (more interpretable than KMeans for DA)
    def assign_tier(group):
        p33 = group["price"].quantile(0.33)
        p67 = group["price"].quantile(0.67)
        return group["price"].apply(
            lambda p: "Budget" if p <= p33 else ("Premium" if p >= p67 else "Mid-range")
        )
    df["price_tier"] = df.groupby("category", group_keys=False).apply(assign_tier)

    fig, axes = plt.subplots(1, 2, figsize=(16, 6))

    tier_order = ["Budget", "Mid-range", "Premium"]
    tier_colors = {"Budget": "#16a34a", "Mid-range": "#0ea5e9", "Premium": "#f59e0b"}

    tier_cat = df.groupby(["category", "price_tier"]).size().unstack("price_tier").fillna(0)
    tier_cat = tier_cat.reindex(columns=[t for t in tier_order if t in tier_cat.columns])
    tier_cat.plot(kind="bar", ax=axes[0], color=[tier_colors[t] for t in tier_cat.columns],
                  edgecolor="white", width=0.75)
    axes[0].set_title("Price Tier Distribution by Category", fontweight="bold")
    axes[0].set_xlabel("")
    axes[0].set_ylabel("# Products")
    axes[0].set_xticklabels(axes[0].get_xticklabels(), rotation=30, ha="right")
    axes[0].legend(title="Tier")

    for tier, color in tier_colors.items():
        subset = df[df["price_tier"] == tier]
        if subset.empty:
            continue
        axes[1].scatter(subset["price"], subset["discount_pct"],
                        c=color, alpha=0.4, s=20, label=tier)
    axes[1].set_xlabel("Price ($)")
    axes[1].set_ylabel("Discount %")
    axes[1].set_title("Price vs Discount % by Tier", fontweight="bold")
    axes[1].legend(title="Tier")

    plt.suptitle("Price Tier Segmentation (KMeans — 3 clusters)", fontsize=13, fontweight="bold")
    plt.tight_layout()
    savefig("15_price_tier_segmentation")

    summary = df.groupby("price_tier").agg(
        products=("name", "count"),
        avg_price=("price", "mean"),
        avg_discount=("discount_pct", "mean"),
        special_rate=("is_on_special", "mean"),
    ).round(2)
    print("\n── Price Tier Summary ──")
    print(summary.to_string())
    summary.to_csv(os.path.join(REPORT_DIR, "price_tiers.csv"))
    return df


# ── 4. Implied annual inflation per category (OLS on 52-week trend) ──────────
def category_inflation(history: pd.DataFrame) -> pd.DataFrame:
    weekly = history.groupby(["category", "week_date"])["price"].mean().reset_index()
    rows = []
    for cat, group in weekly.groupby("category"):
        group = group.sort_values("week_date").reset_index(drop=True)
        group["week_num"] = range(len(group))
        slope, intercept, r, p, _ = stats.linregress(group["week_num"], group["price"])
        annual_rate = slope * 52 / intercept * 100
        rows.append({
            "category":       cat,
            "start_price":    round(group["price"].iloc[0], 2),
            "end_price":      round(group["price"].iloc[-1], 2),
            "weekly_slope":   round(slope, 4),
            "r_squared":      round(r**2, 3),
            "p_value":        round(p, 4),
            "implied_annual_inflation_%": round(annual_rate, 2),
        })

    result = pd.DataFrame(rows).sort_values("implied_annual_inflation_%", ascending=False)

    fig, axes = plt.subplots(1, 2, figsize=(16, 6))

    colors = ["#ef4444" if v > 0 else "#16a34a" for v in result["implied_annual_inflation_%"]]
    axes[0].barh(result["category"], result["implied_annual_inflation_%"], color=colors, edgecolor="white")
    axes[0].axvline(0, color="black", linewidth=0.8)
    axes[0].set_title("Implied Annual Price Inflation by Category\n(from 52-week OLS trend)",
                       fontweight="bold")
    axes[0].set_xlabel("Implied Annual Inflation %")

    for cat, group in weekly.groupby("category"):
        group = group.sort_values("week_date")
        cats = sorted(weekly["category"].unique())
        idx = cats.index(cat)
        axes[1].plot(group["week_date"], group["price"],
                     label=cat, color=PALETTE[idx % len(PALETTE)],
                     linewidth=1.5, alpha=0.8)
    axes[1].set_title("Category Avg Price — 52 Weeks", fontweight="bold")
    axes[1].set_xlabel("Week")
    axes[1].set_ylabel("Avg Price ($)")
    axes[1].legend(fontsize=7, ncol=2)

    plt.suptitle("Category-Level Price Inflation Analysis", fontsize=13, fontweight="bold")
    plt.tight_layout()
    savefig("16_category_inflation")

    print("\n── Implied Annual Inflation by Category ──")
    print(result[["category", "start_price", "end_price", "implied_annual_inflation_%", "r_squared"]].to_string(index=False))
    result.to_csv(os.path.join(REPORT_DIR, "category_inflation.csv"), index=False)
    return result


# ── 5. Brand premium / discount index ─────────────────────────────────────────
def brand_premium_index(df: pd.DataFrame) -> pd.DataFrame:
    cat_avg = df.groupby("category")["price"].mean()
    brand_cat = df.dropna(subset=["brand"]).groupby(["brand", "category"])["price"].mean().reset_index()
    brand_cat["cat_avg"] = brand_cat["category"].map(cat_avg)
    brand_cat["premium_pct"] = (brand_cat["price"] - brand_cat["cat_avg"]) / brand_cat["cat_avg"] * 100

    top_premium  = brand_cat.nlargest(15, "premium_pct")[["brand", "category", "price", "premium_pct"]]
    top_discount = brand_cat.nsmallest(15, "premium_pct")[["brand", "category", "price", "premium_pct"]]

    fig, axes = plt.subplots(1, 2, figsize=(18, 7))

    axes[0].barh(top_premium["brand"] + " (" + top_premium["category"] + ")",
                 top_premium["premium_pct"], color="#ef4444", edgecolor="white", alpha=0.85)
    axes[0].set_title("Top 15 Most Expensive Brands\n(% above category avg)", fontweight="bold")
    axes[0].set_xlabel("Premium %")
    axes[0].axvline(0, color="black", linewidth=0.8)

    axes[1].barh(top_discount["brand"] + " (" + top_discount["category"] + ")",
                 top_discount["premium_pct"].abs(), color="#16a34a", edgecolor="white", alpha=0.85)
    axes[1].set_title("Top 15 Best Value Brands\n(% below category avg)", fontweight="bold")
    axes[1].set_xlabel("Discount vs Category Avg %")

    plt.suptitle("Brand Premium / Discount Index", fontsize=13, fontweight="bold")
    plt.tight_layout()
    savefig("17_brand_premium_index")

    brand_cat.to_csv(os.path.join(REPORT_DIR, "brand_premium_index.csv"), index=False)
    return brand_cat


# ── 6. Promotional cycle analysis ─────────────────────────────────────────────
def promotional_cycle(history: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for pid, group in history.groupby("product_id"):
        group = group.sort_values("week_date")
        special_weeks = group[group["is_on_special"] == 1]["week_date"].tolist()
        if len(special_weeks) < 2:
            continue
        gaps = [(special_weeks[i+1] - special_weeks[i]).days / 7
                for i in range(len(special_weeks) - 1)]
        rows.append({
            "product_id":       pid,
            "category":         group["category"].iloc[0],
            "num_specials":     len(special_weeks),
            "avg_weeks_between":round(np.mean(gaps), 1),
            "min_gap_weeks":    round(min(gaps), 1),
            "max_gap_weeks":    round(max(gaps), 1),
        })

    result = pd.DataFrame(rows)
    by_cat = result.groupby("category").agg(
        avg_specials_per_year=("num_specials", "mean"),
        avg_weeks_between=("avg_weeks_between", "mean"),
    ).round(1)

    fig, axes = plt.subplots(1, 2, figsize=(16, 6))

    by_cat["avg_specials_per_year"].sort_values(ascending=False).plot(
        kind="bar", ax=axes[0], color=PALETTE, edgecolor="white")
    axes[0].set_title("Avg Number of Promotional Events per Product per Year", fontweight="bold")
    axes[0].set_ylabel("Specials / Year")
    axes[0].set_xticklabels(axes[0].get_xticklabels(), rotation=30, ha="right")

    by_cat["avg_weeks_between"].sort_values().plot(
        kind="bar", ax=axes[1], color=PALETTE, edgecolor="white")
    axes[1].set_title("Avg Weeks Between Promotions per Category", fontweight="bold")
    axes[1].set_ylabel("Weeks")
    axes[1].set_xticklabels(axes[1].get_xticklabels(), rotation=30, ha="right")

    plt.suptitle("Promotional Cycle Analysis", fontsize=13, fontweight="bold")
    plt.tight_layout()
    savefig("18_promotional_cycles")

    print("\n── Promotional Cycle by Category ──")
    print(by_cat.to_string())
    by_cat.to_csv(os.path.join(REPORT_DIR, "promotional_cycles.csv"))
    return result


# ── 7. Spearman correlation: price vs discount rate ───────────────────────────
def price_vs_discount_correlation(df: pd.DataFrame):
    rows = []
    for cat, group in df.groupby("category"):
        specials = group[group["is_on_special"] == 1]
        if len(specials) < 5:
            continue
        rho, p = stats.spearmanr(specials["price"], specials["discount_pct"])
        rows.append({"category": cat, "spearman_rho": round(rho, 3), "p_value": round(p, 4),
                     "significant": p < 0.05})

    result = pd.DataFrame(rows)

    fig, axes = plt.subplots(2, 5, figsize=(20, 9))
    axes = axes.flatten()
    cats = sorted(df["category"].unique())
    for i, cat in enumerate(cats):
        specials = df[(df["category"] == cat) & (df["is_on_special"] == 1)]
        axes[i].scatter(specials["price"], specials["discount_pct"],
                        color=PALETTE[i % len(PALETTE)], alpha=0.5, s=15)
        if len(specials) >= 2:
            z = np.polyfit(specials["price"], specials["discount_pct"], 1)
            p_fn = np.poly1d(z)
            x_line = np.linspace(specials["price"].min(), specials["price"].max(), 100)
            axes[i].plot(x_line, p_fn(x_line), color="#ef4444", linewidth=1.5)
        row = result[result["category"] == cat]
        rho_txt = f"ρ={row['spearman_rho'].values[0]:.2f}" if not row.empty else ""
        axes[i].set_title(f"{cat}\n{rho_txt}", fontweight="bold", fontsize=9)
        axes[i].set_xlabel("Price ($)", fontsize=8)
        axes[i].set_ylabel("Discount %", fontsize=8)

    plt.suptitle("Price vs Discount % Correlation (On-Special Products Only)\nSpearman ρ per Category",
                 fontsize=13, fontweight="bold", y=1.01)
    plt.tight_layout()
    savefig("19_price_vs_discount_correlation")

    print("\n── Spearman Correlation: Price vs Discount % ──")
    print(result.to_string(index=False))
    result.to_csv(os.path.join(REPORT_DIR, "price_discount_correlation.csv"), index=False)
    return result


# ── Master runner ──────────────────────────────────────────────────────────────
def run_deep_eda(db_path: str = DB_PATH):
    print("Loading data…")
    products, history = load(db_path)
    print(f"  Products : {len(products):,}  |  History rows : {len(history):,}\n")

    print("[1/7] Normality testing (Q-Q plots, skewness, kurtosis)")
    test_normality(products)

    print("\n[2/7] Own-brand vs national brand t-test")
    brand_ttest(products)

    print("\n[3/7] Price tier segmentation (KMeans)")
    price_tier_segmentation(products)

    print("\n[4/7] Implied annual inflation per category")
    category_inflation(history)

    print("\n[5/7] Brand premium / discount index")
    brand_premium_index(products)

    print("\n[6/7] Promotional cycle analysis")
    promotional_cycle(history)

    print("\n[7/7] Price vs discount Spearman correlation")
    price_vs_discount_correlation(products)

    figs = [f for f in os.listdir(FIG_DIR) if f.endswith(".png")]
    print(f"\n✅  Deep EDA complete — {len(figs)} total figures in {FIG_DIR}")


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.WARNING)
    run_deep_eda()
