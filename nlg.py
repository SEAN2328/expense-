"""Executive summary generator.

Turns the structured analysis into a short natural-language brief that a
finance manager can read without opening spreadsheets. Template-based by
default; a pluggable LLM provider can be swapped in later.
"""


def executive_summary(df, stats, extras) -> str:
    top_cat = stats["by_category"][0]["category"] if stats["by_category"] else "n/a"
    fx = extras.get("fx_exposure", [])
    aging = extras.get("aging", {})
    benford = extras.get("benford", {})
    class_stats = extras.get("class_stats", [])
    capex_rows = sum(c.get("count", 0) for c in class_stats
                     if c.get("account_class") == "CAPEX")

    sentences = []
    sentences.append(
        f"This period processed {stats['total_rows']} expense rows totalling "
        f"${stats['total_amount']:,.2f}, with {stats['approval_required_count']} "
        f"requiring manager approval and {stats['total_flag_count']} flagged for review."
    )
    sentences.append(
        f"Spend is led by {top_cat} (${stats['by_category'][0]['total']:,.2f}); "
        f"{capex_rows} line items classify as capital expenditure."
    )
    if fx:
        non_base = [e for e in fx if e["usd_total"] > 0 and e["currency"] != "USD"]
        if non_base:
            labels = ", ".join(f"{e['currency']} {e['usd_total']:,.0f}USD"
                               for e in non_base[:3])
            sentences.append(f"Currency exposure beyond USD: {labels}.")
    if aging:
        sentences.append(
            f"Payables aging shows ${aging.get('past_due_total', 0):,.2f} past due."
        )
    if benford.get("alert"):
        sentences.append(
            "A Benford first-digit deviation was flagged on invoice amounts; "
            "recommend a focused audit of this batch."
        )
    high = df[df["high_fraud_risk"]] if "high_fraud_risk" in df.columns else None
    if high is not None and not high.empty:
        sentences.append(
            f"{len(high)} charges exceed the fraud-risk threshold and should be "
            "reviewed first."
        )
    return " ".join(sentences)