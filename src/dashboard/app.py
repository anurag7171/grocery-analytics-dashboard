"""
Australian Grocery Analytics Dashboard
Streamlit app — price analysis, trends, and forecasting for Woolworths products.
"""

import os
import sys
import sqlite3
import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from src.scraper.init_db import build_if_missing
from src.analysis.sql_queries import load_all

# ── Config ─────────────────────────────────────────────────────────────────────
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "retail.db")

build_if_missing(DB_PATH)

PALETTE = {
    "primary":    "#16a34a",
    "secondary":  "#0ea5e9",
    "warning":    "#f59e0b",
    "danger":     "#ef4444",
    "bg":         "#f0fdf4",
    "card":       "#ffffff",
}

CATEGORY_COLORS = px.colors.qualitative.Safe

st.set_page_config(
    page_title="Australian Grocery Analytics",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .main { background-color: #f8fafc; }
    .block-container { padding-top: 3rem; padding-bottom: 2rem; }
    .stTabs [data-baseweb="tab-list"] { padding-top: 0.25rem; }
    .metric-card {
        background: white;
        border-radius: 12px;
        padding: 1.2rem 1.5rem;
        box-shadow: 0 1px 4px rgba(0,0,0,0.08);
        border-left: 4px solid #16a34a;
        margin-bottom: 1rem;
    }
    .metric-label { font-size: 0.78rem; color: #64748b; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; }
    .metric-value { font-size: 2rem; font-weight: 700; color: #0f172a; line-height: 1.2; }
    .metric-sub   { font-size: 0.82rem; color: #64748b; margin-top: 0.2rem; }
    .section-header { font-size: 1.25rem; font-weight: 700; color: #0f172a; margin-bottom: 0.5rem; margin-top: 1.5rem; }
    .insight-box {
        background: #eff6ff;
        border-left: 4px solid #3b82f6;
        border-radius: 8px;
        padding: 0.9rem 1.2rem;
        margin-bottom: 0.8rem;
        font-size: 0.9rem;
        color: #1e3a5f;
    }
    div[data-testid="stSidebarNav"] { display: none; }
    .stTabs [data-baseweb="tab-list"] { gap: 1.5rem; }
    .stTabs [data-baseweb="tab"] { border-radius: 8px 8px 0 0; font-weight: 600; padding: 0 0.85rem; }
</style>
""", unsafe_allow_html=True)


# ── Data loading ───────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner="Loading data…")
def load_data():
    return load_all(DB_PATH)


@st.cache_data(ttl=3600, show_spinner="Running forecasts…")
def load_forecasts():
    try:
        from src.forecasting.prophet_model import forecast_df_combined
        return forecast_df_combined(DB_PATH, periods=8)
    except Exception:
        return pd.DataFrame()


def kpi_card(label, value, sub=""):
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">{label}</div>
        <div class="metric-value">{value}</div>
        <div class="metric-sub">{sub}</div>
    </div>""", unsafe_allow_html=True)


def insight(text):
    st.markdown(f'<div class="insight-box">{text}</div>', unsafe_allow_html=True)


# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## Grocery Analytics")
    st.markdown("**Australian supermarket price intelligence**")
    st.divider()

    data = load_data()
    products = data["products"]

    all_cats = sorted(products["category"].unique().tolist())
    selected_cats = st.multiselect("Filter categories", all_cats, default=all_cats, key="cat_filter")

    price_min, price_max = float(products["price"].min()), float(products["price"].max())
    price_range = st.slider("Price range ($)", price_min, price_max, (price_min, price_max), step=0.50)

    show_specials_only = st.checkbox("Specials only")

    st.divider()
    st.caption(f"{len(products):,} products · 10 categories")
    st.caption("Source: Woolworths Online")
    st.caption("History: 52-week synthetic (seasonal model)")


# ── Filter helper ──────────────────────────────────────────────────────────────
def apply_filters(df):
    df = df[df["category"].isin(selected_cats)]
    df = df[(df["price"] >= price_range[0]) & (df["price"] <= price_range[1])]
    if show_specials_only:
        df = df[df["is_on_special"] == 1]
    return df


# ── Empty-selection guard ───────────────────────────────────────────────────────
# With no categories chosen every view would receive empty frames (and the
# forecast would hit NaT dates), so show a clear prompt instead of errors.
if not selected_cats:
    st.info("Select at least one category from the sidebar to explore the dashboard.")
    st.stop()

# ── Tabs ───────────────────────────────────────────────────────────────────────
tabs = st.tabs(["Overview", "Products", "Categories", "Deals", "Best Value", "Price Trends", "Forecast"])

filtered = apply_filters(products)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — OVERVIEW
# ══════════════════════════════════════════════════════════════════════════════
with tabs[0]:
    st.markdown('<div class="section-header">Market Snapshot</div>', unsafe_allow_html=True)

    fp = filtered
    if fp.empty:
        st.info("No products match the current filters. Widen the category or price-range filters in the sidebar.")
    else:
        total       = len(fp)
        on_special  = int(fp["is_on_special"].sum())
        special_pct = round(100 * on_special / total, 1)

        c1, c2, c3, c4, c5 = st.columns(5)
        with c1: kpi_card("Total Products", f"{total:,}", "match current filters")
        with c2: kpi_card("Avg Price", f"${fp['price'].mean():.2f}", "selected categories")
        with c3: kpi_card("On Special", f"{on_special:,}", f"{special_pct}% of selection")
        with c4: kpi_card("Categories", fp["category"].nunique(), "in current filter")
        with c5: kpi_card("Brands", fp["brand"].nunique(), "unique brands")

        st.divider()

        # Recompute per-category aggregates from the filtered products so these
        # charts respond to every sidebar filter (category, price, specials).
        cat_agg = fp.groupby("category", as_index=False).agg(
            avg_price=("price", "mean"),
            special_pct=("is_on_special", "mean"),
        )
        cat_agg["avg_price"]   = cat_agg["avg_price"].round(2)
        cat_agg["special_pct"] = (cat_agg["special_pct"] * 100).round(1)

        col_left, col_right = st.columns(2)
        with col_left:
            st.markdown('<div class="section-header">Average Price by Category</div>', unsafe_allow_html=True)
            fig = px.bar(
                cat_agg.sort_values("avg_price"),
                x="avg_price", y="category", orientation="h",
                color="avg_price", color_continuous_scale="Greens",
                labels={"avg_price": "Avg Price ($)", "category": ""},
                text="avg_price",
            )
            fig.update_traces(texttemplate="$%{text:.2f}", textposition="outside")
            fig.update_layout(height=400, margin=dict(l=0, r=40, t=10, b=10), coloraxis_showscale=False, plot_bgcolor="white")
            st.plotly_chart(fig, use_container_width=True)

        with col_right:
            st.markdown('<div class="section-header">% Products On Special by Category</div>', unsafe_allow_html=True)
            fig2 = px.bar(
                cat_agg.sort_values("special_pct"),
                x="special_pct", y="category", orientation="h",
                color="special_pct", color_continuous_scale="Oranges",
                labels={"special_pct": "% On Special", "category": ""},
                text="special_pct",
            )
            fig2.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
            fig2.update_layout(height=400, margin=dict(l=0, r=40, t=10, b=10), coloraxis_showscale=False, plot_bgcolor="white")
            st.plotly_chart(fig2, use_container_width=True)

        st.markdown('<div class="section-header">Key Insights</div>', unsafe_allow_html=True)
        most_expensive = cat_agg.loc[cat_agg["avg_price"].idxmax(), "category"]
        most_specials  = cat_agg.loc[cat_agg["special_pct"].idxmax(), "category"]
        disc = fp[fp["is_on_special"] == 1].groupby("category")["discount_pct"].mean()
        best_discount  = disc.idxmax() if not disc.empty else most_specials

        insight(f"<b>{most_expensive}</b> is the most expensive of the selected categories on average.")
        insight(f"<b>{most_specials}</b> runs the highest proportion of promotional specials.")
        insight(f"<b>{best_discount}</b> offers the deepest average discount when items are on special.")
        insight(f"<b>{on_special:,} products</b> ({special_pct}%) in your selection are discounted — worth checking before you shop.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — PRODUCT EXPLORER
# ══════════════════════════════════════════════════════════════════════════════
with tabs[1]:
    st.markdown('<div class="section-header">Product Explorer</div>', unsafe_allow_html=True)

    col_s, col_sort = st.columns([3, 1])
    with col_s:
        search = st.text_input("Search products", placeholder="e.g. milk, chicken, pasta…")
    with col_sort:
        sort_by = st.selectbox("Sort by", ["price (low to high)", "price (high to low)", "discount %", "name"])

    view = filtered.copy()
    if search:
        view = view[view["name"].str.contains(search, case=False, na=False)]

    sort_map = {"price (low to high)": ("price", True), "price (high to low)": ("price", False),
                "discount %": ("discount_pct", False), "name": ("name", True)}
    scol, asc = sort_map[sort_by]
    view = view.sort_values(scol, ascending=asc)

    st.markdown(f"**{len(view):,} products** matching filters")

    display_cols = ["name", "brand", "category", "price", "was_price", "discount_pct", "unit_size", "is_on_special"]
    show = view[display_cols].rename(columns={
        "name": "Product", "brand": "Brand", "category": "Category",
        "price": "Price ($)", "was_price": "Was ($)", "discount_pct": "Discount %",
        "unit_size": "Size", "is_on_special": "On Special",
    })
    show["On Special"] = show["On Special"].map({1: "Yes", 0: ""})
    show["Price ($)"]  = show["Price ($)"].map("${:.2f}".format)
    show["Was ($)"]    = show["Was ($)"].map("${:.2f}".format)
    show["Discount %"] = show["Discount %"].map("{:.1f}%".format)

    st.dataframe(show, use_container_width=True, height=480)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — CATEGORY ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════
with tabs[2]:
    st.markdown('<div class="section-header">Category Deep Dive</div>', unsafe_allow_html=True)

    selected_cat = st.selectbox("Select category", sorted(filtered["category"].unique()), key="cat_deep")
    cat_products = filtered[filtered["category"] == selected_cat]

    c1, c2, c3, c4 = st.columns(4)
    with c1: kpi_card("Products", len(cat_products))
    with c2: kpi_card("Avg Price", f"${cat_products['price'].mean():.2f}")
    with c3: kpi_card("On Special", f"{cat_products['is_on_special'].sum()} ({100*cat_products['is_on_special'].mean():.0f}%)")
    with c4: kpi_card("Price Range", f"${cat_products['price'].min():.2f} – ${cat_products['price'].max():.2f}")

    col_a, col_b = st.columns(2)
    with col_a:
        fig = px.histogram(
            cat_products, x="price", nbins=30,
            title="Price Distribution",
            labels={"price": "Price ($)", "count": "Products"},
            color_discrete_sequence=[PALETTE["primary"]],
        )
        fig.update_layout(plot_bgcolor="white", margin=dict(t=30, b=10))
        st.plotly_chart(fig, use_container_width=True)

    with col_b:
        brand_counts = cat_products["brand"].value_counts().head(12).reset_index()
        brand_counts.columns = ["Brand", "Count"]
        fig2 = px.bar(brand_counts, x="Count", y="Brand", orientation="h",
                      title="Top Brands",
                      color="Count", color_continuous_scale="Greens",
                      labels={"Count": "# Products", "Brand": ""})
        fig2.update_layout(plot_bgcolor="white", coloraxis_showscale=False, margin=dict(t=30, b=10))
        st.plotly_chart(fig2, use_container_width=True)

    # Price buckets
    st.markdown('<div class="section-header">Price Buckets — All Categories</div>', unsafe_allow_html=True)
    buckets = data["buckets"]
    buckets_melt = buckets.melt(id_vars="category", var_name="bucket", value_name="count")
    bucket_labels = {"under_2": "<$2", "btw_2_5": "$2–5", "btw_5_10": "$5–10", "btw_10_20": "$10–20", "over_20": ">$20"}
    buckets_melt["bucket"] = buckets_melt["bucket"].map(bucket_labels)
    fig3 = px.bar(buckets_melt, x="category", y="count", color="bucket",
                  barmode="stack", title="Price Distribution by Category",
                  labels={"count": "Products", "category": "", "bucket": "Price range"},
                  color_discrete_sequence=px.colors.sequential.Greens_r)
    fig3.update_layout(plot_bgcolor="white", xaxis_tickangle=-20, margin=dict(t=30))
    st.plotly_chart(fig3, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — DEALS & SPECIALS
# ══════════════════════════════════════════════════════════════════════════════
with tabs[3]:
    st.markdown('<div class="section-header">Current Deals & Specials</div>', unsafe_allow_html=True)

    deals = data["top_discounted"].copy()
    deals = deals[deals["category"].isin(selected_cats)]

    col_a, col_b = st.columns(2)
    with col_a:
        fig = px.bar(
            deals.head(20), x="discount_pct", y="name",
            orientation="h", color="category",
            title="Top 20 Discounts Right Now",
            labels={"discount_pct": "Discount %", "name": ""},
            color_discrete_sequence=CATEGORY_COLORS,
        )
        fig.update_layout(height=500, plot_bgcolor="white", margin=dict(t=30, r=20))
        st.plotly_chart(fig, use_container_width=True)

    with col_b:
        special_rate = data["special_rate"]
        special_rate = special_rate[special_rate["category"].isin(selected_cats)]
        fig2 = px.scatter(
            special_rate, x="special_pct", y="avg_discount",
            size="total", color="category", hover_name="category",
            title="Special Rate vs Average Discount Depth",
            labels={"special_pct": "% Products On Special", "avg_discount": "Avg Discount %"},
            color_discrete_sequence=CATEGORY_COLORS,
        )
        fig2.update_layout(height=500, plot_bgcolor="white", margin=dict(t=30))
        st.plotly_chart(fig2, use_container_width=True)

    st.markdown('<div class="section-header">All Current Specials</div>', unsafe_allow_html=True)
    specials_table = filtered[filtered["is_on_special"] == 1][
        ["name", "brand", "category", "price", "was_price", "discount_pct", "unit_size"]
    ].sort_values("discount_pct", ascending=False).rename(columns={
        "name": "Product", "brand": "Brand", "category": "Category",
        "price": "Price ($)", "was_price": "Was ($)",
        "discount_pct": "Discount %", "unit_size": "Size",
    })
    specials_table["Price ($)"]  = specials_table["Price ($)"].map("${:.2f}".format)
    specials_table["Was ($)"]    = specials_table["Was ($)"].map("${:.2f}".format)
    specials_table["Discount %"] = specials_table["Discount %"].map("{:.1f}%".format)
    st.dataframe(specials_table, use_container_width=True, height=380)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — BEST VALUE
# ══════════════════════════════════════════════════════════════════════════════
with tabs[4]:
    st.markdown('<div class="section-header">Best Value — Unit Price Analysis</div>', unsafe_allow_html=True)

    st.markdown("""
    Unit price (price per 100g/ml) cuts through pack-size tricks and reveals
    which products actually give you the most for your money.
    """)

    bv = data["best_value"].copy()
    bv = bv[bv["category"].isin(selected_cats)]

    col_a, col_b = st.columns(2)
    with col_a:
        fig = px.bar(
            bv.head(20), x="cup_price", y="name",
            orientation="h", color="category",
            title=f"Top 20 Best Unit Value Products",
            labels={"cup_price": "Unit Price ($/100g or /100ml)", "name": ""},
            color_discrete_sequence=CATEGORY_COLORS,
        )
        fig.update_layout(height=500, plot_bgcolor="white", margin=dict(t=30, r=20))
        st.plotly_chart(fig, use_container_width=True)

    with col_b:
        # Brand vs Own-brand unit price comparison
        brand_own = data["brand_own"].copy()
        brand_own = brand_own[brand_own["category"].isin(selected_cats)]
        fig2 = px.bar(
            brand_own, x="category", y="avg_price", color="brand_type",
            barmode="group",
            title="Own Brand vs National Brand — Avg Price",
            labels={"avg_price": "Avg Price ($)", "category": "", "brand_type": ""},
            color_discrete_map={"Own Brand": PALETTE["primary"], "National Brand": PALETTE["secondary"]},
        )
        fig2.update_layout(height=500, plot_bgcolor="white", xaxis_tickangle=-20, margin=dict(t=30))
        st.plotly_chart(fig2, use_container_width=True)

    st.markdown('<div class="section-header">Unit Price Table</div>', unsafe_allow_html=True)
    bv_display = bv[["name", "brand", "category", "price", "cup_price", "cup_measure", "unit_size"]].rename(columns={
        "name": "Product", "brand": "Brand", "category": "Category",
        "price": "Shelf Price ($)", "cup_price": "Unit Price",
        "cup_measure": "Per", "unit_size": "Pack Size",
    })
    bv_display["Shelf Price ($)"] = bv_display["Shelf Price ($)"].map("${:.2f}".format)
    bv_display["Unit Price"]      = bv_display["Unit Price"].map("${:.4f}".format)
    st.dataframe(bv_display, use_container_width=True, height=380)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 6 — PRICE TRENDS
# ══════════════════════════════════════════════════════════════════════════════
with tabs[5]:
    st.markdown('<div class="section-header">52-Week Price Trends</div>', unsafe_allow_html=True)

    weekly = data["weekly_avg"].copy()
    weekly = weekly[weekly["category"].isin(selected_cats)]
    weekly["week_date"] = pd.to_datetime(weekly["week_date"])

    fig = px.line(
        weekly, x="week_date", y="avg_price", color="category",
        title="Average Weekly Price per Category (52 Weeks)",
        labels={"week_date": "Week", "avg_price": "Avg Price ($)", "category": "Category"},
        color_discrete_sequence=CATEGORY_COLORS,
        line_shape="spline",
    )
    fig.update_layout(height=420, plot_bgcolor="white", hovermode="x unified", margin=dict(t=30))
    st.plotly_chart(fig, use_container_width=True)

    col_a, col_b = st.columns(2)
    with col_a:
        # Weekly special rate heatmap
        ws = data["weekly_specials"].copy()
        ws = ws[ws["category"].isin(selected_cats)]
        ws["week_date"] = pd.to_datetime(ws["week_date"])
        ws_pivot = ws.pivot(index="category", columns="week_date", values="special_pct").fillna(0)
        fig2 = px.imshow(
            ws_pivot, aspect="auto",
            color_continuous_scale="RdYlGn",
            title="Weekly Promotions Heatmap (% on special)",
            labels={"color": "% On Special"},
        )
        fig2.update_layout(height=360, margin=dict(t=30))
        st.plotly_chart(fig2, use_container_width=True)

    with col_b:
        # Price volatility top products
        vol = data["volatility"].copy()
        vol = vol[vol["category"].isin(selected_cats)].head(15)
        fig3 = px.bar(
            vol, x="coeff_variation_pct", y="name",
            orientation="h", color="category",
            title="Most Volatile Products (Coefficient of Variation %)",
            labels={"coeff_variation_pct": "CV %", "name": ""},
            color_discrete_sequence=CATEGORY_COLORS,
        )
        fig3.update_layout(height=360, plot_bgcolor="white", margin=dict(t=30))
        st.plotly_chart(fig3, use_container_width=True)

    st.markdown('<div class="section-header">Individual Product Price History</div>', unsafe_allow_html=True)
    selected_product = st.selectbox(
        "Select a product",
        filtered.sort_values("name")["name"].unique(),
        key="prod_trend",
    )
    if selected_product:
        pid = filtered[filtered["name"] == selected_product]["product_id"].values[0]
        conn_tmp = sqlite3.connect(DB_PATH)
        prod_hist = pd.read_sql(
            "SELECT week_date, price, regular_price, is_on_special FROM price_history_weekly WHERE product_id=? ORDER BY week_date",
            conn_tmp, params=(pid,)
        )
        conn_tmp.close()
        prod_hist["week_date"] = pd.to_datetime(prod_hist["week_date"])

        fig4 = go.Figure()
        fig4.add_trace(go.Scatter(x=prod_hist["week_date"], y=prod_hist["regular_price"],
                                  name="Regular Price", line=dict(color="#94a3b8", dash="dot")))
        fig4.add_trace(go.Scatter(x=prod_hist["week_date"], y=prod_hist["price"],
                                  name="Actual Price", line=dict(color=PALETTE["primary"], width=2)))
        specials = prod_hist[prod_hist["is_on_special"] == 1]
        fig4.add_trace(go.Scatter(x=specials["week_date"], y=specials["price"],
                                  name="On Special", mode="markers",
                                  marker=dict(color=PALETTE["danger"], size=8, symbol="star")))
        fig4.update_layout(
            title=f"Price History: {selected_product}",
            xaxis_title="Week", yaxis_title="Price ($)",
            height=350, plot_bgcolor="white", hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            margin=dict(t=50),
        )
        st.plotly_chart(fig4, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 7 — FORECAST
# ══════════════════════════════════════════════════════════════════════════════
with tabs[6]:
    st.markdown('<div class="section-header">8-Week Price Forecast</div>', unsafe_allow_html=True)
    st.markdown("Prophet time-series model trained on 52 weeks of category-level price history. Shaded band = 90% confidence interval.")

    with st.spinner("Running Prophet forecasts…"):
        forecast_df = load_forecasts()

    if forecast_df.empty:
        st.warning("Forecasts unavailable — install prophet: `pip install prophet`")
    else:
        forecast_df["ds"] = pd.to_datetime(forecast_df["ds"])
        forecast_cats = [c for c in forecast_df["category"].unique() if c in selected_cats]

        if not forecast_cats:
            st.info("None of the selected categories have a forecast available — pick another category in the sidebar.")
        else:
            sel_forecast_cat = st.selectbox("Select category to forecast", sorted(forecast_cats), key="fcat")
            cat_fc = forecast_df[forecast_df["category"] == sel_forecast_cat].copy()

            weekly = data["weekly_avg"].copy()
            weekly["week_date"] = pd.to_datetime(weekly["week_date"])
            hist_cat = weekly[weekly["category"] == sel_forecast_cat]
            last_hist_date = hist_cat["week_date"].max()

            if cat_fc.empty or hist_cat.empty or pd.isna(last_hist_date):
                st.info("Not enough price history to forecast this category yet.")
            else:
                # Split historical vs future
                hist_fc  = cat_fc[cat_fc["ds"] <= last_hist_date]
                future_fc = cat_fc[cat_fc["ds"] > last_hist_date]

                fig = go.Figure()
                fig.add_trace(go.Scatter(x=hist_cat["week_date"], y=hist_cat["avg_price"],
                                         name="Historical (actual)", line=dict(color=PALETTE["secondary"], width=2)))
                fig.add_trace(go.Scatter(x=cat_fc["ds"], y=cat_fc["yhat"],
                                         name="Prophet fit + forecast", line=dict(color=PALETTE["primary"], width=2)))
                fig.add_trace(go.Scatter(
                    x=pd.concat([cat_fc["ds"], cat_fc["ds"].iloc[::-1]]),
                    y=pd.concat([cat_fc["yhat_upper"], cat_fc["yhat_lower"].iloc[::-1]]),
                    fill="toself", fillcolor="rgba(22,163,74,0.12)",
                    line=dict(color="rgba(255,255,255,0)"),
                    name="90% confidence band", showlegend=True,
                ))
                # Pass a ms-epoch timestamp (not a string) — Plotly's add_vline fails on
                # string dates over a datetime axis ("unsupported operand type(s) for +").
                fig.add_vline(x=last_hist_date.timestamp() * 1000, line_dash="dash", line_color="#94a3b8",
                              annotation_text="Forecast starts", annotation_position="top left")
                fig.update_layout(
                    title=f"Price Forecast — {sel_forecast_cat}",
                    xaxis_title="Week", yaxis_title="Avg Price ($)",
                    height=420, plot_bgcolor="white", hovermode="x unified",
                    margin=dict(t=50),
                )
                st.plotly_chart(fig, use_container_width=True)

                if not future_fc.empty:
                    st.markdown("**8-Week Forecast Summary**")
                    summary = future_fc[["ds", "yhat", "yhat_lower", "yhat_upper"]].copy()
                    summary.columns = ["Week", "Forecast ($)", "Lower ($)", "Upper ($)"]
                    summary["Week"] = summary["Week"].dt.strftime("%d %b %Y")
                    for c in ["Forecast ($)", "Lower ($)", "Upper ($)"]:
                        summary[c] = summary[c].map("${:.2f}".format)
                    st.dataframe(summary, use_container_width=True, hide_index=True)

                    direction = "rising" if future_fc["yhat"].iloc[-1] > future_fc["yhat"].iloc[0] else "falling"
                    pct_change = 100 * (future_fc["yhat"].iloc[-1] - future_fc["yhat"].iloc[0]) / future_fc["yhat"].iloc[0]
                    insight(f"<b>{sel_forecast_cat}</b> prices are forecast to be <b>{direction}</b> over the next 8 weeks ({pct_change:+.1f}%). Consider stocking up now if this is a staple.")


# ── Footer ─────────────────────────────────────────────────────────────────────
st.divider()
st.caption("Data: Woolworths Online · Price history: 52-week seasonal model · Forecast: Prophet (Meta) · Built with Streamlit + Plotly")
