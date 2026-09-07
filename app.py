"""Streamlit web UI for the Expense Processing Agent.

Run locally:  streamlit run app.py
Deploy: push to GitHub, then create an app on http://share.streamlit.io
pointing at app.py (streamlit and pandas are in requirements.txt).
"""

import io
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
from config import (APPROVAL_THRESHOLD, CATEGORY_CAPS, DEFAULT_BUDGET,
                    FORECAST_DAYS)
from modern import enrich
from reader import InputError, read_expenses
from reporting import synthesize_action_items


def _text_report(stats, action_items, extras) -> str:
    from reporting import build_text_report
    return build_text_report(stats, action_items, extras)

st.set_page_config(page_title="Expense Processing Agent", page_icon=":moneybag:",
                   layout="wide")
st.title("Expense Processing Agent")
st.caption("Upload invoices/expenses as CSV - the agent categorises, screens "
           "for anomalies, policy breaches & fraud signals, and recommends "
           "approvals.")

LEDGER_COLS = ["date", "vendor", "description", "currency", "amount",
               "amount_usd", "category", "account_class", "sub_class",
               "flags", "fraud_risk_index", "risk_score", "status"]


@st.cache_data(show_spinner=False)
def process(upload_bytes: bytes, approval_threshold: float,
            outlier_multiplier: float, caps_json: str,
            screen_vendors: bool) -> tuple:
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
    df, stats, extras = enrich(results["df"], results["stats"])
    cat_table = pd.DataFrame(stats["by_category"])
    return df, stats, extras, cat_table


with st.sidebar:
    st.header("Policy settings")
    approval_threshold = st.number_input("Approval threshold ($)",
                                         value=APPROVAL_THRESHOLD,
                                         min_value=0.0, step=50.0)
    outlier_multiplier = st.number_input("Outlier multiplier (x median)",
                                         value=3.0, min_value=1.0, step=0.5)
    caps_json = st.text_area("Category caps (JSON)", value=json.dumps(CATEGORY_CAPS),
                             height=180,
                             help='Per-category policy caps, e.g. {"meals_entertainment": 75}')
    screen_vendors = st.checkbox("Screen for unapproved vendors", value=True)
    budget_json = st.text_area("Monthly budget (JSON, optional)",
                               value=json.dumps(DEFAULT_BUDGET), height=140)
    st.divider()
    st.caption(f"Forecast horizon: {FORECAST_DAYS} days | Base: USD")

up = st.file_uploader("Upload expenses CSV", type="csv",
                      help="Requires columns: date, vendor, description, amount. "
                           "Optional: currency, category_hint")

