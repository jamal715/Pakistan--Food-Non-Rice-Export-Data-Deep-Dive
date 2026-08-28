from pathlib import Path

import pandas as pd

from src.deep_dive import build_verified_contact_directory, exporter_index, exporter_portfolio, hs8_exporters
from src.deep_dive_fast import (
    build_fast_indexes,
    exporter_portfolio_fast,
    find_exporters_fast,
    hs8_exporters_fast,
)


def _universe():
    return pd.DataFrame([
        {"chapter": "12", "hs8": "12074000", "product_name": "Sesamum seeds", "exporter_name": "ALPHA LTD", "ntn": "100", "_ntn_key": "100", "_exporter_key": "ALPHA LTD", "exported_value_rs": 60.0, "email": "a@example.com"},
        {"chapter": "12", "hs8": "12075000", "product_name": "Mustard seeds", "exporter_name": "ALPHA LTD", "ntn": "100", "_ntn_key": "100", "_exporter_key": "ALPHA LTD", "exported_value_rs": 40.0, "email": "a@example.com"},
        {"chapter": "12", "hs8": "12074000", "product_name": "Sesamum seeds", "exporter_name": "BETA LTD", "ntn": "200", "_ntn_key": "200", "_exporter_key": "BETA LTD", "exported_value_rs": 40.0, "email": "b@example.com"},
    ])


def test_fast_indexes_match_existing_indexes():
    universe = _universe()
    fast_index, fast_contacts = build_fast_indexes(universe, None)
    pd.testing.assert_frame_equal(fast_index.reset_index(drop=True), exporter_index(universe).reset_index(drop=True))
    pd.testing.assert_frame_equal(fast_contacts.reset_index(drop=True), build_verified_contact_directory(universe, None).reset_index(drop=True))
    hits = find_exporters_fast(fast_index, "100")
    assert hits.iloc[0]["ntn"] == "100"


def test_fast_exporter_portfolio_preserves_math():
    universe = _universe()
    _, directory = build_fast_indexes(universe, None)
    original = exporter_portfolio(universe, "100", None)
    fast = exporter_portfolio_fast(universe, "100", directory)
    pd.testing.assert_frame_equal(fast.table.reset_index(drop=True), original.table.reset_index(drop=True))
    assert fast.summary["total_reported_value_rs"] == original.summary["total_reported_value_rs"] == 100.0
    assert round(float(fast.table["share_of_exporter"].sum()), 12) == 1.0
    assert set(fast.checks["status"]) == {"PASS"}


def test_fast_hs8_exporters_preserves_math():
    universe = _universe()
    _, directory = build_fast_indexes(universe, None)
    original = hs8_exporters(universe, "12074000", None)
    fast = hs8_exporters_fast(universe, "12074000", directory)
    pd.testing.assert_frame_equal(fast.table.reset_index(drop=True), original.table.reset_index(drop=True))
    assert fast.summary["total_reported_value_rs"] == original.summary["total_reported_value_rs"] == 100.0
    assert fast.table.iloc[0]["share_of_hs8"] == 0.6
    assert fast.table.iloc[1]["share_of_hs8"] == 0.4
    assert set(fast.checks["status"]) == {"PASS"}
