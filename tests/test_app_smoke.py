from pathlib import Path


def test_executive_dashboard_readability_guards():
    source = Path("app.py").read_text(encoding="utf-8")
    assert 'TDAP reported export value' in source
    assert 'Unique exporters' in source
    assert 'Distinct HS8 products' in source
    assert "Top 10 exporters' share" in source
    assert 'Exporters needed for 60%' in source
    assert 'HHI concentration index' in source
    assert 'CLEAN_PLOT_CONFIG' in source
    assert 'displayModeBar' in source
    assert "{c['top10_share']*100:.0f}%" in source
    assert 'Observed HS8 share' in source
    assert 'Evidence tier' in source
    assert 'Why surfaced' in source


def test_app_reloads_analysis_engine_and_guards_screen_schema():
    source = Path("app.py").read_text(encoding="utf-8")
    assert 'importlib.reload(analysis)' in source
    assert 'SCREEN_REQUIRED' in source
    assert 'evidence_tier' in source
    assert 'rank_within_hs8' in source
    assert 'share_within_hs8' in source
    assert 'Analytical engine/schema mismatch' in source


def test_master_workbook_and_single_chapter_modes_are_preserved():
    source = Path("app.py").read_text(encoding="utf-8")
    assert 'MASTER_FILE = Path("TDAP_Export_Directory_HS01_24.xlsx")' in source
    assert 'LEGACY_FILE = Path("Chapter_12.xlsx")' in source
    assert 'Select HS chapter' in source
    assert 'Use a different workbook' in source
    assert 'Repository master workbook' in source
    assert 'Legacy single-chapter workbook' in source
    assert 'active analytical sheet contains more than one HS2 chapter' in source


def test_ncgcl_logo_is_supported_in_hero():
    source = Path("app.py").read_text(encoding="utf-8")
    assert 'LOGO_FILE = Path("assets/ncgcl_logo.png")' in source
    assert 'hero-logo' in source
    assert 'NCGCL logo' in source


def test_reconciliation_is_visible_and_old_copy_is_removed():
    source = Path("app.py").read_text(encoding="utf-8")
    assert 'reconcile_chapter' in source
    assert 'Reconciliation status' in source
    assert 'Download reconciliation report' in source
    assert 'Data assurance & reconciliation' in source
    assert 'STRATEGIC PLANNING CELL' not in source
    assert 'How to read the screen' not in source
    assert "The previous 65% scale + 35% scarcity" not in source


def test_strategic_shortlist_has_safe_phone_next_to_ntn_and_compact_tiers():
    source = Path("app.py").read_text(encoding="utf-8")
    assert 'CONTACT_FILE = Path("Contact_list_by_Company_hs_chapter.xlsx")' in source
    assert 'enrich_contact_display' in source
    assert '["tier", "chapter_rank", "exporter_name", "ntn", "contact_phone", "firm_chapter_value_rs"' in source
    assert '"contact_phone": "Phone"' in source
    assert 'Contact enrichment integrity' in source
    assert 'Ambiguous identity keys' in source
    assert 'm1.metric("Tier A",' in source
    assert 'm2.metric("Tier B",' in source
    assert 'm3.metric("Tier C",' in source
    assert '"A — high-priority evidence": "A"' in source
    assert 'tier_filter = st.multiselect("Evidence tier", tier_options' in source


def test_cross_chapter_exporter_product_deep_dive_is_separate_and_auditable():
    source = Path("app.py").read_text(encoding="utf-8")
    assert 'Exporter / Product Deep Dive' in source
    assert 'load_cross_chapter_universe' in source
    assert 'Exporter (name or NTN)' in source
    assert 'HS8 product' in source
    assert 'Select verified exporter identity' in source
    assert 'Share of exporter portfolio' in source
    assert 'Share of HS8' in source
    assert 'HS8 share of exporter = exporter value in that HS8 / exporter total value across all loaded HS chapters' in source
    assert 'Exporter share of HS8 = exporter reported value in the HS8 / total reported value of that HS8' in source
    assert 'This cross-chapter view does not feed back into chapter KPIs or tiers.' in source

def test_performance_cache_forms_and_percentage_precision():
    source = Path("app.py").read_text(encoding="utf-8")
    assert "_chapter_sheets_from_path" in source
    assert "_selected_sheet_from_path" in source
    assert "_contacts_from_path" in source
    assert "_cross_chapter_repo_cache" in source
    assert "validated fast cache" in source
    assert 'st.form("deep_exporter_search_form"' in source
    assert 'st.form("deep_hs8_search_form"' in source
    assert "find_exporters_fast" in source
    assert "exporter_portfolio_fast" in source
    assert "hs8_exporters_fast" in source
    assert "{c['top10_share']*100:.2f}%" in source
    assert 'tickformat=".2%"' in source
    assert 'format="%.1%%"' not in source

