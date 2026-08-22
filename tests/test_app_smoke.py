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
    assert 'valueformat' in source
