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
    cols = ["date", "vendor", "description", "amount", "category", "flags", "risk_score", "status"]
    df[cols].to_csv(path, index=False, date_format="%Y-%m-%d %H:%M")
    return str(path)


def build_text_report(stats: dict, summary_flags: list) -> str:
    lines = []
    lines.append("=" * 60)
    lines.append("EXPENSE PROCESSING AGENT REPORT")
    lines.append("=" * 60)
    lines.append(f"Generated: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    lines.append(f"Total expense rows      : {stats['total_rows']}")
    lines.append(f"Total amount            : ${stats['total_amount']:,.2f}")
    lines.append(f"Expenses flagged        : {stats['total_flag_count']}")
    lines.append(f"Needs approval          : {stats['approval_required_count']}")
    lines.append("")
    lines.append("-" * 60)
    lines.append("SPEND BY CATEGORY")
    lines.append("-" * 60)
    for row in stats["by_category"]:
        lines.append(
            f"  {row['category']:<26} n={row['count']:<3} "
            f"total=${row['total']:>12,.2f}  max=${row['max']:>10,.2f}"
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


def build_json_report(stats: dict, summary_flags: list, df: pd.DataFrame) -> dict:
    return {
        "summary": {
            "generated_at": pd.Timestamp.now().isoformat(),
            "total_rows": stats["total_rows"],
            "total_amount": stats["total_amount"],
            "flagged_count": stats["total_flag_count"],
            "approval_required_count": stats["approval_required_count"],
        },
        "by_category": stats["by_category"],
        "action_items": summary_flags,
        "expenses": json.loads(
            df[["date", "vendor", "description", "amount", "category",
                "flags", "risk_score", "status"]].to_json(
                orient="records", date_format="iso", default_handler=str)
        ),
    }


def write_json_report(stats: dict, summary_flags: list,
                      df: pd.DataFrame, output_path: str = OUTPUT_JSON) -> str:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_json_report(stats, summary_flags, df)
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
