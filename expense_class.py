"""Expense class module.

Assigns a modern GL-style class to every expense:
  - account_class : CAPEX (capital expenditure) or OPEX (operating expense)
  - sub_class     : fixed vs variable (cost behaviour)
plus an uncertainty flag when the category assignment is low-confidence.
"""

import re

from config import (CAPEX_KEYWORDS, CAPEX_MIN_SUPPLIES_AMOUNT,
                    CONFIDENCE_THRESHOLD, FIXED_SUBCLASS, VARIABLE_SUBCLASS)


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9\s]", " ", text.lower()).strip()


def account_class(row) -> str:
    """Classify a row as CAPEX or OPEX heuristically."""
    text = _normalize(f"{row['vendor']} {row['description']}")
    if any(keyword in text for keyword in CAPEX_KEYWORDS):
        return "CAPEX"
    if row["category"] == "office_supplies" and row["amount"] > CAPEX_MIN_SUPPLIES_AMOUNT:
        return "CAPEX"
    return "OPEX"


def sub_class(row) -> str:
    """Classify cost behaviour as fixed or variable by category."""
    if row["category"] in FIXED_SUBCLASS:
        return "fixed"
    if row["category"] in VARIABLE_SUBCLASS:
        return "variable"
    return "variable"


def classify(df):
    """Add account_class, sub_class and uncertain_classification columns."""
    df = df.copy()
    df["account_class"] = df.apply(account_class, axis=1)
    df["sub_class"] = df.apply(sub_class, axis=1)
    df["uncertain_classification"] = df["category_confidence"] < CONFIDENCE_THRESHOLD
    return df