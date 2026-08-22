from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from src.analysis import audit, concentration, exporter_table, hs8_table, load_excel, normalize, strategic_screen

st.set_page_config(page_title="Pakistan Export Deep Dive", page_icon="📊", layout="wide")
st.title("Pakistan Export Deep Dive — Chapter Pilot")
st.caption("Decision-support dashboard for TDAP exporter-directory extracts. Chapter 12 is the pilot; the engine is reusable across chapters.")

with st.sidebar:
    st.header("Input")
    uploaded = st.file_uploader("Upload TDAP Excel workbook", type=["xlsx", "xlsm", "xls"])
    st.info("Use the raw exporter × HS8 sheet where possible. The app performs a schema audit before analysis.")

if uploaded is None:
    st.subheader("Ready for Chapter 12")
    st.write("Upload **chapter 12 DD.xlsx** to run the complete due-diligence and analytical pipeline. No data is sent by this repository anywhere; processing occurs in the running Streamlit session.")
    st.stop()

raw, sheet = load_excel(uploaded)
df = normalize(raw)
a = audit(df)

st.success(f"Loaded sheet: {sheet} — {a.rows:,} rows × {a.columns:,} columns")

if a.missing_required:
    st.error("Cannot proceed. Missing required fields: " + ", ".join(a.missing_required))
    st.stop()

c = concentration(df)
exporters = exporter_table(df)
hs8 = hs8_table(df)
screen = strategic_screen(df)

tab1, tab2, tab3, tab4, tab5 = st.tabs(["Executive", "Due diligence", "Exporters", "HS8 landscape", "Strategic screen"])

with tab1:
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Reported value", f"Rs {c['total_value_rs']/1e9:,.2f} bn")
    k2.metric("Exporters", f"{a.unique_exporters:,}")
    k3.metric("HS8 lines", f"{a.unique_hs8:,}")
    k4.metric("Top 10 share", f"{c['top10_share']:.1%}")
    k5.metric("Firms to 60%", f"{c['exporters_to_60pct']:,}")
    st.plotly_chart(px.bar(exporters.head(20), x="reported_value_rs", y="exporter_name", orientation="h", title="Top 20 exporters by TDAP reported value").update_layout(yaxis={"categoryorder":"total ascending"}), use_container_width=True)
    st.plotly_chart(px.bar(hs8.head(20), x="hs8", y="reported_value_rs", hover_data=["product_name", "exporters"], title="Leading HS8 product lines"), use_container_width=True)
    st.warning("These are extract-level results. They are not automatically national export-market shares.")

with tab2:
    st.subheader("Data due diligence")
    checks = pd.DataFrame({
        "Check": ["Rows", "Columns", "Duplicate rows", "Invalid HS8", "Non-positive/missing export value", "Unique exporters", "Unique NTNs", "Unique HS8", "HS2 chapters"],
        "Result": [a.rows, a.columns, a.duplicate_rows, a.invalid_hs8, a.nonpositive_values, a.unique_exporters, a.unique_ntns, a.unique_hs8, ", ".join(a.chapters)],
    })
    st.dataframe(checks, hide_index=True, use_container_width=True)
    st.subheader("Analytical caveats")
    for warning in a.warnings:
        st.warning(warning)
    st.markdown("**Not measurable from this extract alone:** destination diversification, new-market entry, time-series growth, true physical unit value, geopolitical exposure, national market share, and firm diversification when only one HS8 is retained per firm.")

with tab3:
    st.subheader("Exporter concentration")
    st.write(f"HHI: **{c['hhi']:,.0f}** · Top 1: **{c['top1_share']:.1%}** · Top 5: **{c['top5_share']:.1%}** · Top 10: **{c['top10_share']:.1%}**")
    st.dataframe(exporters, hide_index=True, use_container_width=True, column_config={"share": st.column_config.NumberColumn(format="%.2%%"), "cumulative_share": st.column_config.NumberColumn(format="%.2%%"), "reported_value_rs": st.column_config.NumberColumn(format="%,.0f")})

with tab4:
    st.subheader("HS8 capability landscape")
    st.dataframe(hs8, hide_index=True, use_container_width=True, column_config={"share": st.column_config.NumberColumn(format="%.2%%"), "cumulative_share": st.column_config.NumberColumn(format="%.2%%"), "reported_value_rs": st.column_config.NumberColumn(format="%,.0f")})
    fig = px.scatter(hs8, x="exporters", y="reported_value_rs", size="reported_value_rs", hover_name="hs8", hover_data=["product_name"], log_y=True, title="Scale vs capability crowding by HS8")
    st.plotly_chart(fig, use_container_width=True)

with tab5:
    st.subheader("Evidence-based strategic screen")
    st.write("This first-pass score rewards reported export scale and relative scarcity of the HS8 capability. It intentionally does **not** fabricate destination, growth, unit-price or geopolitical signals absent from the source.")
    st.dataframe(screen.head(100), hide_index=True, use_container_width=True, column_config={"capability_score": st.column_config.NumberColumn(format="%.1f"), "exported_value_rs": st.column_config.NumberColumn(format="%,.0f")})
    st.download_button("Download strategic screen CSV", screen.to_csv(index=False).encode("utf-8"), "strategic_screen.csv", "text/csv")

st.divider()
st.caption("Next analytical layer: join PBS HS8 × destination/time data and, where obtainable, shipment quantity/value data. Keep TDAP firm attribution separate from national trade totals unless a defensible linkage is established.")
