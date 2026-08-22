from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from src.analysis import audit, concentration, exporter_table, hs8_table, load_excel, normalize, strategic_screen

st.set_page_config(page_title="Pakistan Export Intelligence", page_icon="📊", layout="wide")
st.title("Pakistan Export Intelligence — Chapter 12 Pilot")
st.caption("TDAP exporter-level decision dashboard. Values are reported values from the supplied extract; period and national-share caveats are shown explicitly.")

DEFAULT_FILE = Path("Chapter_12.xlsx")

with st.sidebar:
    st.header("Data source")
    use_repo_file = DEFAULT_FILE.exists()
    uploaded = st.file_uploader("Upload/replace chapter workbook", type=["xlsx", "xlsm", "xls"])
    if uploaded is not None:
        source = uploaded
        st.success(f"Using uploaded file: {uploaded.name}")
    elif use_repo_file:
        source = DEFAULT_FILE
        st.success("Using repository file: Chapter_12.xlsx")
    else:
        st.warning("No repository workbook found. Upload a TDAP chapter workbook.")
        st.stop()
    st.divider()
    st.markdown("**Interpretation guardrails**")
    st.caption("Reported record count ≠ physical quantity. Value/record ≠ unit price. Extract shares ≠ national export shares unless reconciled to national data.")

raw, sheet = load_excel(source)
df = normalize(raw)
a = audit(df)

if a.missing_required:
    st.error("Cannot proceed. Missing required fields: " + ", ".join(a.missing_required))
    st.stop()

c = concentration(df)
exporters = exporter_table(df)
hs8 = hs8_table(df)
screen = strategic_screen(df)

chapter_label = ", ".join(a.chapters) if a.chapters else "Unknown"
st.success(f"Loaded sheet **{sheet}** · HS chapter **{chapter_label}** · {a.rows:,} source rows · {a.unique_exporters:,} exporters")

# Global filters
with st.expander("Filters and search", expanded=False):
    q = st.text_input("Search exporter / NTN / email / phone", placeholder="e.g., company name, NTN, email or phone")
    top_n = st.slider("Rows to show in ranking charts", 10, min(100, max(10, len(exporters))), min(25, max(10, len(exporters))))

filtered_exporters = exporters.copy()
if q.strip():
    search_cols = [c for c in ["exporter_name", "ntn", "email", "telephone", "address"] if c in filtered_exporters]
    mask = pd.Series(False, index=filtered_exporters.index)
    for col in search_cols:
        mask |= filtered_exporters[col].astype("string").str.contains(q.strip(), case=False, na=False)
    filtered_exporters = filtered_exporters[mask]

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "Executive overview",
    "Exporter ranking & contacts",
    "HS8 landscape",
    "Strategic screen",
    "Due diligence",
    "Methodology",
])

with tab1:
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("TDAP reported value", f"Rs {c['total_value_rs']/1e9:,.2f} bn")
    k2.metric("Exporters", f"{a.unique_exporters:,}")
    k3.metric("HS8 lines", f"{a.unique_hs8:,}")
    k4.metric("Top 10 share", f"{c['top10_share']:.1%}")
    k5.metric("Firms to 60%", f"{c['exporters_to_60pct']:,}")
    k6.metric("HHI", f"{c['hhi']:,.0f}")

    st.subheader("Concentration of reported chapter value")
    thresholds = pd.DataFrame({
        "Threshold": ["25%", "50%", "60%", "80%", "90%"],
        "Exporters required": [c["exporters_to_25pct"], c["exporters_to_50pct"], c["exporters_to_60pct"], c["exporters_to_80pct"], c["exporters_to_90pct"]],
    })
    st.dataframe(thresholds, hide_index=True, use_container_width=True)

    fig = px.bar(
        exporters.head(top_n).sort_values("reported_value_rs"),
        x="reported_value_rs", y="exporter_name", orientation="h",
        hover_data=["rank", "share", "cumulative_share", "ntn"] if "ntn" in exporters else ["rank", "share", "cumulative_share"],
        title=f"Top {top_n} exporters by TDAP reported value",
    )
    st.plotly_chart(fig, use_container_width=True)

    pareto = exporters[["rank", "cumulative_share"]].copy()
    pareto["cumulative_share_pct"] = pareto["cumulative_share"] * 100
    st.plotly_chart(px.line(pareto, x="rank", y="cumulative_share_pct", title="Exporter concentration — cumulative reported value share"), use_container_width=True)
    st.info("Board interpretation: ranking and shares are calculated within this supplied TDAP Chapter 12 extract. They should not be described as Pakistan national export shares until reconciled against national trade data.")

