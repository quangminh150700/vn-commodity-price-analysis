"""Interactive dashboard.  Run:  streamlit run app.py"""
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent / "src"))
from metrics import (
    load_prices,
    load_wholesale_rice,
    rebase,
    return_correlation,
    scorecard,
    seasonality,
    wide,
)

MIN_YEARS = 2            # shortest period the slider allows (YoY needs 13 months)
MIN_SEASON_YEARS = 3     # seasonality needs several full cycles to mean anything
KPI_COLUMNS = 5
SEASON_COLOR_RANGE = 7   # +/- % for the seasonality heatmap colour scale

st.set_page_config(page_title="Vietnam Commodity Prices", page_icon="📈", layout="wide")


@st.cache_data
def data() -> tuple[pd.DataFrame, pd.DataFrame]:
    return load_prices(), load_wholesale_rice()


try:
    prices, wholesale = data()
except FileNotFoundError:
    st.error("Processed data not found. Run `python src/clean.py` first.")
    st.stop()

all_items = sorted(prices["commodity"].unique())
last = prices["date"].max()

# ---------- Sidebar filters ----------
st.sidebar.header("Filters")
picked = st.sidebar.multiselect(
    "Commodities", all_items,
    default=["Coffee (Robusta)", "Rice (VN 5%)", "Rubber (RSS3)", "Crude oil (Brent)", "Gold"])
years = st.sidebar.slider("Period", 2004, last.year, (2016, last.year))
st.sidebar.caption(f"Data: World Bank Pink Sheet (to {last:%b %Y}), WFP Viet Nam.")

if not picked:
    st.warning("Pick at least one commodity.")
    st.stop()
if years[1] - years[0] + 1 < MIN_YEARS:
    st.warning(f"Pick a period of at least {MIN_YEARS} years so year-on-year changes can be computed.")
    st.stop()

start, end = f"{years[0]}-01", f"{years[1]}-12"
w_all = wide(prices, start, end)
w = w_all[picked]

st.title("📈 Vietnam Commodity Price Dashboard")
st.caption("World prices of Viet Nam's key exports and inputs — monthly, nominal USD.")

# ---------- KPI cards ----------
card = scorecard(w)
units = prices.drop_duplicates("commodity").set_index("commodity")["unit"]
cols = st.columns(min(len(picked), KPI_COLUMNS))
for i, name in enumerate(picked):
    col = cols[i % len(cols)]
    if name in card.index:
        r = card.loc[name]
        yoy = "n/a" if pd.isna(r["yoy_%"]) else f"{r['yoy_%']:+.1f}% YoY"
        col.metric(f"{name} ({units[name]})", f"{r['latest']:,.2f}", yoy)
    else:
        col.metric(f"{name} ({units[name]})", "—", "not enough data", delta_color="off")

tab1, tab2, tab3, tab4 = st.tabs(["Trends", "Risk & return", "Seasonality", "Rice deep-dive"])

with tab1:
    indexed = st.toggle("Index to 100 at start of period (compare growth)", value=True)
    plot_df = rebase(w) if indexed else w
    fig = px.line(plot_df, labels={"value": "Index" if indexed else "Price (USD)", "date": ""})
    fig.update_layout(legend_title="", hovermode="x unified")
    st.plotly_chart(fig, width="stretch")
    st.subheader("Scorecard")
    if card.empty:
        st.info("None of the selected commodities has enough data in this period.")
    else:
        st.dataframe(card.style.format("{:,.1f}", na_rep="n/a")
                     .background_gradient(subset=["yoy_%"], cmap="RdYlGn"),
                     width="stretch")

with tab2:
    full = scorecard(w_all).dropna(subset=["cagr_%", "volatility_%"])
    if full.empty:
        st.info("Not enough data in this period for a risk/return comparison.")
    else:
        fig = px.scatter(full.reset_index(names="commodity"), x="volatility_%", y="cagr_%",
                         text="commodity",
                         labels={"volatility_%": "Annualised volatility (%)", "cagr_%": "CAGR (%)"})
        fig.update_traces(textposition="top center", marker_size=12)
        st.plotly_chart(fig, width="stretch")
        st.caption("Top-left = high growth with low risk. Correlation below uses monthly % changes.")
    if len(picked) > 1:
        st.plotly_chart(px.imshow(return_correlation(w).round(2), text_auto=True,
                                  color_continuous_scale="RdBu_r", zmin=-1, zmax=1),
                        width="stretch")

with tab3:
    if years[1] - years[0] + 1 < MIN_SEASON_YEARS:
        st.info(f"Seasonality needs a period of at least {MIN_SEASON_YEARS} years. "
                "Widen the period to see it.")
    else:
        season = pd.DataFrame({c: seasonality(w[c]) for c in picked}).T.dropna(how="all")
        fig = px.imshow(season.round(1), text_auto=True, color_continuous_scale="RdBu_r",
                        zmin=-SEASON_COLOR_RANGE, zmax=SEASON_COLOR_RANGE, aspect="auto",
                        labels={"color": "% vs trend"})
        st.plotly_chart(fig, width="stretch")
        st.caption("Average % deviation from the centred 12-month moving average in each "
                   "calendar month. Use a long period (10+ years) for reliable patterns.")

with tab4:
    rice = w_all[["Rice (VN 5%)", "Rice (Thai 5%)"]]
    spread = (rice["Rice (Thai 5%)"] - rice["Rice (VN 5%)"]).rename("Thai − VN spread")
    c1, c2 = st.columns(2)
    c1.plotly_chart(px.line(rice, title="Export price ($/mt)",
                            labels={"value": "$/mt", "date": ""}), width="stretch")
    c2.plotly_chart(px.area(spread, title="How much cheaper VN rice is ($/mt)",
                            labels={"value": "$/mt", "date": ""}), width="stretch")
    dom = wholesale.groupby("date")["price_usd_kg"].mean().mul(1000).rename("Mekong wholesale")
    both = pd.concat([dom, rice["Rice (VN 5%)"]], axis=1, sort=True).loc[start:end].dropna()
    if both.empty:
        st.info("WFP wholesale data covers 2008 – Jun 2022 only; widen the period to see it.")
    else:
        st.plotly_chart(px.line(both, title="Domestic wholesale vs export price ($/mt)",
                                labels={"value": "$/mt", "date": ""}), width="stretch")
        ratio = (both["Mekong wholesale"] / both["Rice (VN 5%)"]).median()
        st.metric("Domestic wholesale as % of export price (median)", f"{ratio:.0%}")
        st.caption("Domestic price = average of the WFP markets reporting that month "
                   "(An Giang, Dong Thap; Bac Lieu from 2021).")
