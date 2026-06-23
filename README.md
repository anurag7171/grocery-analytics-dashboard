---
title: Australian Grocery Analytics Dashboard
emoji: 🛒
colorFrom: green
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

# 🛒 Australian Grocery Analytics Dashboard

Interactive price intelligence dashboard for Australian supermarket products.

## What's inside

- **1,275 real products** scraped from Woolworths Online across 10 grocery categories
- **66,300 price records** — 52-week synthetic history anchored to real prices with seasonal patterns
- **7-tab Streamlit dashboard** — overview, product explorer, category analysis, deals, best value, price trends, and 8-week forecast
- **Prophet forecasting** — Meta's time-series model trained per category
- **Deep EDA** — 19 analysis charts including normality tests, brand t-tests, inflation analysis, and promotional cycle detection
- **Excel report** — a formatted multi-sheet workbook (`docs/grocery-analytics-report.xlsx`) with category KPIs, brand comparison, weekly trends, and statistical test results

## Tech stack

| Layer | Tools |
|---|---|
| Scraping | `requests`, `BeautifulSoup` |
| Storage | `SQLite` + SQL queries |
| Analysis | `pandas`, `numpy`, `scipy` |
| Visualisation | `plotly`, `seaborn`, `matplotlib` |
| Forecasting | `Prophet` (Meta) |
| Dashboard | `Streamlit` |

## Key findings

- **Snacks** command the largest national-brand premium — 130% above own-brand (p<0.001)
- **Drinks** show the widest price premium for branded products (161%)
- **Fruit & Veg** has the most extreme right-skewed price distribution (skewness 4.2)
- Cheaper products receive **deeper discounts** — Bakery shows strongest inverse correlation (Spearman ρ = -0.78)
- **Dairy & Eggs** implied inflation: 4.7%/yr — highest of all categories

## Case study

**Question.** After the cost-of-living squeeze, which grocery categories are most expensive, where are own-brand savings largest, how often do specials actually run, and where are prices heading next quarter?

**Approach.** Collected 1,275 live Woolworths products, stored them in SQL, modelled a 52-week price history, ran statistical tests (Welch's t-test, Spearman correlation, OLS regression) and a Prophet forecast, then surfaced the results through Tableau and an interactive Streamlit app.

**Findings.** National brands cost up to 130% more than own-brand; cheaper items receive the deepest discounts; Dairy shows the steepest implied inflation (4.7%/yr); Snacks and Drinks go on special roughly every five weeks.

**Recommendation.** Switch to own-brand in Snacks and Drinks for the largest savings, buy Dairy ahead of its rising trend, and time purchases to the five-week promo cycle in the most-discounted categories.

> Note on data: product prices are scraped live from Woolworths; the 52-week price *history* is a realistic synthetic series anchored to those real prices (category seasonality, inflation, and promotional cycles), refreshed weekly via GitHub Actions.

## Run locally

```bash
git clone https://github.com/anurag7171/grocery-analytics-dashboard
cd grocery-analytics-dashboard
pip install -r requirements.txt
streamlit run app.py
```
