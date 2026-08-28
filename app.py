from __future__ import annotations

from io import BytesIO
from pathlib import Path
import base64
import importlib
import re

import pandas as pd
import plotly.express as px
import streamlit as st
import src.analysis as analysis
from src.contact_enrichment import enrich_contact_display, load_contact_workbook
from src.deep_dive import load_cross_chapter_universe
from src.deep_dive_fast import build_fast_indexes, exporter_portfolio_fast, find_exporters_fast, hs8_exporters_fast, load_cross_chapter_cache
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
CONTACT_FILE = Path("Contact_list_by_Company_hs_chapter.xlsx")
LOGO_FILE = Path("assets/ncgcl_logo.png")
DEEP_CACHE_FILE = Path("data/cross_chapter_universe.csv.gz")
DEEP_CACHE_MANIFEST = Path("data/cross_chapter_universe.manifest.json")
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


@st.cache_data(show_spinner=False)
def _chapter_sheets_from_path(path_string: str, mtime_ns: int):
    return _chapter_sheets(Path(path_string))


@st.cache_data(show_spinner=False)
def _chapter_sheets_from_bytes(payload: bytes):
    return _chapter_sheets(BytesIO(payload))


@st.cache_data(show_spinner=False)
def _selected_sheet_from_path(path_string: str, mtime_ns: int, sheet_name: str | None):
    return load_excel(Path(path_string), sheet_name=sheet_name)


@st.cache_data(show_spinner=False)
def _selected_sheet_from_bytes(payload: bytes, sheet_name: str | None):
    return load_excel(BytesIO(payload), sheet_name=sheet_name)


@st.cache_data(show_spinner=False)
def _contacts_from_path(path_string: str, mtime_ns: int):
    return load_contact_workbook(Path(path_string))


@st.cache_data(show_spinner=False)
def _contacts_from_bytes(payload: bytes):
    return load_contact_workbook(BytesIO(payload))


@st.cache_data(show_spinner=False)
def _cross_chapter_from_path(path_string: str, mtime_ns: int):
    return load_cross_chapter_universe(Path(path_string))


@st.cache_data(show_spinner=False)
def _cross_chapter_from_bytes(payload: bytes):
    return load_cross_chapter_universe(BytesIO(payload))


@st.cache_data(show_spinner=False)
def _cross_chapter_repo_cache(source_path: str, source_mtime_ns: int, cache_path: str, cache_mtime_ns: int, manifest_path: str, manifest_mtime_ns: int):
    return load_cross_chapter_cache(Path(source_path), Path(cache_path), Path(manifest_path))


@st.cache_data(show_spinner=False)
def _deep_indexes_cached(universe: pd.DataFrame, contacts: pd.DataFrame | None):
    return build_fast_indexes(universe, contacts)


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

    source_payload = source.getvalue() if hasattr(source, "getvalue") else None
    source_mtime_ns = None if source_payload is not None else source.stat().st_mtime_ns
    if source_payload is not None:
        valid_sheets = _chapter_sheets_from_bytes(source_payload)
    else:
        valid_sheets = _chapter_sheets_from_path(str(source), source_mtime_ns)
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

    contact_uploaded = st.file_uploader("Use a different contact workbook", type=["xlsx", "xlsm", "xls", "csv"], help="Optional display-only contact sidecar. It never enters export-value calculations.")
    if contact_uploaded is not None:
        contact_source = contact_uploaded
        contact_source_mode = "Uploaded contact workbook"
    elif CONTACT_FILE.exists():
        contact_source = CONTACT_FILE
        contact_source_mode = "Repository contact workbook"
    else:
        contact_source = None
        contact_source_mode = "No contact sidecar loaded"

    st.caption(f"Source mode: {source_mode}")
    st.caption(f"Contact mode: {contact_source_mode}")
    st.caption("Decision guardrails")
    st.caption("TDAP record count is not physical quantity. Extract shares are not Pakistan national shares until reconciled with official national totals.")

if source_payload is not None:
    raw, sheet = _selected_sheet_from_bytes(source_payload, selected_sheet)
else:
    raw, sheet = _selected_sheet_from_path(str(source), source_mtime_ns, selected_sheet)
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

