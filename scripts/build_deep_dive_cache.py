from pathlib import Path

from src.deep_dive_fast import write_cross_chapter_cache


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "TDAP_Export_Directory_HS01_24.xlsx"
CACHE = ROOT / "data" / "cross_chapter_universe.csv.gz"
MANIFEST = ROOT / "data" / "cross_chapter_universe.manifest.json"


if __name__ == "__main__":
    manifest = write_cross_chapter_cache(SOURCE, CACHE, MANIFEST)
    print(
        f"Built {CACHE.relative_to(ROOT)}: {manifest['cache_rows']:,} rows, "
        f"{len(manifest['chapters'])} chapters, source sha256={manifest['source_sha256']}"
    )
