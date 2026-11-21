"""Reusable business metrics for monthly commodity price series.

Shared by the analysis notebook and the Streamlit dashboard so both
always report the same numbers.

All series are expected on a regular month-start index (see `wide`), with
missing months kept as NaN. Metrics therefore compare by calendar date,
never by position, so gaps in the data cannot shift "one year ago".
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MONTHS_PER_YEAR = 12
MIN_MONTHS_FOR_SCORECARD = 13  # need a value 12 months before the latest one
DAYS_PER_YEAR = 365.25

SCORECARD_COLUMNS = ["latest", "mom_%", "yoy_%", "cagr_%",
                     "volatility_%", "max_drawdown_%", "vs_period_avg_%"]


def load_prices() -> pd.DataFrame:
    """Tidy table: date, commodity, group, unit, price_usd."""
    return pd.read_csv(PROCESSED / "commodity_prices.csv", parse_dates=["date"])


def load_wholesale_rice() -> pd.DataFrame:
    """Tidy table: date, market, price_vnd_kg, price_usd_kg."""
    return pd.read_csv(PROCESSED / "vn_wholesale_rice.csv", parse_dates=["date"])


def wide(prices: pd.DataFrame, start: str | None = None, end: str | None = None) -> pd.DataFrame:
    """date x commodity price table on a complete monthly index (gaps stay NaN)."""
    w = prices.pivot(index="date", columns="commodity", values="price_usd").sort_index()
    w = w.asfreq("MS")
    return w.loc[start:end]


def rebase(w: pd.DataFrame, base: float = 100) -> pd.DataFrame:
    """Index every series to `base` at its first valid value (makes units comparable)."""
    def first_valid(s: pd.Series) -> float:
        idx = s.first_valid_index()
        return s[idx] if idx is not None else np.nan

    return w.div(w.apply(first_valid)).mul(base)


def value_months_ago(s: pd.Series, months: int) -> float:
    """Value exactly `months` calendar months before the series' last date (NaN if missing)."""
    target = s.index[-1] - pd.DateOffset(months=months)
    return s.get(target, np.nan)


def cagr(s: pd.Series) -> float:
    """Compound annual growth rate between the first and last valid values."""
    s = s.dropna()
    if len(s) < 2 or (s <= 0).any():
        return np.nan
    years = (s.index[-1] - s.index[0]).days / DAYS_PER_YEAR
    if years < 1:
        return np.nan  # annualising less than a year exaggerates noise
    return (s.iloc[-1] / s.iloc[0]) ** (1 / years) - 1


def annual_volatility(s: pd.Series) -> float:
    """Std-dev of month-on-month log returns, annualised.

    Returns across a data gap are NaN (not one big multi-month jump) and are ignored.
    """
    r = np.log(s.where(s > 0)).diff().dropna()
    return r.std() * np.sqrt(MONTHS_PER_YEAR) if len(r) > 1 else np.nan


def max_drawdown(s: pd.Series) -> float:
    """Worst peak-to-trough fall, as a negative fraction."""
    s = s.dropna()
    return (s / s.cummax() - 1).min() if len(s) else np.nan


def scorecard(w: pd.DataFrame) -> pd.DataFrame:
    """One row per commodity: latest price, momentum, growth, risk.

    Only commodities with a price in the table's last month and at least
    13 months of history are scored. Returns an empty frame (with the usual
    columns) if none qualify, e.g. when the period is too short.
    """
    rows: dict[str, dict[str, float]] = {}
    if len(w):
        for c in w.columns:
            s = w[c]
            if pd.isna(s.iloc[-1]) or s.notna().sum() < MIN_MONTHS_FOR_SCORECARD:
                continue
            latest = s.iloc[-1]
            rows[c] = {
                "latest": latest,
                "mom_%": (latest / value_months_ago(s, 1) - 1) * 100,
                "yoy_%": (latest / value_months_ago(s, MONTHS_PER_YEAR) - 1) * 100,
                "cagr_%": cagr(s) * 100,
                "volatility_%": annual_volatility(s) * 100,
                "max_drawdown_%": max_drawdown(s) * 100,
                "vs_period_avg_%": (latest / s.mean() - 1) * 100,
            }
    card = pd.DataFrame.from_dict(rows, orient="index", columns=SCORECARD_COLUMNS)
    return card.astype(float).sort_values("yoy_%", ascending=False)


def seasonality(s: pd.Series) -> pd.Series:
    """Average % deviation from the centred 2x12 moving average, by calendar month.

    The 2x12 MA (13 months, half weight on both ends) is symmetric around each
    month, unlike a plain 12-month centred window. Months with no estimate are NaN.
    """
    trend = s.rolling(MONTHS_PER_YEAR).mean().rolling(2).mean().shift(-(MONTHS_PER_YEAR // 2))
    dev = ((s / trend - 1) * 100).dropna()
    out = dev.groupby(dev.index.month).mean()
    out.index = [MONTHS[m - 1] for m in out.index]
    return out.reindex(MONTHS)


def return_correlation(w: pd.DataFrame) -> pd.DataFrame:
    """Correlation of monthly % changes (not levels, which are spuriously correlated)."""
    return w.pct_change(fill_method=None).corr()


def lagged_correlation(x: pd.Series, y: pd.Series, max_lag: int = 12) -> pd.Series:
    """corr(x_t, y_{t+lag}) of monthly % changes: does x lead y?

    Both series must share a regular monthly index (as produced by `wide`)
    so that shifting by `lag` rows means shifting by `lag` months.
    """
    rx, ry = x.pct_change(fill_method=None), y.pct_change(fill_method=None)
    return pd.Series({lag: rx.corr(ry.shift(-lag)) for lag in range(max_lag + 1)},
                     name="correlation")
