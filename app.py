"""Streamlit web UI for the Expense Processing Agent.

Run locally:  streamlit run app.py
Deploy: push to GitHub, then create an app on https://share.streamlit.io
pointing at app.py (streamlit and pandas are in requirements.txt).
"""

import pandas as pd
import streamlit as st

from reader import InputError, read_expenses
from categorizer import assign_categories
from anomaly import analyze
from reporting import synthesize_action_items

st.set_page_config(page_title="Expense Processing Agent", page_icon=":moneybag:")
st.title("Expense Processing Agent")
st.caption("Upload invoices/expenses as CSV — the agent categorises, screens "
           "for anomalies, and recommends approvals.")

up = st.file_uploader("Upload expenses CSV", type="csv",
                      help="Requires columns: date, vendor, description, amount")

if up is not None:
    try:
        df = read_expenses(up)
        df = assign_categories(df)
        results = analyze(df)
        df_out, stats = results["df"], results["stats"]
    except InputError as exc:
        st.error(f"Input error: {exc}")
        st.stop()

    action_items = synthesize_action_items(df_out, stats)

    st.subheader("Overview")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Rows", stats["total_rows"])
    c2.metric("Total spend", f"${stats['total_amount']:,.2f}")
    c3.metric("Flagged", stats["total_flag_count"])
    c4.metric("Approvals", stats["approval_required_count"])

    st.subheader("Spend by category")
    cat = pd.DataFrame(stats["by_category"])
    st.bar_chart(cat.set_index("category")["total"])

    st.subheader("Expense ledger")
    cols = ["date", "vendor", "description", "amount", "category",
            "flags", "risk_score", "status"]
    st.dataframe(df_out[cols], use_container_width=True, hide_index=True)

    st.subheader("Action items")
    if action_items:
        for item in action_items:
            st.warning(f"[{item['severity'].upper()}] {item['message']}")
    else:
        st.success("No action items — all expenses processed cleanly.")

    st.download_button(
        "Download processed CSV",
        df_out[cols].to_csv(index=False).encode("utf-8"),
        file_name="processed_expenses.csv",
        mime="text/csv",
    )
else:
    st.info("Upload a CSV to get started. Sample data: `python "
            "scripts/generate_data.py` writes `data/expenses.csv`.")