if up is not None:
    try:
        df, stats, extras, cat_table = process(
            up.getvalue(), approval_threshold, outlier_multiplier, caps_json,
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

    action_items = synthesize_action_items(df, stats)
    forecast = forecast_next_period(df)
    concentration = vendor_concentration(df)
    report_txt = _text_report(stats, action_items, extras)

    tab_exec, tab_ledger, tab_class, tab_fraud, tab_finance = st.tabs(
        ["Executive", "Ledger", "Classification", "Fraud & Risk", "Finance"])

    with tab_exec:
        st.subheader("Executive summary")
        st.write(extras["summary"])
        st.divider()
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Rows", stats["total_rows"])
        c2.metric("Total spend (USD)", f"${stats['total_amount']:,.2f}")
        c3.metric("Flagged", stats["total_flag_count"])
        c4.metric("Approvals", stats["approval_required_count"])
        c5.metric("Forecast 30d", f"${forecast['forecast']:,.0f}")
        st.divider()

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Cash-flow trend**")
            weekly = weekly_spend_series(df)
            if not weekly.empty:
                st.line_chart(weekly, height=240)
                st.caption(f"Next {FORECAST_DAYS}d ~${forecast['forecast']:,.0f} "
                           f"(trend {forecast['trend']:+.1f}%/wk).")
        with c2:
            st.markdown("**Spend by category**")
            if not cat_table.empty:
                st.bar_chart(cat_table.set_index("category")["total"], height=240)

        st.divider()
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

    with tab_ledger:
        st.subheader("Expense ledger")
        f1, f2, f3, f4 = st.columns(4)
        text_search = f1.text_input("Search", placeholder="vendor or description")
        cat_filter = f2.multiselect("Category",
                                    sorted(df["category"].unique()),
                                    default=list(df["category"].unique()))
        status_filter = f3.multiselect("Status",
                                       ["approved", "review", "rejected"],
                                       default=["approved", "review", "rejected"])
        aclass_filter = f4.multiselect("Class",
                                       ["CAPEX", "OPEX"],
                                       default=["CAPEX", "OPEX"])
        view = df[(df["category"].isin(cat_filter))
                  & (df["status"].isin(status_filter))
                  & (df["account_class"].isin(aclass_filter))]
        if text_search:
            m = (view["vendor"].str.lower().str.contains(text_search.lower(), na=False)
                 | view["description"].str.lower().str.contains(text_search.lower(), na=False))
            view = view[m]
        st.dataframe(
            view[LEDGER_COLS].assign(
                amount=view["amount"].map("${:,.2f}".format),
                amount_usd=view["amount_usd"].map("${:,.2f}".format)),
            width="stretch", hide_index=True,
            column_config={"date": st.column_config.DatetimeColumn(format="MMM D, YYYY - HH:mm")})

    with tab_class:
        st.subheader("Expense classification")
        class_df = pd.DataFrame(extras["expense_class"])
        if not class_df.empty:
            c1, c2 = st.columns([2, 2])
            with c1:
                st.markdown("**CAPEX / OPEX split**")
                st.bar_chart(class_df.groupby("account_class")["total"].sum(), height=240)
            with c2:
                st.markdown("**Cost behaviour (fixed / variable)**")
                st.bar_chart(class_df.groupby("sub_class")["total"].sum(), height=240)
            st.dataframe(
                class_df.style.format({"total": "${:,.0f}"}),
                width="stretch", hide_index=True)
        unc = df[df["uncertain_classification"]]
        st.metric("Uncertain classifications", len(unc))
        if not unc.empty:
            st.warning("Low-confidence GL tags: "
                       + ", ".join(f"{r['vendor']} ({r['category']})"
                                   for _, r in unc.iterrows()))

    with tab_fraud:
        st.subheader("Fraud & statistical signals")
        mr1, mr2, mr3 = st.columns(3)
        mr1.metric("High fraud-risk rows", stats.get("fraud_high_count", 0))
        mr2.metric("High-risk (FRI>65)", stats.get("fraud_high_count", 0))
        mr3.metric("Uncertain tags", stats.get("uncertain_count", 0))

        benford = extras.get("benford", {})
        if benford.get("count", 0) >= 30:
            bra = pd.DataFrame(extras.get("benford_rows", []))
            st.markdown(f"**Benford's law check** (MAD={benford.get('mad', 0):.4f}, "
                        f"threshold 0.05)")
            if benford.get("alert"):
                st.error("First-digit deviation exceeds tolerance - recommend "
                         "focused audit.")
            if not bra.empty:
                st.line_chart(bra.set_index("digit")[["observed", "expected"]],
                              height=240)
        else:
            st.info("Benford check needs >= 30 amount observations "
                    f"(currently {benford.get('count', 0)}).")

        st.markdown("**Top fraud-risk rows**")
        tr = pd.DataFrame(extras.get("top_risk", []))
        if not tr.empty:
            st.dataframe(
                tr[["vendor", "description", "amount_usd", "category",
                    "fraud_risk_index", "flags"]]
                .assign(amount_usd=tr["amount_usd"].map("${:,.2f}".format)),
                width="stretch", hide_index=True,
                column_config={"amount_usd": st.column_config.NumberColumn(format="%.2f")})

    with tab_finance:
        st.subheader("Vendor concentration")
        conc = pd.DataFrame(concentration["vendors"])
        cl, cr = st.columns([2, 3])
        with cl:
            if not conc.empty:
                st.bar_chart(conc.head(8).set_index("vendor")["amount"], height=240)
        with cr:
            if concentration["alerts"]:
                st.error("Concentration alert: "
                         + ", ".join(f"{a['vendor']} ({a['share']:.0%})"
                                     for a in concentration["alerts"]))
            if not conc.empty:
                st.dataframe(conc.head(8)[["vendor", "amount", "share"]]
                             .style.format({"amount": "${:,.2f}", "share": "{:.1%}"}),
                             width="stretch", hide_index=True)

        st.divider()
        st.subheader("FX exposure")
        fxdf = pd.DataFrame(extras.get("fx_exposure", []))
        if not fxdf.empty:
            st.dataframe(fxdf[["currency", "count", "native_total", "usd_total"]]
                         .style.format({"native_total": "${:,.2f}", "usd_total": "${:,.2f}"}),
                         width="stretch", hide_index=True)
        else:
            st.info("All rows were in the base currency.")

        st.divider()
        st.subheader("Payables aging")
        aging = extras.get("aging", {})
        buckets = pd.DataFrame(aging.get("buckets", []))
        if not buckets.empty:
            c1, c2 = st.columns([2, 3])
            with c1:
                st.bar_chart(buckets.set_index("bucket")["total"], height=240)
            with c2:
                st.dataframe(buckets.style.format({"total": "${:,.2f}"}),
                             width="stretch", hide_index=True)
                st.metric("Past due total",
                          f"${aging.get('past_due_total', 0):,.2f}")

        if budget:
            st.divider()
            st.subheader("Budget vs actual")
            bva = pd.DataFrame(budget_vs_actual(df, budget))
            if not bva.empty:
                st.dataframe(bva[["category", "budget", "actual", "variance"]]
                             .style.format({"budget": "${:,.0f}",
                                            "actual": "${:,.0f}",
                                            "variance": "${:,.0f}"}),
                             width="stretch", hide_index=True)
                overspent = bva[bva["overspend"]]
                if not overspent.empty:
                    st.warning("Overspent: " + ", ".join(overspent["category"]))

    st.divider()
    dl1, dl2, dl3, dl4 = st.columns(4)
    dl1.download_button("Download processed CSV",
                        df.to_csv(index=False).encode("utf-8"),
                        "processed_expenses.csv", "text/csv")
    ai_df = pd.DataFrame(action_items)
    dl2.download_button("Download action items",
                        ai_df.to_csv(index=False).encode("utf-8"),
                        "action_items.csv", "text/csv",
                        disabled=ai_df.empty)
    dl3.download_button("Download JSON report",
                        json.dumps({"summary": stats, "executive_summary":
                                    extras["summary"], "expense_class":
                                    extras["expense_class"], "aging":
                                    extras["aging"], "benford":
                                    extras["benford"], "top_risk":
                                    extras["top_risk"], "action_items":
                                    action_items}, indent=2, default=str),
                        "agent_report.json", "application/json")
    dl4.download_button("Download TXT report",
                        report_txt.encode("utf-8"),
                        "agent_report.txt", "text/plain")
else:
    st.info("Upload a CSV to get started. Sample data: `python "
            "scripts/generate_data.py` writes `data/expenses.csv`.")