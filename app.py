"""Streamlit web UI for the Expense Processing Agent.

Run locally:  streamlit run app.py
Deploy: push to GitHub, then create an app on http://share.streamlit.io
pointing at app.py (streamlit and pandas are in requirements.txt).
"""

import json

import pandas as pd
import streamlit as st

from analytics import (  # noqa: E402
    budget_vs_actual,
    flag_breakdown,
    forecast_next_period,
    vendor_concentration,
    weekly_spend_series,
)
from anomaly import analyze
from categorizer import assign_categories
from config import APPROVAL_THRESHOLD, CATEGORY_CAPS, DEFAULT_BUDGET, FORECAST_DAYS
from reader import InputError, read_expenses
from reporting import synthesize_action_items

st.set_page_config(page_title="Expense Processing Agent", page_icon=":moneybag:",
                   layout="wide")
st.title("Expense Processing Agent")
st.caption("Upload invoices/expenses as CSV - the agent categorises, screens "
           "for anomalies & policy breaches, and recommends approvals.")

LEDGER_COLS = ["date", "vendor", "description", "amount", "category",
               "flags", "risk_score", "status"]


@st.cache_data(show_spinner=False)
def process(upload_bytes: bytes, approval_threshold: float, outlier_multiplier: float,
            caps_json: str, screen_vendors: bool) -> tuple:
    import io

    df = read_expenses(io.BytesIO(upload_bytes))
    df = assign_categories(df)

    caps = json.loads(caps_json) if caps_json.strip() else None
    vendors = None
    if screen_vendors:
        from config import APPROVED_VENDORS
        vendors = APPROVED_VENDORS

    results = analyze(df, approval_threshold=approval_threshold,
                      outlier_multiplier=outlier_multiplier,
                      category_caps=caps, approved_vendors=vendors)
    df_out = results["df"]
    stats = results["stats"]
    tf = pd.DataFrame(stats["by_category"])
    return df_out, stats, tf


with st.sidebar:
    st.header("Policy settings")
    approval_threshold = st.number_input("Approval threshold ($)", value=APPROVAL_THRESHOLD,
                                         min_value=0.0, step=50.0)
    outlier_multiplier = st.number_input("Outlier multiplier (x median)",
                                         value=3.0, min_value=1.0, step=0.5)
    caps_default = json.dumps(CATEGORY_CAPS)
    caps_json = st.text_area("Category caps (JSON)", value=caps_default,
                             height=180,
                             help="Per-category per-expense policy caps, e.g. "
                                  '{"meals_entertainment": 75}')
    screen_vendors = st.checkbox("Screen for unapproved vendors", value=True)
    budget_json = st.text_area("Monthly budget (JSON, optional)",
                               value=json.dumps(DEFAULT_BUDGET), height=140,
                               help='{"software_subscriptions": 15000}')

    st.divider()
    st.caption("Forecast horizon: %d days" % FORECAST_DAYS)

up = st.file_uploader("Upload expenses CSV", type="csv",
                      help="Requires columns: date, vendor, description, amount")

