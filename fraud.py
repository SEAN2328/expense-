"""Fraud and statistical audit signals.

Implements classic forensic-accounting indicators:
  - Benford's law first-digit distribution check on invoice amounts
  - per-category Z-score outliers
  - a composite Fraud Risk Index (FRI) blending rule risk, statistical
    outliers and FX red flags, so analysts can rank reviewers quickly.
"""

import math

import numpy as np
import pandas as pd

from config import (BENFORD_MAD_THRESHOLD, FRAUD_RISK_THRESHOLD,
                    Z_SCORE_THRESHOLD)

BENFORD_EXPECTED = {d: math.log10(1 + 1 / d) for d in range(1, 10)}


def _first_digit(amount: float) -> int:
    if amount <= 0 or math.isnan(amount):
        return None
    return int(str(f"{amount:.2f}".lstrip("0").replace(".", ""))[0])


def benford_table(amounts) -> dict:
    """Observed vs expected first-digit frequencies (Benford's law).

    Returns digits, observed/expected proportions and mean absolute deviation.
    """
    digits = []
    for amount in amounts:
        d = _first_digit(float(amount))
        if d is not None:
            digits.append(d)
    total = len(digits)
    mad = None
    rows = []
    expected_total = 0.0
    observed_total = 0.0
    if total:
        for d in range(1, 10):
            observed = digits.count(d) / total
            expected = BENFORD_EXPECTED[d]
            rows.append({"digit": d, "observed": observed, "expected": expected,
                         "diff": observed - expected})
            expected_total += expected
            observed_total += observed
        mad = float(np.mean([abs(r["diff"]) for r in rows]))
    return {"rows": rows, "count": total, "mad": mad,
            "alert": total >= 30 and mad is not None and mad > BENFORD_MAD_THRESHOLD}


def z_outlier_signal(df: pd.DataFrame) -> pd.Series:
    """True where |z-score| exceeds threshold within the row's category."""
    signal = pd.Series(False, index=df.index)
    for category, group in df.groupby("category"):
        vals = group["amount"].astype(float)
        if len(group) < 3 or vals.std() == 0:
            continue
        z = (vals - vals.mean()).abs() / vals.std()
        for idx in group.index:
            if z.loc[idx] > Z_SCORE_THRESHOLD:
                signal.loc[idx] = True
    return signal


def fraud_risk_index(df: pd.DataFrame, risk_score: pd.Series,
                     z_signal: pd.Series) -> pd.Series:
    """Composite 0-100 fraud index from rule risk, statistical signal, FX."""
    fri = np.zeros(len(df))
    fri += risk_score.astype(float) * 0.7
    fri += z_signal.astype(int) * 20.0
    fri += df["fx_rate_missing"].astype(int) * 10.0
    return np.clip(fri, 0, 100).astype(float)


def append_fraud_signals(df: pd.DataFrame) -> pd.DataFrame:
    """Add z signal, FRI and high-fraud-risk flag columns."""
    df = df.copy()
    df["z_outlier"] = z_outlier_signal(df)
    df["fraud_risk_index"] = fraud_risk_index(df, df["risk_score"], df["z_outlier"])
    df["high_fraud_risk"] = df["fraud_risk_index"] > FRAUD_RISK_THRESHOLD
    return df


def risk_summary(df: pd.DataFrame) -> list:
    """Top-risk rows sorted by fraud risk index for review prioritisation."""
    cols = [c for c in ["date", "vendor", "description", "amount",
                        "amount_usd", "category", "fraud_risk_index",
                        "flags", "status"] if c in df.columns]
    return jsonable_rows(df[cols].sort_values("fraud_risk_index", ascending=False)
                         .head(15))


def jsonable_rows(df: pd.DataFrame) -> list:
    import json
    return json.loads(df.to_json(orient="records", date_format="iso",
                                 default_handler=str))