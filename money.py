"""Multi-currency normalisation module.

Maps each row's currency into a base currency (USD by default) using a
reference rate table, and reports FX exposure so the finance team can see
currency risk across the ledger.
"""

import pandas as pd

from config import BASE_CURRENCY, FX_RATES


def to_base(df, fx_rates=None, base_currency=None):
    """Add `currency`, `amount_usd` and `fx_rate_missing` to the dataframe."""
    fx_rates = dict(fx_rates if fx_rates is not None else FX_RATES)
    base = base_currency or BASE_CURRENCY
    df = df.copy()

    if "currency" not in df.columns:
        df["currency"] = base
    else:
        df["currency"] = df["currency"].astype(str).str.strip().str.upper().replace(
            {"": base, "nan": base})

    df["fx_rate"] = df["currency"].map(fx_rates)
    df["fx_rate_missing"] = df["fx_rate"].isna()
    df["amount_usd"] = df["amount"] * df["fx_rate"].fillna(1.0)
    return df


def fx_exposure(df) -> list:
    """Total spend per currency (and USD-equivalent) for exposure reporting."""
    if "currency" not in df.columns or "amount_usd" not in df.columns:
        return []
    rows = []
    for currency, group in df.groupby("currency"):
        rows.append({
            "currency": currency,
            "native_total": float(group["amount"].fillna(0).sum()),
            "usd_total": float(group["amount_usd"].fillna(0).sum()),
            "count": int(len(group)),
        })
    return sorted(rows, key=lambda r: r["usd_total"], reverse=True)