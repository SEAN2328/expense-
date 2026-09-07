"""Output / reporting module.

Writes the processed results to CSV (per-expense detail) and produces a
human-readable textual report plus a JSON machine-readable report.
"""

import json
from pathlib import Path

import pandas as pd

from config import OUTPUT_CSV, OUTPUT_JSON, OUTPUT_TXT


def write_csv(df: pd.DataFrame, output_path: str = OUTPUT_CSV) -> str:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = ["date", "vendor", "description", "amount", "currency", "amount_usd",
            "category", "category_confidence", "account_class", "sub_class",
            "terms_days", "due_date", "aging_bucket", "fraud_risk_index",
            "flags", "risk_score", "status"]
    cols = [c for c in cols if c in df.columns]
    df[cols].to_csv(path, index=False, date_format="%Y-%m-%d %H:%M")
    return str(path)


def build_text_report(stats: dict, summary_flags: list, extras=None) -> str:
    extras = extras or {}
    lines = []
    lines.append("=" * 60)
    lines.append("EXPENSE PROCESSING AGENT REPORT")
    lines.append("=" * 60)
    lines.append(f"Generated: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    if extras.get("summary"):
        lines.append("EXECUTIVE SUMMARY")
        lines.append("-" * 60)
        lines.append(extras["summary"])
        lines.append("")
    lines.append(f"Total expense rows      : {stats.get('total_rows')}")
    lines.append(f"Total amount ({extras.get('base_currency', 'USD')}) : "
                 f"${stats.get('total_amount', 0):,.2f}")
    lines.append(f"Expenses flagged        : {stats.get('total_flag_count')}")
    lines.append(f"Needs approval          : {stats.get('approval_required_count')}")
    lines.append(f"High fraud risk         : {stats.get('fraud_high_count', 0)}")
    lines.append("")
    lines.append("-" * 60)
    lines.append("SPEND BY CATEGORY")
    lines.append("-" * 60)
    for row in stats.get("by_category", []):
        lines.append(
            f"  {row['category']:<26} n={row['count']:<3} "
            f"total=${row['total']:>12,.2f}  max=${row['max']:>10,.2f}"
        )
    if stats.get("by_class"):
        lines.append("")
        lines.append("-" * 60)
        lines.append("EXPENSE CLASS (CAPEX / OPEX, fixed / variable)")
        lines.append("-" * 60)
        for row in stats["by_class"]:
            share = stats.get("total_amount", 1) and row["total"] / stats["total_amount"]
            lines.append(
                f"  {row['account_class']:<6}/{row['sub_class']:<9} "
                f"n={row['count']:<3} total=${row['total']:>12,.2f} "
                f"({share:>5.1%})"
            )
    if stats.get("aging"):
        lines.append("")
        lines.append("-" * 60)
        lines.append("PAYABLE AGING")
        lines.append("-" * 60)
        for bucket in stats["aging"]["buckets"]:
            lines.append(
                f"  {bucket['bucket']:<10} n={bucket['count']:<3} "
                f"total=${bucket['total']:>12,.2f}"
            )
        lines.append(f"  PAST DUE TOTAL     ${stats['aging']['past_due_total']:,.2f}")
    if extras.get("fx_exposure"):
        lines.append("")
        lines.append("-" * 60)
        lines.append("FX EXPOSURE")
        lines.append("-" * 60)
        for row in extras["fx_exposure"]:
            lines.append(
                f"  {row['currency']:<4} n={row['count']:<3} "
                f"native=${row['native_total']:>12,.2f}  "
                f"usd=${row['usd_total']:>12,.2f}"
            )
    if extras.get("benford") and extras["benford"].get("count", 0) >= 30:
        lines.append("")
        lines.append("-" * 60)
        lines.append(f"BENFORD FIRST-DIGIT CHECK "
                     f"(MAD={extras['benford'].get('mad', 0):.4f}, "
                     f"threshold=0.05, count={extras['benford'].get('count')})")
        lines.append("-" * 60)
        for row in extras.get("benford_rows", []):
            flag = " <-- " if abs(row["diff"]) > 0.05 else ""
            lines.append(
                f"  digit {row['digit']} observed={row['observed']:.3f} "
                f"expected={row['expected']:.3f}{flag}"
            )
    lines.append("")
    lines.append("-" * 60)
    lines.append("DECISION SUPPORT - ACTION ITEMS")
    lines.append("-" * 60)
    if not summary_flags:
        lines.append("  No action items. All expenses processed cleanly.")
    for item in summary_flags:
        lines.append(f"  [{item['severity']}] {item['message']}")
    lines.append("")
    lines.append("Status legend: approved = clear, review = validate, "
                 "rejected = invalid amount.")
    return "\n".join(lines)


def build_json_report(stats: dict, summary_flags: list, df: pd.DataFrame,
                      extras=None) -> dict:
    extras = extras or {}
    def pick(cols):
        existing = [c for c in cols if c in df.columns]
        return json.loads(df[existing].to_json(orient="records",
                                               date_format="iso",
                                               default_handler=str))
    payload = {
        "summary": {
            "generated_at": pd.Timestamp.now().isoformat(),
            "total_rows": stats["total_rows"],
            "total_amount": stats["total_amount"],
            "flagged_count": stats["total_flag_count"],
            "approval_required_count": stats["approval_required_count"],
            "fraud_high_count": stats.get("fraud_high_count", 0),
            "uncertain_classification_count": stats.get("uncertain_count", 0),
        },
        "by_category": stats["by_category"],
        "by_class": extras.get("expense_class", []),
        "fx_exposure": extras.get("fx_exposure", []),
        "aging": extras.get("aging", {}),
        "benford": extras.get("benford", {}),
        "executive_summary": extras.get("summary"),
        "top_risk": extras.get("top_risk", []),
        "action_items": summary_flags,
        "expenses": pick(["date", "vendor", "description", "amount", "currency",
                          "amount_usd", "category", "category_confidence",
                          "account_class", "sub_class", "terms_days", "due_date",
                          "aging_bucket", "fraud_risk_index", "flags",
                          "risk_score", "status"]),
    }
    return payload


def write_json_report(stats: dict, summary_flags: list,
                      df: pd.DataFrame, output_path: str = OUTPUT_JSON,
                      extras=None) -> str:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_json_report(stats, summary_flags, df, extras=extras)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(path)


def write_text_report(report_text: str, output_path: str = OUTPUT_TXT) -> str:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report_text, encoding="utf-8")
    return str(path)


