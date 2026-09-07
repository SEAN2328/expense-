"""Modern enrichment step.

Takes the analysed expense dataframe (from anomaly.analyze) and layers on the
modern finance controls: expense classes, FX normalisation, payment aging,
fraud/statistical signals and a natural-language executive summary. Returns
the enriched dataframe, updated stats and a dictionary of extra reports used
by the CLI and the Streamlit app.
"""

from datetime import date

import numpy as np
import pandas as pd

from config import (BASE_CURRENCY, FX_RATES, VENDOR_TERMS)
from expense_class import classify
from fraud import append_fraud_signals, benford_table, risk_summary
from money import fx_exposure, to_base
from nlg import executive_summary
from treasury import aging_summary, assign_buckets, assign_terms

FLAG_BUMP = {
    "uncertain-classification": 10,
    "missing-fx-rate": 10,
    "high-fraud-risk": 15,
}


def _recompute_flags(df: pd.DataFrame) -> pd.DataFrame:
    """Append modern-control flags to existing flags and refresh status."""

    def combined(row):
        parts = [row["flags"]] if row["flags"] else []
        if row["uncertain_classification"]:
            parts.append("uncertain-classification")
        if row["fx_rate_missing"]:
            parts.append("missing-fx-rate")
        if row["high_fraud_risk"]:
            parts.append("high-fraud-risk")
        return "|".join(p for p in parts if p)

    df["flags"] = df.apply(combined, axis=1)
    df["status"] = df.apply(
        lambda r: ("rejected" if pd.isna(r["amount"]) or r["amount"] <= 0
                   else ("review" if r["flags"] else "approved")), axis=1)

    bump = np.zeros(len(df))
    bump += df["uncertain_classification"].astype(int) * FLAG_BUMP["uncertain-classification"]
    bump += df["fx_rate_missing"].astype(int) * FLAG_BUMP["missing-fx-rate"]
    bump += df["high_fraud_risk"].astype(int) * FLAG_BUMP["high-fraud-risk"]
    df["risk_score"] = np.clip(df["risk_score"].astype(float) + bump, 0, 100)
    return df


def _class_stats(df: pd.DataFrame) -> list:
    stats = []
    for (aclass, sub), group in df.groupby(["account_class", "sub_class"]):
        stats.append({
            "account_class": aclass,
            "sub_class": sub,
            "count": int(len(group)),
            "total": float(group["amount"].fillna(0).sum()),
        })
    return sorted(stats, key=lambda r: r["total"], reverse=True)


def enrich(df: pd.DataFrame, stats: dict, fx_rates=None, base_currency=None,
           vendor_terms=None, as_of=None) -> tuple:
    """Enrich the analysed frame; returns (df, stats, extras)."""
    df = df.copy()
    as_of = pd.Timestamp(as_of if as_of is not None else date.today())

    df = classify(df)
    df = to_base(df, fx_rates=fx_rates, base_currency=base_currency)
    df = assign_terms(df, vendor_terms=vendor_terms or VENDOR_TERMS)
    df = assign_buckets(df, as_of=as_of)
    df = append_fraud_signals(df)
    df = _recompute_flags(df)

    benford = benford_table(df["amount"])
    extras = {
        "expense_class": _class_stats(df),
        "fx_exposure": fx_exposure(df),
        "aging": aging_summary(df),
        "benford": benford,
        "benford_rows": benford["rows"],
        "top_risk": risk_summary(df),
        "base_currency": base_currency or BASE_CURRENCY,
        "summary": None,
    }
    extras["summary"] = executive_summary(df, stats, extras)

    stats = dict(stats)
    stats["by_class"] = extras["expense_class"]
    stats["fx_by_currency"] = extras["fx_exposure"]
    stats["aging"] = extras["aging"]
    stats["benford_alert"] = benford["alert"]
    stats["fraud_high_count"] = int(df["high_fraud_risk"].sum())
    stats["uncertain_count"] = int(df["uncertain_classification"].sum())
    stats["aggregated_bucket_total"] = extras["aging"]["past_due_total"]

    return df, stats, extras


REPORT_EXTRAS_KEYS = ["expense_class", "fx_exposure", "aging", "benford",
                      "top_risk", "summary"]