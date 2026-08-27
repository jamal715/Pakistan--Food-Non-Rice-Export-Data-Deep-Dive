import numpy as np
import pandas as pd

from src.deep_dive import (
    build_verified_contact_directory,
    exporter_portfolio,
    find_exporters,
    hs8_exporters,
)


def universe():
    return pd.DataFrame({
        "chapter": ["07", "12", "12", "12", "12"],
        "source_sheet": ["HS_07", "HS_12", "HS_12", "HS_12", "HS_12"],
        "exporter_name": ["ALPHA TRADING", "ALPHA TRADING LTD", "ALPHA TRADING", "BETA FOODS", "NO NTN CO"],
        "ntn": ["111", "111", "111", "222", pd.NA],
        "_ntn_key": ["111", "111", "111", "222", ""],
        "_exporter_key": ["ALPHA TRADING", "ALPHA TRADING LTD", "ALPHA TRADING", "BETA FOODS", "NO NTN CO"],
        "hs8": ["07019000", "12074000", "12141000", "12074000", "12074000"],
        "hs4": ["0701", "1207", "1214", "1207", "1207"],
        "product_name": ["Potatoes", "Sesamum seeds", "Lucerne meal", "Sesamum seeds", "Sesamum seeds"],
        "exported_value_rs": [100.0, 300.0, 100.0, 150.0, 50.0],
        "email": ["a@example.com", "a@example.com", "a2@example.com", "b@example.com", "n@example.com"],
    })


def contacts():
    return pd.DataFrame({
        "HS_Chapter": ["07", "12", "12", "12", "12"],
        "exporter_name": ["ALPHA TRADING", "ALPHA TRADING LTD", "ALPHA TRADING", "BETA FOODS", "NO NTN CO"],
        "telephone": ["03001111111", "03001111111", "03001111111", "03002222222", "03009999999"],
    })


def test_exporter_search_uses_ntn_as_primary_identity_across_chapters():
    hits = find_exporters(universe(), "ALPHA")
    assert len(hits) == 1
    assert hits.iloc[0].ntn == "111"
    assert hits.iloc[0].chapters == 2
    assert hits.iloc[0].hs8_products == 3
    assert hits.iloc[0].reported_value_rs == 500


def test_exporter_portfolio_math_reconciles_across_chapters():
    result = exporter_portfolio(universe(), "111", contacts())
    assert result.summary["total_reported_value_rs"] == 500
    assert result.summary["hs8_products"] == 3
    assert result.summary["chapters"] == 2
    assert np.isclose(result.table["share_of_exporter"].sum(), 1.0)
    sesame = result.table[result.table.hs8 == "12074000"].iloc[0]
    assert sesame.reported_value_rs == 300
    assert np.isclose(sesame.share_of_exporter, 0.60)
    assert set(result.checks.status) == {"PASS"}
    assert "03001111111" in result.summary["phones"]


def test_hs8_view_uses_full_hs8_denominator_and_keeps_missing_ntn_visible():
    result = hs8_exporters(universe(), "12074000", contacts())
    assert result.summary["total_reported_value_rs"] == 500
    assert result.summary["exporters"] == 3
    assert np.isclose(result.table["share_of_hs8"].sum(), 1.0)
    alpha = result.table[result.table.ntn == "111"].iloc[0]
    beta = result.table[result.table.ntn == "222"].iloc[0]
    missing = result.table[result.table.ntn == ""].iloc[0]
    assert np.isclose(alpha.share_of_hs8, 0.60)
    assert np.isclose(beta.share_of_hs8, 0.30)
    assert np.isclose(missing.share_of_hs8, 0.10)
    assert "NTN unavailable" in missing.identity_status
    assert missing.phone == ""
    assert set(result.checks.status) == {"PASS"}


def test_contact_directory_withholds_name_only_phone_when_ntn_is_missing():
    directory = build_verified_contact_directory(universe(), contacts())
    assert set(directory.ntn) == {"111", "222"}
    assert "03001111111" in directory.loc[directory.ntn == "111", "phones"].iloc[0]
    assert "03002222222" in directory.loc[directory.ntn == "222", "phones"].iloc[0]
    assert "03009999999" not in " ".join(directory.phones.tolist())


def test_same_name_with_multiple_ntns_does_not_receive_sidecar_phone():
    u = universe().copy()
    extra = u.iloc[[3]].copy()
    extra["chapter"] = "12"
    extra["exporter_name"] = "DUPLICATE NAME"
    extra["_exporter_key"] = "DUPLICATE NAME"
    extra["ntn"] = "333"
    extra["_ntn_key"] = "333"
    extra["hs8"] = "12141000"
    extra["exported_value_rs"] = 25.0
    extra2 = extra.copy()
    extra2["ntn"] = "444"
    extra2["_ntn_key"] = "444"
    u = pd.concat([u, extra, extra2], ignore_index=True)
    c = contacts().copy()
    c = pd.concat([c, pd.DataFrame({"HS_Chapter": ["12"], "exporter_name": ["DUPLICATE NAME"], "telephone": ["03005555555"]})], ignore_index=True)
    directory = build_verified_contact_directory(u, c)
    assert directory.loc[directory.ntn.isin(["333", "444"]), "phones"].eq("").all()
