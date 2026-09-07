# Expense Processing Agent

A working AI agent that automates the accounts-payable **invoice & expense
review** workflow for a finance team. It reads raw expense records, analyses
them against policy rules, decides an outcome for each item, and produces
reports with actionable recommendations — without a single one-off prompt.

## Business problem

Payable teams manually sift hundreds of invoices each month to:

- classify spend (travel, software, meals, ...) for budgeting and P&L,
- catch duplicate charges, unusually large amounts, and policy breaches,
- route big-ticket items (> $1,500) for manager approval,
- prevent payment of invalid (negative / zero) amounts.

This agent fully automates those steps in a single run and outputs both a
per-expense ledger and a prioritised action list for the finance analyst.

## How the agent works (4-step workflow)

| Step | Module | What it does |
|------|--------|--------------|
| 1. READ | `reader.py` | Loads a CSV, validates required columns, normalises dates/amounts, raises clear errors on bad input. |
| 2. ANALYSE | `categorizer.py`, `anomaly.py` | Assigns each expense a business category via keyword matching (with optional manual hints); runs 4 detection rules: high-amount outliers vs category median, near-duplicate charges (same vendor, same amount, 1-3 days apart), meals outside business hours, and over-threshold amounts. |
| 3. DECIDE | `anomaly.py` | Classifies each row as `approved` / `review` / `rejected` and computes a 0-100 risk score from the active flags. |
| 4. OUTPUT | `reporting.py` | Writes `processed_expenses.csv` (ledger), `agent_report.json` (machine-readable), and `agent_report.txt` (management summary + prioritised action items). |

## Quick start

```
pip install -r requirements.txt
python scripts/generate_data.py     # create sample data/data/expenses.csv
python main.py data/expenses.csv    # run the agent
python tests.py                     # verify correctness
```

## Outputs

The sample run on 47 expense rows:

- detects 6 seeded anomalies (duplicate pair, two over-$7k for approval,
  outlier, off-hours meal, negative credit), plus genuine recurring duplicates;
- flags **8 rows**, recommends **2** for manager approval, rejects **1** invalid
  credit note, and auto-approves the rest;
- reports spend by category (e.g. software_subscriptions dominate at $16.8k).

## Configuration

All policy rules live in `config.py` — outliers threshold, approval limit,
business hours, category keywords — so the agent is tunable per company policy
without touching the detection logic.

## Extending

- Drop in OCR/LLM extraction in place of `reader.py` to accept scanned PDF
  invoices.
- Add rules in `anomaly.py` (e.g. supplier not on approved-vendor list).
- Point `synthesize_action_items` at an e-mail/approval API to close the loop
  automatically.