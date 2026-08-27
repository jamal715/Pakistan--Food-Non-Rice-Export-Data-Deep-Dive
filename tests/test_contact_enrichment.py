import pandas as pd

from src.contact_enrichment import enrich_contact_display


def _raw():
    return pd.DataFrame({
        "exporter_name": ["SAFE CO", "HANI TRADING COMPANY", "HANI TRADING COMPANY", "BOBY TRADING COMPANY", "BOBY TRADING COMPANY"],
        "ntn": ["111", "222", "222", "333", "444"],
        "hs8": ["12010000", "12020000", "12030000", "12040000", "12050000"],
        "exported_value_rs": [100.0, 80.0, 20.0, 60.0, 40.0],
    })


def _target():
    return pd.DataFrame({
        "exporter_name": ["SAFE CO", "HANI TRADING COMPANY", "HANI TRADING COMPANY", "BOBY TRADING COMPANY", "BOBY TRADING COMPANY"],
        "ntn": ["111", "222", "222", "333", "444"],
        "hs8": ["12010000", "12020000", "12030000", "12040000", "12050000"],
        "chapter_rank": [1, 2, 2, 3, 4],
        "firm_chapter_value_rs": [100.0, 100.0, 100.0, 60.0, 40.0],
    })


def _contacts():
    return pd.DataFrame({
        "HS_Chapter": ["12", "12", "12", "12", "12"],
        "exporter_name": ["SAFE CO", "HANI TRADING COMPANY", "HANI TRADING COMPANY", "BOBY TRADING COMPANY", "BOBY TRADING COMPANY"],
        "telephone": ["0211111111", "", "04235788303", "", "0715804233"],
    })


def test_contact_enrichment_is_display_only_and_row_stable():
    target = _target()
    before = target.copy(deep=True)
    out, audit = enrich_contact_display(target, _raw(), _contacts(), "12")

    assert len(out) == len(before)
    pd.testing.assert_frame_equal(out[before.columns], before)
    assert out.loc[out.exporter_name == "SAFE CO", "contact_phone"].tolist() == ["0211111111"]
    assert out.loc[out.exporter_name == "HANI TRADING COMPANY", "contact_phone"].tolist() == ["04235788303", "04235788303"]

    # Same chapter + same name but two distinct NTNs is deliberately withheld.
    assert out.loc[out.exporter_name == "BOBY TRADING COMPANY", "contact_phone"].fillna("").eq("").all()
    assert audit.ambiguous_identity_keys >= 1


def test_conflicting_contact_numbers_are_withheld_instead_of_guessed():
    contacts = pd.DataFrame({
        "HS_Chapter": ["12", "12"],
        "exporter_name": ["SAFE CO", "SAFE CO"],
        "telephone": ["0211111111", "0219999999"],
    })
    target = _target().iloc[[0]].copy()
    raw = _raw().iloc[[0]].copy()
    out, audit = enrich_contact_display(target, raw, contacts, "12")
    assert out.contact_phone.fillna("").iloc[0] == ""
    assert audit.ambiguous_contact_keys == 1


def test_existing_source_phone_has_priority_over_sidecar():
    target = _target().iloc[[0]].copy()
    target["telephone"] = ["03001234567"]
    raw = _raw().iloc[[0]].copy()
    out, audit = enrich_contact_display(target, raw, _contacts(), "12")
    assert out.contact_phone.iloc[0] == "03001234567"
    assert out.contact_phone_source.iloc[0] == "source workbook"
    assert audit.rows_with_source_phone == 1
    pd.testing.assert_series_equal(out["telephone"], target["telephone"], check_names=False)
