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
    # Strategic-screen V4 no longer renders the old Plotly gauge whose
    # Indicator number used `valueformat`. Guard the current explicit
    # percentage formatting and evidence-screen labels instead.
    assert "{c['top10_share']*100:.0f}%" in source
    assert 'Observed HS8 share' in source
    assert 'Evidence tier' in source
    assert 'Why surfaced' in source
