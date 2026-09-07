"""Treasury module: payment terms and accounts-payable aging.

Assigns payment terms per vendor, computes due dates, and buckets payable
into standard aging categories (not due / 0-30 / 31-60 / 61-90 / 90+) for
cash-management decision support.
"""

from datetime import date

import pandas as pd

from config import DEFAULT_TERMS_DAYS, VENDOR_TERMS

AGING_ORDER = ["not_due", "0_30", "31_60", "61_90", "over_90"]


def terms_for(vendor: str, vendor_terms=None, default=None) -> int:
    vendor_terms = vendor_terms if vendor_terms is not None else VENDOR_TERMS
    default = default if default is not None else DEFAULT_TERMS_DAYS
    vendor_lower = str(vendor).lower()
    for keyword, days in vendor_terms.items():
        if keyword in vendor_lower:
            return days
    return default


def assign_terms(df, vendor_terms=None, default=None):
    """Add `terms_days` and `due_date` columns."""
    df = df.copy()
    df["terms_days"] = [terms_for(v, vendor_terms, default) for v in df["vendor"]]
    df["due_date"] = df["date"] + pd.to_timedelta(df["terms_days"], unit="D")
    return df


def aging_bucket(due_date, as_of) -> str:
    delta_days = (as_of - due_date).days
    if delta_days < 0:
        return "not_due"
    if delta_days <= 30:
        return "0_30"
    if delta_days <= 60:
        return "31_60"
    if delta_days <= 90:
        return "61_90"
    return "over_90"


def assign_buckets(df, as_of=None):
    """Add `aging_bucket` relative to an as-of date (today by default)."""
    df = df.copy()
    as_of = pd.Timestamp(as_of if as_of is not None else date.today())
    df["aging_bucket"] = [aging_bucket(d if pd.notna(d) else as_of, as_of)
                          for d in df["due_date"]]
    return df


def aging_summary(df) -> dict:
    """Aggregate payable amounts per aging bucket, ordered for reporting."""
    if "aging_bucket" not in df.columns:
        return {"buckets": [], "past_due_total": 0.0}
    buckets = []
    past_due = 0.0
    for name in AGING_ORDER:
        group = df[df["aging_bucket"] == name]
        total = float(group["amount"].fillna(0).sum())
        buckets.append({"bucket": name, "count": int(len(group)), "total": total})
        if name != "not_due":
            past_due += total
    return {"buckets": buckets, "past_due_total": past_due}