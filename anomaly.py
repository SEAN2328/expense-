"""Anomaly detection and rule-based flagging module.

Produces flags for each expense and computes category-level statistics and
risk scores. All rules are transparent and explainable, providing decision
support to the finance team.
"""

from datetime import datetime

import numpy as np
import pandas as pd

from config import (
    APPROVAL_THRESHOLD,
    APPROVED_VENDORS,
    BUSINESS_HOURS_END,
    BUSINESS_HOURS_START,
    CATEGORY_CAPS,
    OUTLIER_MULTIPLIER,
)


def _flag_outlier(df: pd.DataFrame, multiplier: float) -> pd.Series:
    """Flag amounts that are large relative to their category's median."""
    flags = pd.Series(index=df.index, dtype=str)
    for category, group in df.groupby("category"):
        median = group["amount"].median()
        if median and median > 0:
            threshold = median * multiplier
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


def _needs_approval(df: pd.DataFrame, threshold: float) -> pd.Series:
    return df["amount"] > threshold


def _flag_category_cap(df: pd.DataFrame, category_caps: dict) -> pd.Series:
    """Flag expenses that exceed their category's policy cap."""
    flags = pd.Series(index=df.index, dtype=str)
    if not category_caps:
        return flags.fillna("")
    for idx, row in df.iterrows():
        cap = category_caps.get(row["category"])
        if cap is not None and row["amount"] > cap:
            flags.loc[idx] = "category-cap-breach"
    return flags.fillna("")


def _flag_unapproved_vendor(df: pd.DataFrame, approved_vendors: list) -> pd.Series:
    """Flag expenses from vendors that are not on the approved list."""
    flags = pd.Series(index=df.index, dtype=str)
    if not approved_vendors:
        return flags.fillna("")
    approved = [v.strip().lower() for v in approved_vendors]
    for idx, row in df.iterrows():
        vendor = str(row["vendor"]).lower()
        if not any(keyword in vendor for keyword in approved):
            flags.loc[idx] = "unapproved-vendor"
    return flags.fillna("")


def analyze(df: pd.DataFrame, approval_threshold: float = None,
            outlier_multiplier: float = None, category_caps: dict = None,
            approved_vendors: list = None) -> dict:
    """Run all flagging rules and category statistics.

    All thresholds/caps default to those in config.py but can be overridden
    per-run (e.g. from the Streamlit sidebar) for what-if analysis.
    """
    approval_threshold = (approval_threshold if approval_threshold is not None
                          else APPROVAL_THRESHOLD)
    outlier_multiplier = (outlier_multiplier if outlier_multiplier is not None
                          else OUTLIER_MULTIPLIER)
    category_caps = category_caps if category_caps is not None else CATEGORY_CAPS
    approved_vendors = (approved_vendors if approved_vendors is not None
                        else APPROVED_VENDORS)

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")

    flags = pd.DataFrame(index=df.index)
    flags["amount_outlier"] = _flag_outlier(df, outlier_multiplier)
    flags["near_duplicate"] = _flag_near_duplicate(df)
    flags["outside_hours"] = _flag_out_of_business_hours(df)
    flags["category_cap_breach"] = _flag_category_cap(df, category_caps)
    flags["unapproved_vendor"] = _flag_unapproved_vendor(df, approved_vendors)
    flags["needs_approval"] = _needs_approval(df, approval_threshold)

    if category_caps:
        df["category_cap"] = df["category"].map(category_caps)

    # Combine non-empty, non-False flags into a single reason string.
    def combine(row):
        parts = []
        if row["amount_outlier"]:
            parts.append(row["amount_outlier"])
        if row["near_duplicate"]:
            parts.append(row["near_duplicate"])
        if row["outside_hours"]:
            parts.append(row["outside_hours"])
        if row["category_cap_breach"]:
            parts.append(row["category_cap_breach"])
        if row["unapproved_vendor"]:
            parts.append(row["unapproved_vendor"])
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
        "by_flag": _flag_table(df),
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
    score += non_empty(flags["category_cap_breach"]) * 20
    score += non_empty(flags["unapproved_vendor"]) * 30

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


def _flag_table(df: pd.DataFrame) -> list:
    """Count rows per flag type for summaries and charts."""
    counts = {}
    for flags in df["flags"]:
        if not flags:
            continue
        for flag in flags.split("|"):
            counts[flag] = counts.get(flag, 0) + 1
    return sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
