from __future__ import annotations

from pathlib import Path
import base64
import importlib
import re

import pandas as pd
import plotly.express as px
import streamlit as st
import src.analysis as analysis
from src.reconciliation import reconcile_chapter

analysis = importlib.reload(analysis)
audit = analysis.audit
concentration = analysis.concentration
exporter_table = analysis.exporter_table
hs8_table = analysis.hs8_table
load_excel = analysis.load_excel
normalize = analysis.normalize
strategic_screen = analysis.strategic_screen

st.set_page_config(page_title="Pakistan Export Intelligence", page_icon="🇵🇰", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""<style>
.block-container{padding-top:1.5rem;padding-bottom:3rem;max-width:1550px}
[data-testid="stMetric"]{background:rgba(30,41,59,.45);border:1px solid rgba(148,163,184,.15);padding:16px;border-radius:12px;min-height:150px}
[data-testid="stMetricLabel"]{font-size:.76rem;text-transform:uppercase;letter-spacing:.035em;white-space:normal!important}
[data-testid="stMetricValue"]{font-size:2.15rem!important;white-space:normal!important}
.hero{padding:18px 22px;border:1px solid rgba(148,163,184,.16);border-radius:14px;background:linear-gradient(120deg,rgba(0,77,115,.34),rgba(51,51,51,.42));margin-bottom:14px;display:flex;align-items:center;justify-content:space-between;gap:24px}
.hero-copy{min-width:0}.hero h1{margin:12px 0 0;font-size:2rem}.hero p{margin:.45rem 0 0;color:#cbd5e1}.hero-logo{width:min(290px,24vw);max-height:95px;object-fit:contain;object-position:right center;filter:drop-shadow(0 2px 5px rgba(0,0,0,.2))}
.badge{display:inline-block;padding:4px 9px;border-radius:999px;background:rgba(0,77,115,.38);color:#e6f4f8;font-size:.75rem;margin-right:6px}
.smallnote{color:#94a3b8;font-size:.78rem}.modebar{opacity:.18!important;transform:scale(.82);transform-origin:top right}.js-plotly-plot:hover .modebar{opacity:.70!important}
</style>""", unsafe_allow_html=True)

MASTER_FILE = Path("TDAP_Export_Directory_HS01_24.xlsx")
LEGACY_FILE = Path("Chapter_12.xlsx")
LOGO_FILE = Path("assets/ncgcl_logo.png")
PLOT_CONFIG = {"displaylogo": False, "responsive": True, "scrollZoom": False, "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d", "toggleSpikelines"]}
CLEAN_PLOT_CONFIG = {"displayModeBar": False, "responsive": True}


def _chapter_code(sheet_name: str) -> str | None:
    m = re.search(r"(?:^|\b)HS[_\s-]?(\d{1,2})(?:\b|\s)", str(sheet_name), flags=re.I)
    return m.group(1).zfill(2) if m else None


def _chapter_sheets(file_or_path) -> list[dict]:
    """Return valid single-HS2 chapter sheets without loading them into one analytical universe."""
    xls = pd.ExcelFile(file_or_path)
    found = []
    for sheet_name in xls.sheet_names:
        code = _chapter_code(sheet_name)
        if code is None:
            continue
        preview = pd.read_excel(xls, sheet_name=sheet_name, nrows=8)
        preview = normalize(preview)
        missing = [c for c in analysis.REQUIRED if c not in preview.columns]
        if missing:
            continue
        observed = sorted(preview["hs8"].dropna().astype("string").str[:2].unique().tolist()) if "hs8" in preview else []
        consistent = not observed or observed == [code]
        found.append({"sheet": sheet_name, "chapter": code, "consistent": consistent, "observed": observed})
    return sorted(found, key=lambda x: (x["chapter"], x["sheet"]))


def _logo_data_uri() -> str | None:
    if not LOGO_FILE.exists():
        return None
    return "data:image/png;base64," + base64.b64encode(LOGO_FILE.read_bytes()).decode("ascii")


with st.sidebar:
    st.header("Control panel")
    uploaded = st.file_uploader("Use a different workbook", type=["xlsx", "xlsm", "xls"], help="Upload either the 24-sheet master workbook or a standalone single-chapter workbook.")
    if uploaded is not None:
        source = uploaded
        source_mode = "Uploaded workbook"
    elif MASTER_FILE.exists():
        source = MASTER_FILE
        source_mode = "Repository master workbook"
    else:
        source = LEGACY_FILE
        source_mode = "Legacy single-chapter workbook"
    if not hasattr(source, "read") and not source.exists():
        st.error("No workbook available. Add the master workbook or upload a chapter workbook.")
        st.stop()

    valid_sheets = _chapter_sheets(source)
    if len(valid_sheets) > 1:
        labels = {f"HS {x['chapter']} · {x['sheet']}": x for x in valid_sheets}
        default_idx = next((i for i, x in enumerate(valid_sheets) if x["chapter"] == "12"), 0)
        selected_label = st.selectbox("Select HS chapter", list(labels), index=default_idx)
        selected = labels[selected_label]
        selected_sheet = selected["sheet"]
        if not selected["consistent"]:
            st.warning(f"Sheet label HS {selected['chapter']} does not fully match observed HS2 values: {', '.join(selected['observed']) or 'none detected'}")
    else:
        selected_sheet = valid_sheets[0]["sheet"] if valid_sheets else None
        if selected_sheet:
            st.caption(f"Detected chapter sheet: {selected_sheet}")

    st.caption(f"Source mode: {source_mode}")
    st.caption("Decision guardrails")
    st.caption("TDAP record count is not physical quantity. Extract shares are not Pakistan national shares until reconciled with official national totals.")

raw, sheet = load_excel(source, sheet_name=selected_sheet)
df = normalize(raw)
a = audit(df)
if a.missing_required:
    st.error("Missing required fields: " + ", ".join(a.missing_required))
    st.stop()
if len(a.chapters) > 1:
    st.error("The active analytical sheet contains more than one HS2 chapter. The app stopped to protect chapter-specific rankings and denominators.")
    st.stop()

c = concentration(df)
exporters = exporter_table(df)
hs8 = hs8_table(df)
screen = strategic_screen(df)
reconciliation = reconcile_chapter(df)
chapter_label = ", ".join(a.chapters) if a.chapters else (_chapter_code(sheet) or "Unknown")

SCREEN_REQUIRED = {"evidence_tier", "chapter_rank", "exporter_name", "firm_chapter_value_rs", "firm_chapter_share", "hs8", "hs8_value_rs", "rank_within_hs8", "share_within_hs8", "firms_in_hs8", "screening_reason"}
missing_screen = sorted(SCREEN_REQUIRED - set(screen.columns))
if missing_screen:
    st.error("Analytical engine/schema mismatch. Missing strategic-screen fields: " + ", ".join(missing_screen) + ". The app has stopped rather than displaying inconsistent results. Restart/redeploy the app from the current main branch.")
    st.stop()

logo_uri = _logo_data_uri()
logo_html = f'<img class="hero-logo" src="{logo_uri}" alt="NCGCL logo">' if logo_uri else ""
st.markdown(f'''<div class="hero"><div class="hero-copy"><span class="badge">EXPORT ANALYTICS</span><h1>Pakistan Export Intelligence</h1><p>HS Chapter {chapter_label} · Executive decision dashboard</p></div>{logo_html}</div>''', unsafe_allow_html=True)

with st.expander("Search & analytical controls", expanded=False):
    x1, x2, x3 = st.columns([2, 1, 1])
    q = x1.text_input("Find exporter", placeholder="Company, NTN, email, phone or address")
    top_n = x2.slider("Ranking depth", 10, min(100, max(10, len(exporters))), min(25, max(10, len(exporters))))
    threshold = x3.selectbox("Strategic coverage", [50, 60, 70, 80, 90], index=1)

filtered = exporters.copy()
if q.strip():
    cols = [x for x in ["exporter_name", "ntn", "email", "telephone", "address"] if x in filtered]
    mask = pd.Series(False, index=filtered.index)
    for col in cols:
        mask |= filtered[col].astype("string").str.contains(q.strip(), case=False, na=False)
    filtered = filtered[mask]

overview, leaders, products, shortlist, diligence, methodology = st.tabs(["Executive Brief", "Exporter Intelligence", "Product Portfolio", "Strategic Shortlist", "Data Assurance", "Methodology"])

with overview:
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    total_bn = round(c["total_value_rs"] / 1e9)
    k1.metric("TDAP reported export value", f"Rs {total_bn:,.0f} bn")
    k2.metric("Unique exporters", f"{a.unique_exporters:,}")
    k3.metric("Distinct HS8 products", f"{a.unique_hs8:,}")
    k4.metric("Top 10 exporters' share", f"{c['top10_share']*100:.0f}%")
    k5.metric("Exporters needed for 60%", f"{c['exporters_to_60pct']:,}")
    k6.metric("HHI concentration index", f"{c['hhi']:,.0f}")
    st.caption("KPIs describe the selected TDAP chapter extract, not Pakistan's national export market, until reconciliation with official national totals.")
    st.subheader("Concentration curve")
    pareto = exporters[["rank", "cumulative_share"]].copy()
    pareto["Cumulative share (%)"] = pareto.cumulative_share * 100
    fig = px.area(pareto, x="rank", y="Cumulative share (%)", labels={"rank": "Exporter rank"}, height=350)
    fig.add_hline(y=60, line_dash="dash", annotation_text="60% coverage")
    st.plotly_chart(fig, use_container_width=True, config=PLOT_CONFIG)
    st.subheader(f"Top {top_n} exporters")
    chart = exporters.head(top_n).sort_values("reported_value_rs")
    fig = px.bar(chart, x="reported_value_rs", y="exporter_name", orientation="h", hover_data=[x for x in ["rank", "share", "cumulative_share", "ntn", "email", "telephone"] if x in chart], labels={"reported_value_rs": "Reported value (Rs)", "exporter_name": ""}, height=max(500, top_n * 27))
    st.plotly_chart(fig, use_container_width=True, config=CLEAN_PLOT_CONFIG)

with leaders:
    st.subheader("Exporter ranking, concentration & contact directory")
    st.caption("Company-level view. Values aggregate all rows observed for the exporter in the selected chapter extract.")
    ranking_cols = [x for x in ["rank", "exporter_name", "ntn", "reported_value_rs", "share", "cumulative_share", "record_count", "avg_value_per_reported_record_rs", "hs8_count", "hs4_count", "largest_hs8", "email", "telephone", "address"] if x in filtered]
    st.dataframe(filtered[ranking_cols], hide_index=True, use_container_width=True, height=680, column_config={
        "rank": "Rank", "exporter_name": "Exporter", "ntn": "NTN",
        "reported_value_rs": st.column_config.NumberColumn("Reported value (Rs)", format="%,.0f"),
        "share": st.column_config.NumberColumn("Extract share", format="%.2%%"),
        "cumulative_share": st.column_config.NumberColumn("Cumulative", format="%.2%%"),
        "avg_value_per_reported_record_rs": st.column_config.NumberColumn("Value / record*", format="%,.0f"),
        "hs8_count": "HS8 breadth", "hs4_count": "HS4 breadth", "largest_hs8": "Lead HS8",
    })
    st.caption("*Descriptive value per TDAP reported record; not a physical unit value or price.")

with products:
    st.subheader("HS8 product portfolio")
    p1, p2 = st.columns([1.15, 1])
    with p1:
        fig = px.treemap(hs8, path=["hs8"], values="reported_value_rs", hover_data=[x for x in ["product_name", "exporters", "share"] if x in hs8], title=f"Where reported Chapter {chapter_label} value sits")
        st.plotly_chart(fig, use_container_width=True, config=CLEAN_PLOT_CONFIG)
    with p2:
        fig = px.scatter(hs8, x="exporters", y="reported_value_rs", size="reported_value_rs", hover_name="hs8", hover_data=["product_name"], log_y=True, title="Scale vs exporter participation")
        fig.update_layout(yaxis_title="Reported value (Rs)", xaxis_title="Number of exporters")
        st.plotly_chart(fig, use_container_width=True, config=PLOT_CONFIG)
    st.dataframe(hs8, hide_index=True, use_container_width=True, column_config={
        "reported_value_rs": st.column_config.NumberColumn("Reported value (Rs)", format="%,.0f"),
        "share": st.column_config.NumberColumn("Extract share", format="%.2%%"),
        "cumulative_share": st.column_config.NumberColumn("Cumulative", format="%.2%%"),
    })

with shortlist:
    st.subheader("Exporter × HS8 evidence screen")
    st.caption("A transparent prioritisation screen for due diligence. One row = one exporter × HS8 capability after aggregation. It is not a financing recommendation and does not claim national market share.")
    a_count = int((screen["evidence_tier"] == "A — high-priority evidence").sum())
    b_count = int((screen["evidence_tier"] == "B — priority review").sum())
    c_count = int((screen["evidence_tier"] == "C — broader pipeline").sum())
    m1, m2, m3 = st.columns(3)
    m1.metric("Tier A", a_count, help="Firm is top-decile by observed chapter scale, top 3 within its HS8, and has at least 10% of observed HS8 value.")
    m2.metric("Tier B", b_count, help="Either top 3 with at least 10% observed HS8 share, or a top-decile firm in an HS8 with five or fewer observed firms.")
    m3.metric("Tier C", c_count, help="All other observed exporter-HS8 capabilities. These remain visible and are not treated as failures.")
    tier_options = ["A — high-priority evidence", "B — priority review", "C — broader pipeline"]
    tier_filter = st.multiselect("Evidence tier", tier_options, default=tier_options[:2])
    s = screen[screen["evidence_tier"].isin(tier_filter)].copy() if tier_filter else screen.copy()
    tier_display = {
        "A — high-priority evidence": "A",
        "B — priority review": "B",
        "C — broader pipeline": "C",
    }
    s["tier"] = s["evidence_tier"].map(tier_display).fillna(s["evidence_tier"])
    if "telephone" in s:
        s["telephone"] = s["telephone"].fillna("")
    show = [x for x in ["tier", "chapter_rank", "exporter_name", "ntn", "telephone", "firm_chapter_value_rs", "firm_chapter_share", "firm_hs8_breadth", "hs8", "product_name", "hs8_value_rs", "rank_within_hs8", "share_within_hs8", "firms_in_hs8", "screening_reason", "email"] if x in s]
    st.dataframe(s[show], hide_index=True, use_container_width=True, height=680, column_config={
        "tier": "Tier", "chapter_rank": "Company chapter rank", "exporter_name": "Exporter", "ntn": "NTN", "telephone": "Phone",
        "firm_chapter_value_rs": st.column_config.NumberColumn("Firm chapter value (Rs)", format="%,.0f"),
        "firm_chapter_share": st.column_config.NumberColumn("Firm extract share", format="%.2%%"),
        "firm_hs8_breadth": "Observed HS8 breadth", "hs8": "HS8", "product_name": "Product",
        "hs8_value_rs": st.column_config.NumberColumn("HS8 value (Rs)", format="%,.0f"),
        "rank_within_hs8": "HS8 rank",
        "share_within_hs8": st.column_config.NumberColumn("Observed HS8 share", format="%.1%%"),
        "firms_in_hs8": "Firms in HS8", "screening_reason": "Why surfaced",
    })
    st.markdown("**Tier rules**  \n**A:** firm is in the top 10% by observed chapter scale **and** ranks top 3 in the HS8 **and** contributes at least 10% of observed HS8 value.  \n**B:** either (i) top 3 in HS8 with ≥10% observed HS8 share, or (ii) top-10%-scale firm operating in an HS8 with ≤5 observed firms.  \n**C:** broader pipeline. These thresholds are policy screening rules, not statistical estimates; change them only through documented methodology review.")
    st.download_button("Download evidence screen", s[show].to_csv(index=False).encode("utf-8-sig"), "exporter_hs8_evidence_screen.csv", "text/csv")

with diligence:
    st.subheader("Data assurance & reconciliation")
    r1, r2, r3 = st.columns(3)
    r1.metric("Reconciliation status", "PASS" if reconciliation.passed else "FAIL")
    r2.metric("Checks passed", reconciliation.summary["passed_checks"])
    r3.metric("Checks failed", reconciliation.summary["failed_checks"])
    if reconciliation.passed:
        st.success("Selected chapter reconciles to the source dataframe across totals, shares, concentration and exporter × HS8 calculations.")
    else:
        st.error("One or more reconciliation controls failed. Do not rely on the affected outputs until the differences are resolved.")
    st.dataframe(reconciliation.checks, hide_index=True, use_container_width=True)
    st.download_button("Download reconciliation report", reconciliation.checks.to_csv(index=False).encode("utf-8-sig"), f"chapter_{chapter_label}_reconciliation.csv", "text/csv")
    st.subheader("Source controls")
    checks = pd.DataFrame({"Control": ["Source mode", "Source sheet", "Source rows", "Source columns", "Duplicate rows", "Invalid HS8", "Non-positive/missing value", "Unique exporters", "Unique NTNs", "Unique HS8", "Detected chapter"], "Result": [source_mode, sheet, a.rows, a.columns, a.duplicate_rows, a.invalid_hs8, a.nonpositive_values, a.unique_exporters, a.unique_ntns, a.unique_hs8, chapter_label]})
    st.dataframe(checks, hide_index=True, use_container_width=True)
    for warning in a.warnings:
        st.warning(warning)

with methodology:
    st.subheader("Analytical doctrine")
    st.markdown("""**Observed:** exporter identity, HS8 product, TDAP reported value, reported record count and available contact fields.  
**Derived:** company-level chapter value/rank/share; exporter-HS8 aggregated value; within-HS8 rank/share; number of observed firms; HS8/HS4 breadth; transparent evidence tiers.  
**Not inferred:** national market share, destination attractiveness, growth, physical unit value, credit quality, financing suitability or geopolitical fit.  
**Screening principle:** keep company-level scale separate from product-level capability. Surface the evidence used for prioritisation instead of hiding it inside a composite score. Tier rules are explicit policy thresholds and are not statistical estimates.  
**Workbook principle:** a 24-sheet workbook is a navigation container only. One selected HS2 sheet is analysed at a time so rankings, shares and concentration remain chapter-specific.  
**Reconciliation principle:** each selected chapter is independently re-aggregated from source fields and compared with dashboard totals, concentration metrics, exporter-HS8 values, shares and ranks. Any failed control is surfaced in Data Assurance.  
**Next enrichment:** PBS HS8 × destination × value × quantity × fiscal year, followed by global demand, Pakistan share, competitor concentration, market access and policy indicators.""")
    st.code("Workbook → chapter selector → normalization → audit → company aggregation → HS8 aggregation → exporter×HS8 aggregation → within-HS8 position → transparent evidence tier → reconciliation → due diligence")

st.divider()
st.caption(f"Source: {source_mode} · Sheet: {sheet} · Chapter {chapter_label} · {a.rows:,} rows · {a.unique_exporters:,} exporters | Internal decision-support")