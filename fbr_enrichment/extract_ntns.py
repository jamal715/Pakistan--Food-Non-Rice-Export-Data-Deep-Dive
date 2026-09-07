from __future__ import annotations

from pathlib import Path
import re
import pandas as pd

SOURCE = Path("TDAP_Export_Directory_HS01_24.xlsx")
OUTPUT_DIR = Path(r"C:\Users\jamal.nasir_ncgcl\OneDrive\OneDrive - Higher Education Commission\NCGCL\Export Facility")
OUTPUT = OUTPUT_DIR / "FBR_Exporter_Verification_HS01_24.xlsx"

NTN_ALIASES = ["ntn", "detail_ntn", "NTN"]
NAME_ALIASES = ["exporter_name", "master_name", "company_name_detail", "company_name"]
CHAPTER_ALIASES = ["hs_chapter_query", "hs_chapter", "chapter", "hs2"]


def clean_ntn(value) -> str | None:
    if pd.isna(value):
        return None
    text = re.sub(r"\D", "", str(value).strip())
    text = text.lstrip("0") or "0"
    return text if text and text != "0" else None


def pick_column(df: pd.DataFrame, aliases: list[str]) -> str | None:
    lower = {str(c).strip().lower(): c for c in df.columns}
    for alias in aliases:
        if alias.lower() in lower:
            return lower[alias.lower()]
    return None


def infer_chapter(sheet: str, df: pd.DataFrame) -> str:
    chapter_col = pick_column(df, CHAPTER_ALIASES)
    if chapter_col:
        vals = (
            df[chapter_col]
            .dropna()
            .astype(str)
            .str.extract(r"(\d{1,2})", expand=False)
            .dropna()
        )
        if not vals.empty:
            return vals.iloc[0].zfill(2)
    m = re.search(r"(?:HS|CHAPTER)?\s*0?(\d{1,2})", sheet, flags=re.I)
    if m:
        return m.group(1).zfill(2)
    raise ValueError(f"Could not infer HS chapter from sheet {sheet!r}")


def extract() -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    if not SOURCE.exists():
        raise FileNotFoundError(f"Source workbook not found: {SOURCE.resolve()}")

    xls = pd.ExcelFile(SOURCE)
    chapter_frames: dict[str, list[pd.DataFrame]] = {}

    for sheet in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet)
        ntn_col = pick_column(df, NTN_ALIASES)
        if ntn_col is None:
            continue
        name_col = pick_column(df, NAME_ALIASES)
        chapter = infer_chapter(sheet, df)
        if chapter not in {f"{i:02d}" for i in range(1, 25)}:
            continue

        out = pd.DataFrame({
            "hs_chapter": chapter,
            "ntn": df[ntn_col].map(clean_ntn),
            "exporter_name_source": df[name_col].astype("string").str.strip() if name_col else pd.NA,
            "source_sheet": sheet,
        }).dropna(subset=["ntn"])

        # One row per chapter × NTN; retain all observed name variants for auditability.
        grouped = (
            out.groupby(["hs_chapter", "ntn"], as_index=False)
            .agg(
                exporter_name_source=("exporter_name_source", lambda s: " | ".join(sorted({x for x in s.dropna().astype(str) if x}))),
                source_sheet=("source_sheet", "first"),
            )
        )
        chapter_frames.setdefault(chapter, []).append(grouped)

    per_chapter: dict[str, pd.DataFrame] = {}
    for chapter in [f"{i:02d}" for i in range(1, 25)]:
        frames = chapter_frames.get(chapter, [])
        if frames:
            c = pd.concat(frames, ignore_index=True)
            c = (
                c.groupby(["hs_chapter", "ntn"], as_index=False)
                .agg(
                    exporter_name_source=("exporter_name_source", lambda s: " | ".join(sorted({x for x in s.dropna().astype(str) if x}))),
                    source_sheet=("source_sheet", lambda s: " | ".join(sorted(set(s.astype(str))))),
                )
                .sort_values(["exporter_name_source", "ntn"], na_position="last")
                .reset_index(drop=True)
            )
        else:
            c = pd.DataFrame(columns=["hs_chapter", "ntn", "exporter_name_source", "source_sheet"])
        per_chapter[chapter] = c

    all_rows = pd.concat(per_chapter.values(), ignore_index=True)
    master = (
        all_rows.groupby("ntn", as_index=False)
        .agg(
            exporter_name_source=("exporter_name_source", lambda s: " | ".join(sorted({x for x in s.dropna().astype(str) if x}))),
            chapters=("hs_chapter", lambda s: ",".join(sorted(set(s.astype(str))))),
            chapter_count=("hs_chapter", "nunique"),
        )
        .sort_values(["exporter_name_source", "ntn"], na_position="last")
        .reset_index(drop=True)
    )
    master["status"] = "pending"
    master["last_attempt"] = pd.NaT
    master["error"] = pd.NA
    return master, per_chapter


def initialize_workbook() -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    master, per_chapter = extract()

    with pd.ExcelWriter(OUTPUT, engine="openpyxl") as writer:
        # Empty master/result sheets are created now; collector will replace them later.
        pd.DataFrame(columns=[
            "ntn", "legal_name_fbr", "principal_activity_raw", "reference_no",
            "taxpayer_category", "registered_for_sales_tax", "sales_tax_registered_since",
            "registered_on", "tax_office", "income_tax_status", "sales_tax_status",
            "registered_address", "masked_email_fbr", "masked_cell_fbr",
            "verification_date", "source"
        ]).to_excel(writer, sheet_name="Taxpayer_Master", index=False)

        pd.DataFrame(columns=[
            "ntn", "legal_name_fbr", "business_name", "business_address", "activity_code",
            "activity_level_1", "activity_level_2", "activity_detail", "principal_activity_raw"
        ]).to_excel(writer, sheet_name="Business_Activities", index=False)

        master.to_excel(writer, sheet_name="ALL_UNIQUE_NTN", index=False)
        for chapter, frame in per_chapter.items():
            frame.to_excel(writer, sheet_name=f"HS{chapter}", index=False)

        pd.DataFrame(columns=["ntn", "reason", "details", "timestamp"]).to_excel(writer, sheet_name="Manual_Review", index=False)
        pd.DataFrame(columns=["timestamp", "ntn", "event", "details"]).to_excel(writer, sheet_name="Run_Log", index=False)

    print(f"Created: {OUTPUT}")
    print(f"Global unique NTNs: {len(master):,}")
    for chapter, frame in per_chapter.items():
        print(f"HS{chapter}: {len(frame):,} unique NTNs")
    return OUTPUT


if __name__ == "__main__":
    initialize_workbook()