if up is not None:
    try:
        df_out, stats, cat_table = process(up.getvalue(), approval_threshold,
                                           outlier_multiplier, caps_json,
                                           screen_vendors)
    except (InputError, ValueError) as exc:
        st.error(f"Input error: {exc}")
        st.stop()

    try:
        budget = json.loads(budget_json) if budget_json.strip() else None
        if not isinstance(budget, dict):
            budget = None
    except json.JSONDecodeError:
        budget = None
        st.warning("Budget JSON could not be parsed; showing actual spend only.")

    action_items = synthesize_action_items(df_out, stats)
    forecast = forecast_next_period(df_out)
    concentration = vendor_concentration(df_out)

    st.subheader("Overview")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Rows", stats["total_rows"])
    c2.metric("Total spend", f"${stats['total_amount']:,.2f}")
    c3.metric("Flagged", stats["total_flag_count"])
    c4.metric("Approvals", stats["approval_required_count"])
    c5.metric("Forecast 30d", f"${forecast['forecast']:,.0f}")

    st.subheader("Cash-flow trend")
    weekly = weekly_spend_series(df_out)
    if not weekly.empty:
        st.line_chart(weekly, height=260)
        trend = forecast["trend"]
        st.caption(f"Linear-trend cash-flow forecast: next {FORECAST_DAYS} days "
                   f"~${forecast['forecast']:,.0f} "
                   f"(trend {trend:+.1f}%/week, {forecast['confidence']}).")

    st.subheader("Spend by category")
    if not cat_table.empty:
        st.bar_chart(cat_table.set_index("category")["total"], height=260)

    st.subheader("Flag breakdown")
    fb = flag_breakdown(stats)
    if fb.empty:
        st.success("No flags raised.")
    else:
        st.bar_chart(fb.set_index("flag")["count"], height=220)

    st.subheader("Vendor concentration")
    conc = pd.DataFrame(concentration["vendors"])
    c_left, c_right = st.columns([2, 3])
    with c_left:
        if not conc.empty:
            st.bar_chart(conc.head(8).set_index("vendor")["amount"], height=260)
    with c_right:
        if concentration["alerts"]:
            st.error("Concentration alert: "
                     + ", ".join(f"{a['vendor']} ({a['share']:.0%})"
                                 for a in concentration["alerts"]))
        st.dataframe(conc.head(8)[["vendor", "amount", "share"]]
                     .style.format({"amount": "${:,.2f}", "share": "{:.1%}"}),
                     width="stretch", hide_index=True)

    if budget:
        st.subheader("Budget vs actual")
        bva = pd.DataFrame(budget_vs_actual(df_out, budget))
        if not bva.empty:
            bva_disp = bva[["category", "budget", "actual", "variance"]]
            bva_disp = bva_disp.style.format(
                {"budget": "${:,.0f}", "actual": "${:,.0f}", "variance": "${:,.0f}"})
            st.dataframe(bva_disp, width="stretch", hide_index=True)
            overspent = bva[bva["overspend"]]
            if not overspent.empty:
                st.warning("Overspent categories: "
                           + ", ".join(overspent["category"]))

    st.subheader("Expense ledger")
    f1, f2, f3 = st.columns(3)
    text_search = f1.text_input("Search", placeholder="vendor or description")
    cat_filter = f2.multiselect("Category", sorted(df_out["category"].unique()),
                                default=list(df_out["category"].unique()))
    status_filter = f3.multiselect("Status", ["approved", "review", "rejected"],
                                   default=["approved", "review", "rejected"])
    view = df_out[(df_out["category"].isin(cat_filter))
                  & (df_out["status"].isin(status_filter))]
    if text_search:
        mask = (view["vendor"].str.lower().str.contains(text_search.lower(), na=False)
                | view["description"].str.lower().str.contains(text_search.lower(), na=False))
        view = view[mask]
    st.dataframe(view[LEDGER_COLS].assign(
        amount=view["amount"].map("${:,.2f}".format)),
        width="stretch", hide_index=True,
        column_config={"date": st.column_config.DatetimeColumn(format="MMM D, YYYY - HH:mm")})

    st.subheader("Action items")
    if action_items:
        for item in action_items:
            sev = item["severity"].upper()
            if sev == "HIGH":
                st.error(f"[{sev}] {item['message']}")
            elif sev == "MEDIUM":
                st.warning(f"[{sev}] {item['message']}")
            else:
                st.info(f"[{sev}] {item['message']}")
    else:
        st.success("No action items - all expenses processed cleanly.")

    st.divider()
    dl1, dl2, dl3 = st.columns(3)
    dl1.download_button("Download processed CSV",
                        df_out[LEDGER_COLS].to_csv(index=False).encode("utf-8"),
                        "processed_expenses.csv", "text/csv")
    ai_df = pd.DataFrame(action_items)
    dl2.download_button("Download action items",
                        ai_df.to_csv(index=False).encode("utf-8"),
                        "action_items.csv", "text/csv",
                        disabled=ai_df.empty)
    dl3.download_button("Download JSON report",
                        json.dumps({
                            "summary": stats,
                            "forecast": forecast,
                            "concentration": concentration,
                            "action_items": action_items,
                        }, indent=2, default=str),
                        "agent_report.json", "application/json")
else:
    st.info("Upload a CSV to get started. Sample data: `python "
            "scripts/generate_data.py` writes `data/expenses.csv`.")