with tab2:
    st.subheader("Exporter ranking & communication directory")
    st.write("Search, sort and export the table. Ranking is based on TDAP reported value in the supplied chapter extract.")
    ranking_cols = [c for c in [
        "rank", "exporter_name", "ntn", "reported_value_rs", "share", "cumulative_share",
        "record_count", "avg_value_per_reported_record_rs", "hs8_count", "hs4_count", "largest_hs8",
        "email", "telephone", "address"
    ] if c in filtered_exporters]
    st.dataframe(
        filtered_exporters[ranking_cols],
        hide_index=True,
        use_container_width=True,
        height=650,
        column_config={
            "rank": "Rank",
            "exporter_name": "Exporter",
            "ntn": "NTN",
            "reported_value_rs": st.column_config.NumberColumn("TDAP reported value (Rs)", format="%,.0f"),
            "share": st.column_config.NumberColumn("Chapter extract share", format="%.2%%"),
            "cumulative_share": st.column_config.NumberColumn("Cumulative share", format="%.2%%"),
            "record_count": st.column_config.NumberColumn("Reported record count", format="%,.0f"),
            "avg_value_per_reported_record_rs": st.column_config.NumberColumn("Avg value / reported record (Rs)", format="%,.0f", help="Descriptive TDAP value per reported record. This is NOT physical unit value."),
            "hs8_count": "HS8 breadth",
            "hs4_count": "HS4 breadth",
            "largest_hs8": "Largest HS8",
            "email": "Email",
            "telephone": "Telephone",
            "address": "Address",
        },
    )
    st.download_button(
        "Download exporter ranking & contacts CSV",
        filtered_exporters[ranking_cols].to_csv(index=False).encode("utf-8-sig"),
        "chapter12_exporter_ranking_contacts.csv",
        "text/csv",
    )

with tab3:
    st.subheader("HS8 capability landscape")
    st.dataframe(
        hs8,
        hide_index=True,
        use_container_width=True,
        column_config={
            "reported_value_rs": st.column_config.NumberColumn(format="%,.0f"),
            "share": st.column_config.NumberColumn(format="%.2%%"),
            "cumulative_share": st.column_config.NumberColumn(format="%.2%%"),
        },
    )
    fig = px.scatter(hs8, x="exporters", y="reported_value_rs", size="reported_value_rs", hover_name="hs8", hover_data=["product_name"], log_y=True, title="HS8 scale vs number of participating exporters")
    st.plotly_chart(fig, use_container_width=True)

with tab4:
    st.subheader("Evidence-based strategic screen")
    st.write("First-pass screening combines reported scale with relative scarcity of the HS8 capability. It deliberately excludes destination, growth, unit-price and geopolitical claims that the source cannot support.")
    st.dataframe(
        screen.head(200), hide_index=True, use_container_width=True,
        column_config={
            "capability_score": st.column_config.NumberColumn(format="%.1f"),
            "exported_value_rs": st.column_config.NumberColumn(format="%,.0f"),
        }
    )
    st.download_button("Download strategic screen CSV", screen.to_csv(index=False).encode("utf-8-sig"), "chapter12_strategic_screen.csv", "text/csv")

with tab5:
    st.subheader("Data due diligence")
    checks = pd.DataFrame({
        "Check": ["Rows", "Columns", "Duplicate rows", "Invalid HS8", "Non-positive/missing export value", "Unique exporters", "Unique NTNs", "Unique HS8", "HS2 chapters"],
        "Result": [a.rows, a.columns, a.duplicate_rows, a.invalid_hs8, a.nonpositive_values, a.unique_exporters, a.unique_ntns, a.unique_hs8, chapter_label],
    })
    st.dataframe(checks, hide_index=True, use_container_width=True)
    st.subheader("Caveats carried into every interpretation")
    for warning in a.warnings:
        st.warning(warning)

with tab6:
    st.subheader("How to read this dashboard")
    st.markdown("""
**Observed from TDAP extract**: exporter identity, HS8 product, reported export value, reported record count and contact fields where supplied.

**Derived by this application**: rank, extract share, cumulative share, HHI, firms required to reach concentration thresholds, HS8 breadth, HS4 breadth, and screening indicators.

**Not established by this file alone**: physical unit value, shipment quantity, export destination, new-market entry, national market share, global demand growth, tariff advantage or geopolitical fit.

**Privacy/access**: this dashboard contains business contact information and NTNs. Deploy it as a private/controlled-access application unless your organization explicitly approves wider publication.
""")

st.divider()
st.caption("Next layer after this pilot is validated: PBS HS8 × country × quantity/value/time enrichment, followed by global market and policy data. Firm attribution and national totals remain analytically separated unless a defensible linkage is established.")