# Contact enrichment is intentionally downstream of every analytical calculation above.
# It adds display-only metadata and cannot change source rows, values, ranks, shares, HHI,
# evidence tiers or reconciliation results.
contact_error = None
contact_audit = None
contacts = None
if contact_source is not None:
    try:
        if hasattr(contact_source, "getvalue"):
            contacts = _contacts_from_bytes(contact_source.getvalue())
        else:
            contacts = _contacts_from_path(str(contact_source), contact_source.stat().st_mtime_ns)
        exporters_display, exporter_contact_audit = enrich_contact_display(exporters, df, contacts, chapter_label)
        screen_display, contact_audit = enrich_contact_display(screen, df, contacts, chapter_label)
    except Exception as exc:
        contact_error = str(exc)
        contacts = None
        exporters_display = exporters.copy()
        screen_display = screen.copy()
else:
    exporters_display = exporters.copy()
    screen_display = screen.copy()

if "contact_phone" not in exporters_display:
    exporters_display["contact_phone"] = exporters_display["telephone"].fillna("") if "telephone" in exporters_display else ""
if "contact_phone" not in screen_display:
    screen_display["contact_phone"] = screen_display["telephone"].fillna("") if "telephone" in screen_display else ""

# The deep-dive universe is a separate read-only aggregation across chapter sheets. Existing
# chapter calculations above are already complete before this dataset is built.
deep_dive_error = None
deep_universe = None
deep_audit = None
deep_source_mode = source_mode
try:
    deep_source = source
    if len(valid_sheets) <= 1 and MASTER_FILE.exists():
        deep_source = MASTER_FILE
        deep_source_mode = "Repository master workbook (cross-chapter deep dive)"
    if hasattr(deep_source, "getvalue"):
        deep_universe, deep_audit = _cross_chapter_from_bytes(deep_source.getvalue())
    else:
        deep_stamp = deep_source.stat().st_mtime_ns
        cached_pair = None
        if Path(deep_source) == MASTER_FILE and DEEP_CACHE_FILE.exists() and DEEP_CACHE_MANIFEST.exists():
            cached_pair = _cross_chapter_repo_cache(
                str(MASTER_FILE), deep_stamp,
                str(DEEP_CACHE_FILE), DEEP_CACHE_FILE.stat().st_mtime_ns,
                str(DEEP_CACHE_MANIFEST), DEEP_CACHE_MANIFEST.stat().st_mtime_ns,
            )
        if cached_pair is not None:
            deep_universe, deep_audit = cached_pair
            deep_source_mode += " · validated fast cache"
        else:
            deep_universe, deep_audit = _cross_chapter_from_path(str(deep_source), deep_stamp)
except Exception as exc:
    deep_dive_error = str(exc)

deep_exporter_index = pd.DataFrame()
deep_contact_directory = pd.DataFrame()
if deep_universe is not None:
    deep_exporter_index, deep_contact_directory = _deep_indexes_cached(deep_universe, contacts)

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

filtered = exporters_display.copy()
if q.strip():
    cols = [x for x in ["exporter_name", "ntn", "email", "contact_phone", "telephone", "address"] if x in filtered]
    mask = pd.Series(False, index=filtered.index)
    for col in cols:
        mask |= filtered[col].astype("string").str.contains(q.strip(), case=False, na=False)
    filtered = filtered[mask]

overview, leaders, products, deep_dive, shortlist, diligence, methodology = st.tabs(["Executive Brief", "Exporter Intelligence", "Product Portfolio", "Exporter / Product Deep Dive", "Strategic Shortlist", "Data Assurance", "Methodology"])

with overview:
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    total_bn = round(c["total_value_rs"] / 1e9)
    k1.metric("TDAP reported export value", f"Rs {total_bn:,.0f} bn")
    k2.metric("Unique exporters", f"{a.unique_exporters:,}")
    k3.metric("Distinct HS8 products", f"{a.unique_hs8:,}")
    k4.metric("Top 10 exporters' share", f"{c['top10_share']*100:.2f}%")
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
    chart = exporters_display.head(top_n).sort_values("reported_value_rs")
    fig = px.bar(chart, x="reported_value_rs", y="exporter_name", orientation="h", hover_data=[x for x in ["rank", "share", "cumulative_share", "ntn", "email", "contact_phone"] if x in chart], labels={"reported_value_rs": "Reported value (Rs)", "exporter_name": ""}, height=max(500, top_n * 27))
    st.plotly_chart(fig, use_container_width=True, config=CLEAN_PLOT_CONFIG)

