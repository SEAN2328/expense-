"""Categorisation module.

Maps each expense to a business category using keyword matching against
the vendor and description. Supports an optional manually-provided category
in the input data that takes precedence.
"""

import re

from config import CATEGORY_KEYWORDS, DEFAULT_CATEGORY


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9\s]", " ", text.lower()).strip()


def categorize_row(vendor: str, description: str, hint: object = None) -> str:
    """Return the best-matching category for a single expense row.

    The optional `hint` (a pre-labelled category in the input) wins if it is a
    known category. Otherwise we score keyword matches across vendor and
    description, favouring the category with the most matches.
    """
    # Manual / pre-existing tag takes precedence.
    if isinstance(hint, str):
        h = hint.strip().lower()
        if h and h != "uc" and h != "unknown":
            if h in CATEGORY_KEYWORDS or h == DEFAULT_CATEGORY:
                return h

    search_text = _normalize(f"{vendor} {description}")
    best_category = DEFAULT_CATEGORY
    best_score = 0
    for category, keywords in CATEGORY_KEYWORDS.items():
        score = sum(keyword in search_text for keyword in keywords)
        if score > best_score:
            best_score = score
            best_category = category
    return best_category


def assign_categories(df):
    """Add a `category` column to the dataframe using category hints if present."""
    has_hint = "category_hint" in df.columns
    categories = []
    for idx, row in df.iterrows():
        hint = row["category_hint"] if has_hint else None
        categories.append(categorize_row(row["vendor"], row["description"], hint))
    df = df.copy()
    df["category"] = categories
    return df
