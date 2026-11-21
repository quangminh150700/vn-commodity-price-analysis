"""Clean the raw datasets into tidy CSVs in data/processed/.

Sources
-------
- World Bank Commodity Price Data ("Pink Sheet"), monthly, nominal USD.
- WFP Viet Nam food prices (wholesale rice, Mekong Delta markets), via HDX.

Run:  python src/clean.py
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"

PINK_SHEET = RAW / "CMO-Historical-Data-Monthly.xlsx"
PINK_SHEET_TAB = "Monthly Prices"
WFP_FILE = RAW / "wfp_food_prices_vnm.csv"

# Commodities that matter to Viet Nam's economy (exports, inputs, savings).
# Pink Sheet column name (whitespace-stripped) -> (short name, group)
COMMODITIES = {
    "Coffee, Robusta": ("Coffee (Robusta)", "Vietnam export"),
    "Rice, Viet Namese 5%": ("Rice (VN 5%)", "Vietnam export"),
    "Rice, Thai 5%": ("Rice (Thai 5%)", "Competitor benchmark"),
    "Rubber, RSS3": ("Rubber (RSS3)", "Vietnam export"),
    "Cocoa": ("Cocoa", "Soft commodity"),
    "Sugar, world": ("Sugar (world)", "Soft commodity"),
    "Crude oil, Brent": ("Crude oil (Brent)", "Energy & input"),
    "Urea": ("Urea (fertilizer)", "Energy & input"),
    "DAP": ("DAP (fertilizer)", "Energy & input"),
    "Maize": ("Maize", "Energy & input"),
    "Gold": ("Gold", "Store of value"),
    "Copper": ("Copper", "Industrial metal"),
}

PERIOD_PATTERN = r"^\d{4}M\d{2}$"  # e.g. 1960M01


def _find_header_row(raw: pd.DataFrame) -> int:
    """Locate the row holding commodity names instead of assuming a fixed position."""
    first = next(iter(COMMODITIES))
    for i in range(min(len(raw), 30)):
        if first in {str(v).strip() for v in raw.iloc[i]}:
            return i
    raise ValueError(f"Could not find the header row (looked for '{first}') in {PINK_SHEET.name}")


def clean_pink_sheet() -> pd.DataFrame:
    raw = pd.read_excel(PINK_SHEET, sheet_name=PINK_SHEET_TAB, header=None)
    header = _find_header_row(raw)
    names = [str(n).strip() for n in raw.iloc[header]]
    units = [str(u).strip().strip("()") for u in raw.iloc[header + 1]]

    missing = [c for c in COMMODITIES if c not in names]
    if missing:
        raise ValueError(f"Columns not found in {PINK_SHEET.name}: {missing}. "
                         "The World Bank may have renamed them; update COMMODITIES.")

    body = raw.iloc[header + 2:].copy()
    body.columns = names
    period = body.iloc[:, 0].astype(str).str.strip()
    body = body[period.str.match(PERIOD_PATTERN)]  # drop footnotes / blank rows
    dates = pd.to_datetime(body.iloc[:, 0].astype(str).str.replace("M", "-"), format="%Y-%m")
    unit_of = dict(zip(names, units))

    frames = []
    for col, (short, group) in COMMODITIES.items():
        # Missing values are stored as "…" or ".." -> NaN
        price = pd.to_numeric(body[col], errors="coerce")
        frames.append(pd.DataFrame({
            "date": dates.values,
            "commodity": short,
            "group": group,
            "unit": unit_of[col],
            "price_usd": price.values,
        }))
    df = pd.concat(frames, ignore_index=True).dropna(subset=["price_usd"])
    return df.sort_values(["commodity", "date"]).reset_index(drop=True)


def clean_wfp_rice() -> pd.DataFrame:
    df = pd.read_csv(WFP_FILE, dtype={"date": str})
    # drop the HXL tag row (#date, ...) and any row without a real date
    df = df[df["date"].str.match(r"\d{4}-\d{2}-\d{2}", na=False)].copy()
    df["date"] = pd.to_datetime(df["date"]).dt.to_period("M").dt.to_timestamp()
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df["usdprice"] = pd.to_numeric(df["usdprice"], errors="coerce")
    rice = df[(df["commodity"] == "Rice") & (df["pricetype"] == "Wholesale") & (df["unit"] == "KG")]
    return (rice.groupby(["date", "market"], as_index=False)
            .agg(price_vnd_kg=("price", "mean"), price_usd_kg=("usdprice", "mean")))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    prices = clean_pink_sheet()
    rice = clean_wfp_rice()
    prices.to_csv(OUT / "commodity_prices.csv", index=False)
    rice.to_csv(OUT / "vn_wholesale_rice.csv", index=False)
    print(f"commodity_prices.csv : {len(prices):>6} rows, "
          f"{prices['commodity'].nunique()} commodities, "
          f"{prices['date'].min():%Y-%m} -> {prices['date'].max():%Y-%m}")
    print(f"vn_wholesale_rice.csv: {len(rice):>6} rows, "
          f"{rice['date'].min():%Y-%m} -> {rice['date'].max():%Y-%m}")


if __name__ == "__main__":
    main()
