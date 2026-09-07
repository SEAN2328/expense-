"""Verification tests for the Expense Processing Agent.

Run with:  python -m pytest tests.py   or   python tests.py
"""

import os
import sys
import tempfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from scripts.generate_data import generate  # noqa: E402
from anomaly import analyze  # noqa: E402
from categorizer import assign_categories  # noqa: E402
from reader import read_expenses  # noqa: E402


def _run_pipeline_on(df: pd.DataFrame):
    """Run categorization + analysis, return the annotated dataframe."""
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        df.to_csv(f.name, index=False, date_format="%Y-%m-%d %H:%M")
        tmp = f.name
    try:
        raw = read_expenses(tmp)
        annotated = assign_categories(raw)
        result = analyze(annotated)
        return result["df"], result["stats"]
    finally:
        os.unlink(tmp)


def test_all_injected_anomalies_detected():
    df, stats = _run_pipeline_on(generate())
    flagged = df[df["flags"] != ""]
    assert stats["approval_required_count"] == 2          # Staples 7400 + AWS 7800
    assert stats["total_flag_count"] >= 6                  # our injected edge cases
    # near-duplicate pair
    grille = df[df["vendor"] == "The Capital Grille"]
    dup_rows = grille[grille["flags"].str.contains("near-duplicate", na=False)]
    assert len(dup_rows) >= 1
    # off-hours meal
    pizza = df[df["vendor"] == "Late Night Pizza Co."]
    assert pizza["flags"].str.contains("outside-business-hours").any()
    # invalid amount rejected
    refund = df[df["vendor"] == "Refund Desk"]
    assert (refund["status"] == "rejected").all()
    # approval overrides
    aws = df[df["description"] == "Annual reserved instances"]
    assert (aws["status"] == "review").all()
    assert (aws["flags"].str.contains("exceeds-approval-limit")).all()
    print("OK: all 6 injected anomaly types detected.")


def test_clean_expenses_are_approved():
    clean = pd.DataFrame({
        "date": ["2026-08-10 10:00", "2026-08-11 11:00"],
        "vendor": ["Office Depot", "Uber"],
        "description": ["Printer paper", "Taxi to HQ"],
        "amount": [25.00, 18.00],
    })
    df, _ = _run_pipeline_on(clean)
    assert (df["status"] == "approved").all()
    print("OK: clean expenses auto-approved, zero false positives.")


def test_category_cap_breach_and_vendor_screening():
    capped = pd.DataFrame({
        "date": ["2026-08-10 20:00"],
        "vendor": ["The Capital Grille"],
        "description": ["Client dinner"],
        "amount": [150.00],
    })
    df, _ = _run_pipeline_on(capped)
    row = df.iloc[0]
    assert "category-cap-breach" in row["flags"]
    assert row["status"] == "review"

    unknown = pd.DataFrame({
        "date": ["2026-08-10 12:00"],
        "vendor": ["Nexus Consulting Group"],
        "description": ["Advisory project"],
        "amount": [900.00],
    })
    df2, _ = _run_pipeline_on(unknown)
    assert "unapproved-vendor" in df2.iloc[0]["flags"]
    print("OK: category-cap breach and unapproved-vendor screening detected.")


def test_compliance_rules_can_be_disabled():
    capped = pd.DataFrame({
        "date": ["2026-08-10 20:00"],
        "vendor": ["Random Vendor XYZ"],
        "description": ["Widget purchase"],
        "amount": [5000.00],
    })
    from config import NO_CAPS, NO_VENDORS
    result = analyze(assign_categories(capped),
                     category_caps=NO_CAPS, approved_vendors=NO_VENDORS)
    df = result["df"]
    assert df.iloc[0]["status"] == "review"  # only outlier/approval logic remains
    assert "category-cap-breach" not in df.iloc[0]["flags"]
    assert "unapproved-vendor" not in df.iloc[0]["flags"]
    print("OK: caps and vendor screening can be toggled off.")


def test_forecast_and_concentration():
    from analytics import forecast_next_period, vendor_concentration
    df, _ = _run_pipeline_on(generate())
    forecast = forecast_next_period(df)
    assert forecast["forecast"] >= 0
    conc = vendor_concentration(df)
    assert conc["total"] == df["amount"].sum()
    assert conc["vendors"]
    print("OK: cash-flow forecast and vendor concentration analytics run.")


def test_input_validation():
    from reader import InputError
    import tempfile
    bad = pd.DataFrame({"vendor": ["X"], "amount": [1.0]})  # missing date/description
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        bad.to_csv(f.name, index=False)
        tmp = f.name
    try:
        try:
            read_expenses(tmp)
            assert False, "should have raised InputError"
        except InputError:
            pass
    finally:
        os.unlink(tmp)
    print("OK: missing required columns rejected with clear error.")


if __name__ == "__main__":
    test_all_injected_anomalies_detected()
    test_clean_expenses_are_approved()
    test_category_cap_breach_and_vendor_screening()
    test_compliance_rules_can_be_disabled()
    test_forecast_and_concentration()
    test_input_validation()
    print("\nAll tests passed.")