"""Categorisation module.

Maps each expense to a business category using keyword matching against
the vendor and description, and scores the confidence of that assignment.
Supports an optional manually-provided category in the input data that takes
precedence.
"""

import re

from config import CATEGORY_KEYWORDS, DEFAULT_CATEGORY


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9\s]", " ", text.lower()).strip()


def score_row(vendor: str, description: str, hint: object = None):
    """Return (category, confidence) for a single expense row.

    Confidence is 0-100. A valid pre-labelled hint is trusted heavily; keyword
    strength scales with the number of matched keywords and keyword specificity.
    """
    if isinstance(hint, str):
        h = hint.strip().lower()
        if h and h != "uc" and h != "unknown":
            if h in CATEGORY_KEYWORDS or h == DEFAULT_CATEGORY:
                return h, 97.0

    search_text = _normalize(f"{vendor} {description}")
    best_category = DEFAULT_CATEGORY
    best_score = 0
    total_matches = 0
    for category, keywords in CATEGORY_KEYWORDS.items():
        score = sum(keyword in search_text for keyword in keywords)
        total_matches += score
        if score > best_score:
            best_score = score
            best_category = category

    if not search_text:
        confidence = 5.0
    elif best_score == 0:
        confidence = 30.0
    else:
        strength = 50.0 + best_score * (12.0 if best_score >= 2 else 10.0)
        confidence = min(92.0, strength - min(total_matches - best_score, 2) * 8.0)
    return best_category, round(confidence, 1)


def categorize_row(vendor: str, description: str, hint: object = None) -> str:
    """Return the best-matching category for a single expense row."""
    return score_row(vendor, description, hint)[0]


def assign_categories(df):
    """Add `category` and `category_confidence` columns to the dataframe."""
    has_hint = "category_hint" in df.columns
    categories = []
    confidences = []
    for idx, row in df.iterrows():
        hint = row["category_hint"] if has_hint else None
        category, confidence = score_row(row["vendor"], row["description"], hint)
        categories.append(category)
        confidences.append(confidence)
    df = df.copy()
    df["category"] = categories
    df["category_confidence"] = confidences
    return df