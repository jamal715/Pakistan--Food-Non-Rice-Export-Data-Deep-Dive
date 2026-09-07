from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_WORKBOOK = REPO_ROOT / "TDAP_Export_Directory_HS01_24.xlsx"

OUTPUT_DIR = Path(
    r"C:\Users\jamal.nasir_ncgcl\OneDrive\OneDrive - Higher Education Commission\NCGCL\Export Facility"
)
NTN_UNIVERSE_WORKBOOK = OUTPUT_DIR / "FBR_NTN_Universe_HS01_24.xlsx"
FINAL_WORKBOOK = OUTPUT_DIR / "FBR_Exporter_Verification_HS01_24.xlsx"
STATE_DB = OUTPUT_DIR / "FBR_Exporter_Verification_HS01_24.sqlite3"
RAW_DIR = OUTPUT_DIR / "FBR_Raw_Profile_Snapshots"

FBR_PROFILE_URL = "https://iris.fbr.gov.pk/public/txplogin.xhtml"

SAVE_RAW_HTML = True
SAVE_SCREENSHOTS = False
EXPORT_EVERY_N_SUCCESSFUL = 10

NTN_ALIASES = ["ntn", "detail_NTN", "NTN"]
EXPORTER_NAME_ALIASES = [
    "exporter_name",
    "master_name",
    "company_name_detail",
    "company_name",
]
HS2_ALIASES = ["hs2", "hs_chapter", "hs_chapter_query", "chapter", "HS_Chapter"]
