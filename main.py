"""Expense Processing Agent - main entry point.

This agent automates an invoice/expense review workflow:

  1. READ     - load raw expense records from CSV
  2. ANALYSE  - categorise spend, detect anomalies and policy breaches
  3. DECIDE   - classify each expense as approved / review / rejected and
                compute a risk score
  4. OUTPUT   - write a CSV ledger, a human-readable report and a
                machine-readable JSON report with action items

Usage:
    python main.py [input.csv]   (defaults to data/expenses.csv)

Exit codes:
    0 - completed successfully
    1 - input error
"""

import sys
from pathlib import Path

from config import *
from anomaly import analyze
from categorizer import assign_categories
from reader import InputError, read_expenses
from reporting import (
    synthesize_action_items,
    write_csv,
    write_json_report,
    write_text_report,
)

DEFAULT_INPUT = "data/expenses.csv"


def run_pipeline(input_path: str) -> int:
    """Execute the full agent workflow and return a process exit code."""
    print("[1/4] READ: loading expenses from", input_path)
    df = read_expenses(input_path)

    print("[2/4] ANALYSE: categorising and checking for anomalies...")
    df = assign_categories(df)
    results = analyze(df)

    print("[3/4] DECIDE: classifying and scoring each expense...")
    df = results["df"]
    stats = results["stats"]
    action_items = synthesize_action_items(df, stats)

    print("[4/4] OUTPUT: writing reports...")
    csv_path = write_csv(df)
    txt_path = write_text_report(_build_text_report(stats, action_items))
    json_path = write_json_report(stats, action_items, df)

    _print_summary(stats, action_items)
    print(f"\nOutput files:\n  CSV : {csv_path}\n  TXT : {txt_path}\n  JSON: {json_path}")
    return 0


def _build_text_report(stats, action_items) -> str:
    from reporting import build_text_report
    return build_text_report(stats, action_items)


def _print_summary(stats, action_items):
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Rows processed      : {stats['total_rows']}")
    print(f"Total spend         : ${stats['total_amount']:,.2f}")
    print(f"Flagged for review  : {stats['total_flag_count']}")
    print(f"Approvals required  : {stats['approval_required_count']}")
    print(f"Action items        : {len(action_items)}")
    print("=" * 60)


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    input_path = argv[0] if argv else DEFAULT_INPUT
    if not Path(input_path).exists():
        print(f"ERROR: input file not found: {input_path}", file=sys.stderr)
        print("Run `python scripts/generate_data.py` to create sample data.", file=sys.stderr)
        return 1
    try:
        return run_pipeline(input_path)
    except InputError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())