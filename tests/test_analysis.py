import pandas as pd
from src.analysis import normalize, audit, concentration, hs8_table


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
    df = normalize(sample())
    a = audit(df)
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
