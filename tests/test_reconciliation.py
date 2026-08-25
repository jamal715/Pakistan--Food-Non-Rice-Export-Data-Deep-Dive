import pandas as pd

from src.analysis import normalize
from src.reconciliation import reconcile_chapter


def _sample():
    return normalize(pd.DataFrame([
        {"ntn": "1", "exporter_name": "A", "hs8": "12010000", "hs4": "1201", "product_name": "P1", "exported_value_rs": 100.0},
        {"ntn": "1", "exporter_name": "A", "hs8": "12020000", "hs4": "1202", "product_name": "P2", "exported_value_rs": 50.0},
        {"ntn": "2", "exporter_name": "B", "hs8": "12010000", "hs4": "1201", "product_name": "P1", "exported_value_rs": 50.0},
        {"ntn": "3", "exporter_name": "C", "hs8": "12020000", "hs4": "1202", "product_name": "P2", "exported_value_rs": 25.0},
    ]))


def test_reconciliation_passes_for_known_chapter():
    result = reconcile_chapter(_sample())
    assert result.passed
    assert result.summary["failed_checks"] == 0
    assert result.summary["source_total_value_rs"] == 225.0
    assert set(result.checks["status"]) == {"PASS"}
    assert "source total = exporter aggregation" in set(result.checks["check"])
    assert "within-HS8 shares reconcile" in set(result.checks["check"])
    assert "within-HS8 ranks reconcile" in set(result.checks["check"])


def test_reconciliation_fails_closed_on_missing_required_field():
    bad = pd.DataFrame({"exporter_name": ["A"], "exported_value_rs": [10.0]})
    result = reconcile_chapter(bad)
    assert not result.passed
    assert result.summary["failed_checks"] == 1
    assert result.checks.iloc[0]["status"] == "FAIL"
