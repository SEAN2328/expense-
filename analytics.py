"""Cash-flow analytics module.

Produces spend trends, a next-period cash-flow forecast, vendor
concentration analysis and budget-vs-actual comparisons to support
financial planning decisions.
"""

import numpy as np
import pandas as pd

from config import FORECAST_DAYS, VENDOR_CONCENTRATION_ALERT


def daily_spend_series(df: pd.DataFrame) -> pd.Series:
    """Daily total spend as a time series aligned to the date index."""
    s = df.dropna(subset=["date"]).set_index("date")["amount"].sort_index()
    return s.resample("D").sum().fillna(0.0)


def weekly_spend_series(df: pd.DataFrame) -> pd.Series:
    """Weekly total spend as a time series for trend charts."""
    s = df.dropna(subset=["date"]).set_index("date")["amount"].sort_index()
    return s.resample("W").sum().fillna(0.0)


def forecast_next_period(df: pd.DataFrame, days: int = None) -> dict:
    """Forecast spend for the next `days` days.

    Uses the recent average daily burn rate blended with a linear-trend
    projection so the forecast is never misleadingly clamped to zero.
    Returns the projected total, the per-day trend and a confidence label.
    """
    days = days or FORECAST_DAYS
    daily = daily_spend_series(df)
    total_days = len(daily)
    if total_days == 0:
        return {"forecast": 0.0, "trend": 0.0, "confidence": "insufficient-data"}

    base_avg = float(daily.mean())
    recent = [v for v in daily.tail(7) if v > 0]
    recent_avg = float(np.mean(recent)) if recent else base_avg

    if total_days < 3:
        forecast = max(0.0, recent_avg * days) if recent_avg > 0 else max(0.0, base_avg * days)
        return {"forecast": forecast, "trend": 0.0, "confidence": "recent-rate"}

    x = np.arange(total_days)
    slope, intercept = np.polyfit(x, daily.values.astype(float), 1)
    projected = np.maximum(intercept + slope * np.arange(1, days + 1), 0.0)
    trend_forecast = float(projected.sum())
    forecast = max(0.0, 0.5 * recent_avg * days + 0.5 * trend_forecast)

    daily_mean = float(daily[daily > 0].mean()) if (daily > 0).any() else 1.0
    trend_pct = float(slope * 7 / daily_mean * 100)
    return {"forecast": forecast, "trend": trend_pct, "confidence": "trend-fit"}


def vendor_concentration(df: pd.DataFrame, top_n: int = 10) -> dict:
    """Share of total spend per vendor and concentration alerts."""
    total = float(df["amount"].fillna(0).sum())
    grouped = (df.groupby("vendor")["amount"].sum().sort_values(ascending=False))
    rows = []
    for vendor, amount in grouped.items():
        share = 0.0 if total == 0 else float(amount / total)
        rows.append({"vendor": vendor, "amount": float(amount), "share": share})
    top = rows[:top_n]
    alerts = [r for r in rows if r["share"] > VENDOR_CONCENTRATION_ALERT]
    return {"total": total, "vendors": top, "alerts": alerts}


def budget_vs_actual(df: pd.DataFrame, budget: dict) -> list:
    """Compare per-category actual spend against a given budget dict."""
    if not budget:
        return []
    actual = df.groupby("category")["amount"].sum()
    rows = []
    for category, budget_amount in budget.items():
        act = float(actual.get(category, 0.0))
        budget_amount = float(budget_amount)
        rows.append({
            "category": category,
            "budget": budget_amount,
            "actual": act,
            "variance": budget_amount - act,
            "overspend": act > budget_amount,
        })
    return sorted(rows, key=lambda r: r["variance"])


def flag_breakdown(stats: dict) -> pd.DataFrame:
    """Return the by-flag counts from agent stats as a small dataframe."""
    return pd.DataFrame(stats["by_flag"], columns=["flag", "count"])