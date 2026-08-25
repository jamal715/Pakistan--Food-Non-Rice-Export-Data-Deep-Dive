import pandas as pd
from src.analysis import normalize, audit, concentration, hs8_table, strategic_screen


def sample():
    return pd.DataFrame({
        "master_name": ["A", "B", "C"],
        "ptc_code": [12074000, 12074000, 12119000],
        "ExpSum": [60, 30, 10],
        "Count(*)": [3, 2, 1],
        "NTN": ["1", "2", "3"],
        "product_name": ["Sesame", "Sesame", "Plants"],
    })


def test_normalization_and_audit():
    df = normalize(sample()); a = audit(df)
    assert a.missing_required == []
    assert a.unique_exporters == 3
    assert a.unique_hs8 == 2
    assert set(a.chapters) == {"12"}


def test_concentration():
    c = concentration(normalize(sample()))
    assert c["total_value_rs"] == 100
    assert round(c["top1_share"], 2) == 0.60
    assert c["exporters_to_60pct"] == 1


def test_hs8_aggregation():
    t = hs8_table(normalize(sample()))
    sesame = t.loc[t.hs8 == "12074000"].iloc[0]
    assert sesame.reported_value_rs == 90
    assert sesame.exporters == 2


def test_strategic_screen_is_exporter_hs8_and_explainable():
    df = normalize(pd.DataFrame({
        "master_name": ["A", "A", "B", "C"],
        "ptc_code": [12074000, 12074000, 12074000, 12119000],
        "ExpSum": [40, 20, 30, 10],
        "Count(*)": [2, 1, 2, 1],
        "NTN": ["1", "1", "2", "3"],
        "product_name": ["Sesame", "Sesame", "Sesame", "Plants"],
    }))
    s = strategic_screen(df)
    a = s[(s.ntn == "1") & (s.hs8 == "12074000")].iloc[0]
    assert a.hs8_value_rs == 60
    assert a.firm_chapter_value_rs == 60
    assert a.rank_within_hs8 == 1
    assert a.firms_in_hs8 == 2
    assert round(a.share_within_hs8, 4) == round(60/90, 4)
    assert "HS8 rank 1 of 2" in a.screening_reason
    assert "capability_score" not in s.columns
