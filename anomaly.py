"""Anomaly detection and rule-based flagging module.

Produces flags for each expense and computes category-level statistics and
risk scores. All rules are transparent and explainable, providing decision
support to the finance team.
"""

from datetime import datetime

import numpy as np
import pandas as pd

from config import APPROVAL_THRESHOLD, BUSINESS_HOURS_END, BUSINESS_HOURS_START, OUTLIER_MULTIPLIER


def _flag_outlier(df: pd.DataFrame) -> pd.Series:
    """Flag amounts that are large relative to their category's median."""
    flags = pd.Series(index=df.index, dtype=str)
    for category, group in df.groupby("category"):
        median = group["amount"].median()
        if median and median > 0:
            threshold = median * OUTLIER_MULTIPLIER
            outliers = group[group["amount"] > threshold]
            flags.loc[outliers.index] = "amount-outlier"
    return flags.fillna("")


def _flag_near_duplicate(df: pd.DataFrame) -> pd.Series:
    """Flag expenses from the same vendor, same amount, within 3 days."""
    flags = pd.Series(index=df.index, dtype=str)
    if df["date"].isna().all():
        return flags.fillna("")
    df2 = df.dropna(subset=["date"])
    for idx, row in df2.iterrows():
        same_vendor = df2["vendor"] == row["vendor"]
        same_amount = np.isclose(df2["amount"], row["amount"])
        near_date = (df2["date"] - row["date"]).abs().dt.days.between(1, 3)
        dup_count = int((same_vendor & same_amount & near_date).sum())
        if dup_count > 0:
            flags.loc[idx] = "near-duplicate"
    return flags.fillna("")


def _flag_out_of_business_hours(df: pd.DataFrame) -> pd.Series:
    """Flag meals/entertainment expenses timestamped outside business hours."""
    flags = pd.Series(index=df.index, dtype=str)
    ts = pd.to_datetime(df["date"], errors="coerce")
    for idx, row in df.iterrows():
        t = ts.loc[idx]
        if pd.isna(t):
            continue
        hour = t.hour
        if row["category"] == "meals_entertainment" and not (
            BUSINESS_HOURS_START <= hour < BUSINESS_HOURS_END
        ):
            flags.loc[idx] = "outside-business-hours"
    return flags.fillna("")


def _needs_approval(df: pd.DataFrame) -> pd.Series:
    return df["amount"] > APPROVAL_THRESHOLD


def analyze(df: pd.DataFrame) -> dict:
    """Run all flagging rules and category statistics."""
    df = df.copy()

    flags = pd.DataFrame(index=df.index)
    flags["amount_outlier"] = _flag_outlier(df)
    flags["near_duplicate"] = _flag_near_duplicate(df)
    flags["outside_hours"] = _flag_out_of_business_hours(df)
    flags["needs_approval"] = _needs_approval(df)

    # Combine non-empty, non-False flags into a single reason string.
    def combine(row):
        parts = []
        if row["amount_outlier"]:
            parts.append(row["amount_outlier"])
        if row["near_duplicate"]:
            parts.append(row["near_duplicate"])
        if row["outside_hours"]:
            parts.append(row["outside_hours"])
        if row["needs_approval"]:
            parts.append("exceeds-approval-limit")
        return "|".join(parts)

    df["flags"] = flags.apply(combine, axis=1)
    df["status"] = _assign_status(df)
    df["risk_score"] = _risk_score(df, flags)

    stats = {
        "total_rows": int(len(df)),
        "total_amount": float(df["amount"].fillna(0).sum()),
        "total_flag_count": int((df["flags"] != "").sum()),
        "approval_required_count": int(flags["needs_approval"].sum()),
        "by_category": _category_table(df),
    }
    return {"flags": flags, "df": df, "stats": stats}


def _assign_status(df: pd.DataFrame) -> pd.Series:
    """Rule-based approve / review / reject classification."""
    def rule(row):
        rejected = row["amount"] <= 0
        needs_review = row["flags"] != ""
        if rejected:
            return "rejected"
        if needs_review:
            return "review"
        return "approved"
    return df.apply(rule, axis=1)


def _risk_score(df: pd.DataFrame, flags: pd.DataFrame) -> pd.Series:
    """Simple 0-100 risk score based on number of active flags and category."""
    high_risk_cats = {"travel", "meals_entertainment", "professional_services"}
    score = np.zeros(len(df))

    non_empty = lambda col: (col != "").astype(int)
    score += non_empty(flags["needs_approval"]) * 40
    score += non_empty(flags["amount_outlier"]) * 25
    score += non_empty(flags["near_duplicate"]) * 25
    score += non_empty(flags["outside_hours"]) * 10

    cat_risk = df["category"].isin(high_risk_cats).astype(int) * 10
    return np.clip(score + cat_risk, 0, 100)


def _category_table(df: pd.DataFrame) -> list:
    table = []
    for category, group in df.groupby("category"):
        if group["amount"].notna().sum() == 0:
            continue
        table.append({
            "category": category,
            "count": int(len(group)),
            "total": float(group["amount"].fillna(0).sum()),
            "mean": float(group["amount"].mean()),
            "median": float(group["amount"].median()),
            "max": float(group["amount"].max()),
        })
    return sorted(table, key=lambda r: r["total"], reverse=True)
