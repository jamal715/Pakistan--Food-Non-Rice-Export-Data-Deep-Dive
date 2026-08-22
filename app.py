from __future__ import annotations

from pathlib import Path
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.analysis import audit, concentration, exporter_table, hs8_table, load_excel, normalize, strategic_screen

st.set_page_config(page_title="Pakistan Export Intelligence", page_icon="🇵🇰", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
.block-container {padding-top: 1.5rem; padding-bottom: 3rem; max-width: 1550px;}
[data-testid="stMetric"] {background: rgba(30,41,59,.45); border: 1px solid rgba(148,163,184,.15); padding: 16px; border-radius: 12px; min-height:150px;}
[data-testid="stMetricLabel"] {font-size: .76rem; text-transform: uppercase; letter-spacing: .035em; white-space:normal !important; overflow:visible !important; text-overflow:clip !important; line-height:1.25;}
[data-testid="stMetricValue"] {font-size:2.15rem !important; white-space:normal !important; overflow:visible !important; text-overflow:clip !important;}
.hero {padding: 18px 22px; border:1px solid rgba(148,163,184,.16); border-radius:14px; background:linear-gradient(120deg,rgba(0,77,115,.34),rgba(51,51,51,.42)); margin-bottom:14px;}
.hero h1 {margin:0; font-size:2rem;}
.hero p {margin:.45rem 0 0; color:#cbd5e1;}
.badge {display:inline-block;padding:4px 9px;border-radius:999px;background:rgba(0,77,115,.38);color:#e6f4f8;font-size:.75rem;margin-right:6px;}
.smallnote {color:#94a3b8;font-size:.78rem;}
.modebar {opacity:.18 !important; transform:scale(.82); transform-origin:top right;}
.js-plotly-plot:hover .modebar {opacity:.70 !important;}
</style>
""", unsafe_allow_html=True)

DEFAULT_FILE = Path("Chapter_12.xlsx")
PLOT_CONFIG = {"displaylogo": False, "responsive": True, "scrollZoom": False, "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d", "toggleSpikelines"]}
CLEAN_PLOT_CONFIG = {"displayModeBar": False, "responsive": True}

with st.sidebar:
    st.header("Control panel")
    uploaded = st.file_uploader("Replace chapter workbook", type=["xlsx", "xlsm", "xls"])
    if uploaded is not None:
        source = uploaded
        st.success(f"Session file: {uploaded.name}")
    elif DEFAULT_FILE.exists():
        source = DEFAULT_FILE
        st.success("Repository dataset loaded")
    else:
        st.error("No workbook available")
        st.stop()
    st.markdown("---")
    st.caption("Decision guardrails")
    st.caption("TDAP record count is not physical quantity. Value/record is not unit price. Extract shares are not Pakistan national shares until reconciled with PBS.")

raw, sheet = load_excel(source)
df = normalize(raw)
a = audit(df)
if a.missing_required:
    st.error("Missing required fields: " + ", ".join(a.missing_required)); st.stop()

c = concentration(df)
exporters = exporter_table(df)
hs8 = hs8_table(df)
screen = strategic_screen(df)
chapter_label = ", ".join(a.chapters) if a.chapters else "Unknown"

st.markdown(f"""
<div class="hero">
<span class="badge">STRATEGIC PLANNING CELL</span><span class="badge">EXPORT ANALYTICS</span>
<h1>Pakistan Export Intelligence</h1>
<p>HS Chapter {chapter_label} · Executive decision dashboard</p>
</div>
""", unsafe_allow_html=True)

with st.expander("Search & analytical controls", expanded=False):
    x1,x2,x3 = st.columns([2,1,1])
    q=x1.text_input("Find exporter", placeholder="Company, NTN, email, phone or address")
    top_n=x2.slider("Ranking depth",10,min(100,max(10,len(exporters))),min(25,max(10,len(exporters))))
    threshold=x3.selectbox("Strategic coverage",[50,60,70,80,90],index=1)

filtered=exporters.copy()
if q.strip():
    cols=[x for x in ["exporter_name","ntn","email","telephone","address"] if x in filtered]
    mask=pd.Series(False,index=filtered.index)
    for col in cols: mask |= filtered[col].astype("string").str.contains(q.strip(),case=False,na=False)
    filtered=filtered[mask]

overview, leaders, products, shortlist, diligence, methodology = st.tabs([
    "Executive Brief", "Exporter Intelligence", "Product Portfolio", "Strategic Shortlist", "Data Assurance", "Methodology"
])

with overview:
    k1,k2,k3,k4,k5,k6=st.columns(6)
    total_bn = round(c['total_value_rs']/1e9)
    k1.metric("TDAP reported export value", f"Rs {total_bn:,.0f} bn", help="Total reported export value represented by the records in the loaded TDAP extract. This is not yet a reconciled national export total.")
    k2.metric("Unique exporters", f"{a.unique_exporters:,}", help="Number of distinct exporter entities observed in this chapter extract.")
    k3.metric("Distinct HS8 products", f"{a.unique_hs8:,}", help="Number of distinct 8-digit HS product codes represented in the extract.")
    k4.metric("Top 10 exporters' share", f"{c['top10_share']*100:.0f}%", help="Share of the extract's reported value accounted for by the ten largest exporters.")
    k5.metric("Exporters needed for 60%", f"{c['exporters_to_60pct']:,}", help="Minimum number of top-ranked exporters whose cumulative reported value reaches at least 60% of this extract.")
    k6.metric("HHI concentration index", f"{c['hhi']:,.0f}", help="Herfindahl-Hirschman Index calculated from exporter shares in this extract. Higher values indicate greater concentration.")

    st.caption("All KPI values are calculated from the loaded TDAP extract. Shares and concentration measures describe this extract, not Pakistan's national market, until reconciliation with official national totals is completed.")

    st.subheader("What leadership should know")
    l,r=st.columns([1.15,1])
    with l:
        st.markdown(f"**Concentrated entry point.** Just **{c['exporters_to_60pct']} exporters account for 60%** of reported Chapter {chapter_label} value in this extract, while {a.unique_exporters:,} exporters form the wider base.")
        st.markdown("**Leadership implication.** A targeted engagement programme can begin with the firms controlling the first 60%, while a second pipeline identifies diversified and less-common HS8 capabilities outside the largest firms.")
        st.info("Destination attractiveness, growth, physical unit value and geopolitical fit require the next PBS/global-market enrichment layer.")
    with r:
        gauge=go.Figure(go.Indicator(mode="gauge+number",value=c['top10_share']*100,number={'suffix':'%', 'valueformat':'.0f'},title={'text':'Share held by top 10 exporters'},gauge={'axis':{'range':[0,100]},'steps':[{'range':[0,50]},{'range':[50,100]}]}))
        gauge.update_layout(height=240,margin=dict(l=25,r=25,t=50,b=10))
        st.plotly_chart(gauge,use_container_width=True,config=CLEAN_PLOT_CONFIG)

    st.subheader("Concentration curve")
    pareto=exporters[["rank","cumulative_share"]].copy(); pareto["Cumulative share (%)"]=pareto["cumulative_share"]*100
    fig=px.area(pareto,x="rank",y="Cumulative share (%)",labels={'rank':'Exporter rank'},height=350)
    fig.add_hline(y=60,line_dash="dash",annotation_text="60% strategic coverage")
    fig.update_layout(showlegend=False,margin=dict(l=10,r=10,t=20,b=10))
    st.plotly_chart(fig,use_container_width=True,config=PLOT_CONFIG)

    st.subheader(f"Top {top_n} exporters")
    chart=exporters.head(top_n).sort_values("reported_value_rs")
    fig=px.bar(chart,x="reported_value_rs",y="exporter_name",orientation="h",hover_data=[x for x in ["rank","share","cumulative_share","ntn","email","telephone"] if x in chart],labels={'reported_value_rs':'Reported value (Rs)','exporter_name':''},height=max(500,top_n*27))
    fig.update_layout(margin=dict(l=10,r=25,t=10,b=10), yaxis={'automargin':True})
    st.plotly_chart(fig,use_container_width=True,config=CLEAN_PLOT_CONFIG)
    st.caption("Hover over a bar for rank, share, cumulative share and available contact details. Chart controls are hidden here to keep the executive ranking unobstructed.")

with leaders:
    st.subheader("Exporter ranking, concentration & contact directory")
    st.caption("Operational view for leadership, sector teams and exporter engagement. Click column headers to sort; use search above to locate a firm.")
    ranking_cols=[x for x in ["rank","exporter_name","ntn","reported_value_rs","share","cumulative_share","record_count","avg_value_per_reported_record_rs","hs8_count","hs4_count","largest_hs8","email","telephone","address"] if x in filtered]
    st.dataframe(filtered[ranking_cols],hide_index=True,use_container_width=True,height=680,column_config={
        "rank":"Rank","exporter_name":"Exporter","ntn":"NTN",
        "reported_value_rs":st.column_config.NumberColumn("Reported value (Rs)",format="%,.0f"),
        "share":st.column_config.ProgressColumn("Chapter share",format="%.2f%%",min_value=0,max_value=1),
        "cumulative_share":st.column_config.NumberColumn("Cumulative share",format="%.2%%"),
        "record_count":"Records","avg_value_per_reported_record_rs":st.column_config.NumberColumn("Value / record*",format="%,.0f"),
        "hs8_count":"HS8 breadth","hs4_count":"HS4 breadth","largest_hs8":"Lead HS8","email":"Email","telephone":"Phone","address":"Address"})
    st.caption("*Descriptive value per TDAP reported record; not a physical unit value or price.")
    st.download_button("Download engagement list",filtered[ranking_cols].to_csv(index=False).encode("utf-8-sig"),"exporter_engagement_list.csv","text/csv")

with products:
    st.subheader("HS8 product portfolio")
    p1,p2=st.columns([1.15,1])
    with p1:
        fig=px.treemap(hs8,path=["hs8"],values="reported_value_rs",hover_data=[x for x in ["product_name","exporters","share"] if x in hs8],title=f"Where reported Chapter {chapter_label} value sits")
        fig.update_layout(margin=dict(l=5,r=5,t=45,b=5))
        st.plotly_chart(fig,use_container_width=True,config=CLEAN_PLOT_CONFIG)
    with p2:
        fig=px.scatter(hs8,x="exporters",y="reported_value_rs",size="reported_value_rs",hover_name="hs8",hover_data=["product_name"],log_y=True,title="Scale vs exporter participation")
        fig.update_layout(margin=dict(l=5,r=15,t=45,b=5), yaxis_title="Reported value (Rs)", xaxis_title="Number of exporters")
        st.plotly_chart(fig,use_container_width=True,config=PLOT_CONFIG)
    st.caption("Bubble size represents TDAP-reported value. Hover for HS8/product details. Pan/zoom controls are reduced to the useful analytical set and no longer overlap the exporter ranking chart.")
    st.dataframe(hs8,hide_index=True,use_container_width=True,column_config={"reported_value_rs":st.column_config.NumberColumn("Reported value (Rs)",format="%,.0f"),"share":st.column_config.NumberColumn("Share",format="%.2%%"),"cumulative_share":st.column_config.NumberColumn("Cumulative",format="%.2%%")})

with shortlist:
    st.subheader("Strategic exporter / capability shortlist")
    st.caption("Screening prioritizes observed scale and relative scarcity/breadth. It does not fabricate destination, growth or geopolitical evidence absent from the source.")
    s=screen.copy()
    st.dataframe(s.head(200),hide_index=True,use_container_width=True,column_config={"capability_score":st.column_config.ProgressColumn("Capability score",format="%.1f",min_value=0,max_value=max(100,float(s['capability_score'].max()) if len(s) else 100)),"exported_value_rs":st.column_config.NumberColumn("Reported value (Rs)",format="%,.0f")})
    st.download_button("Download strategic shortlist",s.to_csv(index=False).encode("utf-8-sig"),"strategic_shortlist.csv","text/csv")

with diligence:
    st.subheader("Data assurance & board-use status")
    checks=pd.DataFrame({"Control":["Source rows","Source columns","Duplicate rows","Invalid HS8","Non-positive/missing value","Unique exporters","Unique NTNs","Unique HS8","Detected chapter"],"Result":[a.rows,a.columns,a.duplicate_rows,a.invalid_hs8,a.nonpositive_values,a.unique_exporters,a.unique_ntns,a.unique_hs8,chapter_label]})
    st.dataframe(checks,hide_index=True,use_container_width=True)
    st.markdown("#### Interpretation controls")
    for warning in a.warnings: st.warning(warning)
    st.markdown("#### Evidence status")
    evidence=pd.DataFrame({"Question":["Who exports?","What HS8 capability?","How much TDAP-reported value?","Exporter concentration?","Physical unit value?","Destination / new market?","Growth over time?","Geopolitical opportunity?"],"Status":["Available","Available","Available","Derived","Not available in this extract","Requires PBS HS8 × country","Requires time-series enrichment","Requires external market/policy layer"]})
    st.dataframe(evidence,hide_index=True,use_container_width=True)

with methodology:
    st.subheader("Analytical doctrine")
    st.markdown("""
**Observed:** exporter identity, HS8 product, TDAP reported export value, reported record count and available business-contact fields.  
**Derived:** exporter rank, extract share, cumulative share, concentration thresholds, HHI, HS8/HS4 breadth and first-pass capability indicators.  
**Not inferred:** record count is not quantity; value/record is not unit value; TDAP extract share is not national market share.  
**Next enrichment:** reconcile PBS HS8 × destination × value × quantity × fiscal year; then add world demand, Pakistan share, competitor concentration, tariffs/market access and policy/geopolitical indicators. Firm attribution and national aggregates remain separated unless a defensible linkage exists.
""")
    st.markdown("#### Reproducibility")
    st.code("Input workbook → normalization → due diligence → exporter aggregation → concentration → HS8 capability map → strategic screen → executive dashboard")

st.divider()
st.caption(f"Source sheet: {sheet} · Chapter {chapter_label} · {a.rows:,} rows · {a.unique_exporters:,} exporters | Internal decision-support")
