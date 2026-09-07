from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from config import EXPORTER_NAME_ALIASES, HS2_ALIASES, NTN_ALIASES, NTN_UNIVERSE_WORKBOOK, OUTPUT_DIR, SOURCE_WORKBOOK, STATE_DB
from identity import normalize_ntn
from storage import connect, replace_ntn_source


def _first_column(df: pd.DataFrame, aliases: list[str]) -> str | None:
    lower = {str(c).strip().lower(): c for c in df.columns}
    for alias in aliases:
        if alias.lower() in lower:
            return lower[alias.lower()]
    return None


def _chapter_from_sheet_or_data(sheet_name: str, df: pd.DataFrame) -> str | None:
    matches = re.findall(r"(?<!\d)(0?[1-9]|1\d|2[0-4])(?!\d)", sheet_name)
    if matches:
        return f"{int(matches[-1]):02d}"
    hs_col = _first_column(df, HS2_ALIASES)
    if hs_col:
        vals = pd.Series(df[hs_col]).dropna().astype(str).str.extract(r"(\d{1,2})", expand=False).dropna()
        vals = vals[vals.astype(int).between(1, 24)]
        if vals.nunique() == 1:
            return f"{int(vals.iloc[0]):02d}"
    return None


def build_ntn_universe(source_workbook: Path = SOURCE_WORKBOOK) -> pd.DataFrame:
    if not source_workbook.exists():
        raise FileNotFoundError(f"Source workbook not found: {source_workbook}")

    xls = pd.ExcelFile(source_workbook)
    rows = []
    chapter_frames: dict[str, pd.DataFrame] = {}

    for sheet in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet, dtype=object)
        chapter = _chapter_from_sheet_or_data(sheet, df)
        if not chapter or int(chapter) not in range(1, 25):
            continue
        ntn_col = _first_column(df, NTN_ALIASES)
        name_col = _first_column(df, EXPORTER_NAME_ALIASES)
        if not ntn_col:
            continue
        work = pd.DataFrame({
            "ntn": df[ntn_col].map(normalize_ntn),
            "exporter_name": df[name_col].astype("string").str.strip() if name_col else pd.Series([pd.NA] * len(df)),
        })
        work = work[work.ntn.notna()].drop_duplicates()
        work.insert(0, "chapter", chapter)
        rows.append(work)
        chapter_frames[chapter] = work[["ntn", "exporter_name"]].drop_duplicates().sort_values(["ntn", "exporter_name"], na_position="last")

    if not rows:
        raise RuntimeError("No HS01-HS24 sheets with an NTN column were found in the source workbook.")

    all_rows = pd.concat(rows, ignore_index=True).drop_duplicates()
    global_unique = (
        all_rows.groupby("ntn", as_index=False)
        .agg(
            source_exporter_names=("exporter_name", lambda s: " | ".join(sorted({str(x).strip() for x in s.dropna() if str(x).strip()}))),
            source_chapters=("chapter", lambda s: ",".join(sorted(set(s)))),
        )
        .sort_values("ntn").reset_index(drop=True)
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(NTN_UNIVERSE_WORKBOOK, engine="openpyxl") as writer:
        global_unique.to_excel(writer, sheet_name="ALL_UNIQUE_NTN", index=False)
        for chapter in [f"{i:02d}" for i in range(1, 25)]:
            frame = chapter_frames.get(chapter, pd.DataFrame(columns=["ntn", "exporter_name"]))
            frame.to_excel(writer, sheet_name=f"HS{chapter}", index=False)

    with connect(STATE_DB) as conn:
        replace_ntn_source(conn, all_rows)

    print(f"Source workbook: {source_workbook}")
    print(f"Chapter memberships with NTN: {len(all_rows):,}")
    print(f"Globally unique NTN: {global_unique.ntn.nunique():,}")
    print(f"NTN universe workbook: {NTN_UNIVERSE_WORKBOOK}")
    print(f"Checkpoint database: {STATE_DB}")
    return global_unique


if __name__ == "__main__":
    build_ntn_universe()
