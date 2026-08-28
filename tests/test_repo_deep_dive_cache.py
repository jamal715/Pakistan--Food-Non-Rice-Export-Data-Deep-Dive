from pathlib import Path

from src.deep_dive_fast import load_cross_chapter_cache


ROOT = Path(__file__).resolve().parents[1]


def test_repository_fast_cache_is_synchronized_and_complete():
    pair = load_cross_chapter_cache(
        ROOT / "TDAP_Export_Directory_HS01_24.xlsx",
        ROOT / "data" / "cross_chapter_universe.csv.gz",
        ROOT / "data" / "cross_chapter_universe.manifest.json",
    )
    assert pair is not None
    universe, audit = pair
    assert audit.chapters == [f"{i:02d}" for i in range(1, 25)]
    assert audit.rows == len(universe) == 7637
    assert audit.inconsistent_hs2_rows == 0
    assert universe["_ntn_key"].isna().sum() == 0
    assert int((universe["_ntn_key"] == "").sum()) == audit.missing_ntn_rows
    assert universe["exported_value_rs"].sum() == audit.total_value_rs