with leaders:
    st.subheader("Exporter ranking, concentration & contact directory")
    st.caption("Company-level view. Values aggregate all rows observed for the exporter in the selected chapter extract.")
    ranking_cols = [x for x in ["rank", "exporter_name", "ntn", "contact_phone", "reported_value_rs", "share", "cumulative_share", "record_count", "avg_value_per_reported_record_rs", "hs8_count", "hs4_count", "largest_hs8", "email", "address"] if x in filtered]
    st.dataframe(filtered[ranking_cols], hide_index=True, use_container_width=True, height=680, column_config={
        "rank": "Rank", "exporter_name": "Exporter", "ntn": "NTN", "contact_phone": "Phone",
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
        fig = px.treemap(hs8, path=["hs8"], values="reported_value_rs", hover_data={"product_name": True, "exporters": True, "share": ":.2%"}, title=f"Where reported Chapter {chapter_label} value sits")
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

with deep_dive:
    st.subheader("Exporter / Product Deep Dive")
    st.caption("Cross-chapter research view. It reads the available HS chapter sheets as a separate universe and does not change the selected-chapter rankings, HHI, strategic tiers or reconciliation above.")
    if deep_dive_error:
        st.error("Cross-chapter deep dive could not be built: " + deep_dive_error)
    elif deep_universe is None or deep_audit is None:
        st.info("No cross-chapter universe is available.")
    else:
        st.caption(f"Deep-dive source: {deep_source_mode} · {len(deep_audit.chapters)} HS chapters · {deep_audit.rows:,} source rows · {deep_audit.unique_ntns:,} verified NTNs · {deep_audit.unique_hs8:,} HS8 products")
        search_mode = st.radio("Explore by", ["Exporter (name or NTN)", "HS8 product"], horizontal=True, key="deep_dive_mode")

        if search_mode == "Exporter (name or NTN)":
            with st.form("deep_exporter_search_form", clear_on_submit=False):
                exporter_input = st.text_input("Search exporter", placeholder="Type company name or NTN", key="deep_exporter_query_input")
                exporter_submit = st.form_submit_button("Search exporter")
            if exporter_submit:
                st.session_state["deep_exporter_committed_query"] = exporter_input.strip()
            exporter_query = st.session_state.get("deep_exporter_committed_query", "")
            if exporter_query:
                matches = find_exporters_fast(deep_exporter_index, exporter_query)
                if matches.empty:
                    st.warning("No verified NTN matched that exporter search across the loaded chapter universe.")
                else:
                    option_map = {}
                    for _, row in matches.iterrows():
                        label = f"{row['exporter_name']} · NTN {row['ntn']} · {row['hs8_products']} HS8 · {row['chapters']} chapters"
                        option_map[label] = row["ntn"]
                    selected_exporter = st.selectbox("Select verified exporter identity", list(option_map), key=f"deep_exporter_select_{exporter_query}")
                    profile = exporter_portfolio_fast(deep_universe, option_map[selected_exporter], deep_contact_directory)
                    sm = profile.summary
                    d1, d2, d3, d4 = st.columns(4)
                    d1.metric("Total reported value", f"Rs {sm['total_reported_value_rs']/1e9:,.2f} bn")
                    d2.metric("Distinct HS8 products", f"{sm['hs8_products']:,}")
                    d3.metric("HS chapters observed", f"{sm['chapters']:,}")
                    d4.metric("NTN", sm["ntn"])
                    st.markdown(f"**{sm['exporter_name']}**")
                    if sm["name_aliases"] and sm["name_aliases"] != sm["exporter_name"]:
                        st.caption("Observed name aliases: " + sm["name_aliases"])
                    st.caption("Phone: " + (sm["phones"] or "Not safely available") + " · Email: " + (sm["emails"] or "Not available"))
                    st.markdown("**Product mix** — each share equals this exporter's reported value in the HS8 divided by this exporter's total reported value across the loaded HS chapters.")
                    chart = profile.table.sort_values("share_of_exporter")
                    fig = px.bar(chart, x="share_of_exporter", y="hs8", orientation="h", hover_data=["chapter", "product_name", "reported_value_rs"], labels={"share_of_exporter": "Share of exporter portfolio", "hs8": "HS8"}, height=max(420, min(900, len(chart) * 30)))
                    fig.update_xaxes(tickformat=".2%")
                    st.plotly_chart(fig, use_container_width=True, config=CLEAN_PLOT_CONFIG)
                    st.dataframe(profile.table, hide_index=True, use_container_width=True, column_config={
                        "rank": "Rank", "chapter": "HS chapter", "hs8": "HS8", "product_name": "Product description",
                        "reported_value_rs": st.column_config.NumberColumn("Reported value (Rs)", format="%,.0f"),
                        "share_of_exporter": st.column_config.NumberColumn("Share of exporter portfolio", format="%.2%%"),
                        "source_rows": "Source rows",
                    })
                    with st.expander("Calculation controls", expanded=False):
                        st.code("HS8 share of exporter = exporter value in that HS8 / exporter total value across all loaded HS chapters")
                        st.dataframe(profile.checks, hide_index=True, use_container_width=True)
                    st.download_button("Download exporter product portfolio", profile.table.to_csv(index=False).encode("utf-8-sig"), f"exporter_{sm['ntn']}_hs8_portfolio.csv", "text/csv")

        else:
            with st.form("deep_hs8_search_form", clear_on_submit=False):
                hs8_input = st.text_input("Enter exact HS8 code", placeholder="e.g. 12074000", key="deep_hs8_query_input")
                hs8_submit = st.form_submit_button("Search HS8")
            if hs8_submit:
                st.session_state["deep_hs8_committed_query"] = hs8_input.strip()
            hs8_query = st.session_state.get("deep_hs8_committed_query", "")
            if hs8_query:
                digits = re.sub(r"\D", "", hs8_query)
                if len(digits) != 8:
                    st.warning("Enter an exact 8-digit HS8 code so the denominator remains unambiguous.")
                else:
                    try:
                        profile = hs8_exporters_fast(deep_universe, digits, deep_contact_directory)
                    except KeyError as exc:
                        st.warning(str(exc))
                    except ValueError as exc:
                        st.warning(str(exc))
                    else:
                        sm = profile.summary
                        h1, h2, h3, h4 = st.columns(4)
                        h1.metric("HS8 total reported value", f"Rs {sm['total_reported_value_rs']/1e9:,.2f} bn")
                        h2.metric("Observed exporters", f"{sm['exporters']:,}")
                        h3.metric("Verified NTN exporters", f"{sm['verified_ntn_exporters']:,}")
                        h4.metric("HS chapter", sm["chapter"])
                        st.markdown(f"**HS8 {sm['hs8']} — {sm['product_name'] or 'Description unavailable'}**")
                        if sm["missing_ntn_exporters"]:
                            st.caption(f"{sm['missing_ntn_exporters']} observed exporter identities have no NTN. They remain in the HS8 denominator and are clearly flagged rather than being dropped or assigned to another firm.")
                        st.markdown("**Exporter position inside this HS8** — each share equals the exporter's reported value in this HS8 divided by the total reported value of this HS8 across the loaded chapter universe.")
                        chart = profile.table.head(30).sort_values("share_of_hs8")
                        fig = px.bar(chart, x="share_of_hs8", y="exporter_name", orientation="h", hover_data=["ntn", "reported_value_rs", "phone"], labels={"share_of_hs8": "Share of HS8", "exporter_name": ""}, height=max(480, min(1000, len(chart) * 30)))
                        fig.update_xaxes(tickformat=".2%")
                        st.plotly_chart(fig, use_container_width=True, config=CLEAN_PLOT_CONFIG)
                        st.dataframe(profile.table, hide_index=True, use_container_width=True, height=650, column_config={
                            "rank": "HS8 rank", "exporter_name": "Exporter", "ntn": "NTN", "phone": "Phone", "email": "Email",
                            "reported_value_rs": st.column_config.NumberColumn("Reported HS8 value (Rs)", format="%,.0f"),
                            "share_of_hs8": st.column_config.NumberColumn("Share of HS8", format="%.2%%"),
                            "identity_status": "Identity status", "source_rows": "Source rows",
                        })
                        with st.expander("Calculation controls", expanded=False):
                            st.code("Exporter share of HS8 = exporter reported value in the HS8 / total reported value of that HS8")
                            st.dataframe(profile.checks, hide_index=True, use_container_width=True)
                        st.download_button("Download HS8 exporter table", profile.table.to_csv(index=False).encode("utf-8-sig"), f"hs8_{sm['hs8']}_exporters.csv", "text/csv")

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
    s = screen_display[screen_display["evidence_tier"].isin(tier_filter)].copy() if tier_filter else screen_display.copy()
    tier_display = {
        "A — high-priority evidence": "A",
        "B — priority review": "B",
        "C — broader pipeline": "C",
    }
    s["tier"] = s["evidence_tier"].map(tier_display).fillna(s["evidence_tier"])
    s["contact_phone"] = s["contact_phone"].fillna("")
    show = [x for x in ["tier", "chapter_rank", "exporter_name", "ntn", "contact_phone", "firm_chapter_value_rs", "firm_chapter_share", "firm_hs8_breadth", "hs8", "product_name", "hs8_value_rs", "rank_within_hs8", "share_within_hs8", "firms_in_hs8", "screening_reason", "email"] if x in s]
    st.dataframe(s[show], hide_index=True, use_container_width=True, height=680, column_config={
        "tier": "Tier", "chapter_rank": "Company chapter rank", "exporter_name": "Exporter", "ntn": "NTN", "contact_phone": "Phone",
        "firm_chapter_value_rs": st.column_config.NumberColumn("Firm chapter value (Rs)", format="%,.0f"),
        "firm_chapter_share": st.column_config.NumberColumn("Firm extract share", format="%.2%%"),
        "firm_hs8_breadth": "Observed HS8 breadth", "hs8": "HS8", "product_name": "Product",
        "hs8_value_rs": st.column_config.NumberColumn("HS8 value (Rs)", format="%,.0f"),
        "rank_within_hs8": "HS8 rank",
        "share_within_hs8": st.column_config.NumberColumn("Observed HS8 share", format="%.2%%"),
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

    st.subheader("Contact enrichment integrity")
    if contact_error:
        st.error("Contact sidecar was not applied: " + contact_error)
    elif contact_audit is None:
        st.info("No contact sidecar is loaded. Export calculations and reconciliation remain fully operational.")
    else:
        q1, q2, q3, q4 = st.columns(4)
        q1.metric("Contact rows in chapter", contact_audit.contact_rows_for_chapter)
        q2.metric("Safe phone keys", contact_audit.safe_phone_keys)
        q3.metric("Ambiguous identity keys", contact_audit.ambiguous_identity_keys)
        q4.metric("Rows still without phone", contact_audit.rows_without_phone)
        contact_checks = pd.DataFrame({
            "Control": [
                "Analytical calculations performed before contact enrichment",
                "Contact join changes target row count",
                "Phone match requires chapter + normalized exporter + unique NTN",
                "Conflicting phone values are assigned",
                "Multiple NTNs under same chapter/exporter are assigned",
            ],
            "Result": ["PASS", "PASS", "PASS", "NO", "NO"],
        })
        st.dataframe(contact_checks, hide_index=True, use_container_width=True)
        st.caption("Phone numbers are display-only metadata. Ambiguous identities or conflicting phone values are deliberately left blank rather than guessed.")

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
**Workbook principle:** a 24-sheet workbook is a navigation container for the existing chapter analytics. One selected HS2 sheet is analysed at a time so rankings, shares and concentration remain chapter-specific.  
**Deep-dive principle:** the Exporter / Product Deep Dive separately reads all available chapter sheets. NTN is the primary exporter identity. Exporter product shares use the exporter's total value across the loaded chapters as denominator; HS8 exporter shares use the complete observed HS8 value as denominator. This cross-chapter view does not feed back into chapter KPIs or tiers.  
**Reconciliation principle:** each selected chapter is independently re-aggregated from source fields and compared with dashboard totals, concentration metrics, exporter-HS8 values, shares and ranks. Any failed control is surfaced in Data Assurance.  
**Contact-enrichment principle:** phone numbers are attached only after analytical calculations. Sidecar matches require the selected chapter, normalized exporter identity and exactly one NTN in the analytical source; conflicting contacts or ambiguous legal identities are withheld rather than guessed.  
**Next enrichment:** PBS HS8 × destination × value × quantity × fiscal year, followed by global demand, Pakistan share, competitor concentration, market access and policy indicators.""")
    st.code("Workbook → chapter selector → chapter analytics/reconciliation | parallel cross-chapter universe → NTN exporter portfolio or HS8 exporter composition → display-only contact enrichment → due diligence")

st.divider()
st.caption(f"Source: {source_mode} · Sheet: {sheet} · Chapter {chapter_label} · {a.rows:,} rows · {a.unique_exporters:,} exporters | Internal decision-support")