def synthesize_action_items(df: pd.DataFrame, stats: dict) -> list:
    """Turn flags into prioritised, actionable recommendations."""
    items = []
    flagged = df[df["flags"] != ""]

    for _, row in flagged.iterrows():
        reason = row["flags"]
        if "exceeds-approval-limit" in reason:
            items.append({
                "severity": "high",
                "message": (f"Expense {row['description'][:40]} from {row['vendor']} "
                            f"of ${row['amount']:.2f} exceeds the approval limit; "
                            "route to finance manager."),
            })
        if "near-duplicate" in reason:
            items.append({
                "severity": "high",
                "message": (f"Possible duplicate charge from {row['vendor']} "
                            f"(${row['amount']:.2f}); verify receipts before payment."),
            })
        if "amount-outlier" in reason:
            items.append({
                "severity": "medium",
                "message": (f"{row['vendor']} amount ${row['amount']:.2f} is an outlier "
                            f"for category '{row['category']}'; validate justification."),
            })
        if "outside-business-hours" in reason:
            items.append({
                "severity": "low",
                "message": (f"Meal expense at {row['vendor']} outside business hours; "
                            "check policy compliance."),
            })
        if "category-cap-breach" in reason:
            cap = row.get("category_cap")
            cap_txt = f"${cap:.2f}" if pd.notna(cap) else "the policy cap"
            items.append({
                "severity": "medium",
                "message": (f"{row['vendor']} expense of ${row['amount']:.2f} exceeds "
                            f"category '{row['category']}' cap of {cap_txt}; policy breach."),
            })
        if "unapproved-vendor" in reason:
            items.append({
                "severity": "high",
                "message": (f"Vendor '{row['vendor']}' is not on the approved vendor "
                            "list; compliance review required before payment."),
            })
        if "missing-fx-rate" in reason:
            items.append({
                "severity": "medium",
                "message": (f"Row from {row['vendor']} ({row['currency']}) has no FX "
                            "rate; confirm currency/exchange rate before posting."),
            })
        if "uncertain-classification" in reason:
            items.append({
                "severity": "low",
                "message": (f"Category '{row['category']}' for {row['vendor']} "
                            f"is low confidence ({row['category_confidence']:.0f}%); "
                            "verify the GL code."),
            })
        if "high-fraud-risk" in reason:
            items.append({
                "severity": "high",
                "message": (f"{row['vendor']} ({row['description'][:30]}) scores "
                            f"FRI {row['fraud_risk_index']:.0f}/100; prioritise audit."),
            })

    # Rejected rows (non-positive amounts).
    rejected = df[df["status"] == "rejected"]
    for _, row in rejected.iterrows():
        items.append({
            "severity": "high",
            "message": f"Row for {row['vendor']} has invalid/non-positive amount "
                       f"(${row['amount']}); needs correction.",
        })

    # Cap and de-duplicate.
    seen = set()
    deduped = []
    for item in items:
        key = item["message"]
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped[:50]
