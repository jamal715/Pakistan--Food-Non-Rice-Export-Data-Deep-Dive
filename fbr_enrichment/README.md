# FBR Taxpayer Profile Enrichment — HS01–24

This folder is deliberately isolated from the Streamlit/export-analysis application. It does **not** modify `app.py`, exporter values, HS8 calculations, rankings, HHI, reconciliation, strategic tiers, or the existing contact-enrichment layer.

## Purpose

For every unique NTN observed in `TDAP_Export_Directory_HS01_24.xlsx`, build an auditable FBR verification dataset containing legal identity, tax/registration status, registered address, masked FBR contact fields, and all FBR business/branch Principal Activity records.

The FBR profile is a verification/enrichment source. It is not treated as proof that a listed branch currently produces the relevant HS8 product or is currently exporting.

## FBR route review — September 2026

The current public FBR **Taxpayer Profile Inquiry** exposes the required legal identity, business/branch address and Principal Activity fields through the IRIS Online Verification interface, but that profile inquiry is CAPTCHA-protected.

FBR provides legitimate bulk/download routes for Active Taxpayer Lists (Income Tax and Sales Tax), but those lists do not expose the full Principal Activity/business-branch profile required by this study. Historical eFBR/RegSys detail URLs also appear in older public material, but no reliable current official non-CAPTCHA bulk/API route for the full profile fields was identified and the legacy routes are therefore not used as an unattended source.

The collector **does not solve or bypass CAPTCHA**. The user reads each challenge. The software handles the repetitive work around it: global NTN de-duplication, browser navigation, NTN filling, submission, extraction, parsing, identity checks, checkpointing, retries, chapter mapping, and Excel production.

If FBR/PRAL later provides an authorised bulk extract/API, only the retrieval adapter needs to change; the schema, parser, identity controls and output remain usable.

Official references:

- IRIS / Online Verification: https://iris.fbr.gov.pk/public/txplogin.xhtml
- FBR ATL status guidance: https://www.fbr.gov.pk/categ/check-active-taxpayer-status/51147/30859/71169
- FBR ATL downloads: https://www.fbr.gov.pk/download-atl/132041

## Fixed output location

The scripts write to:

`C:\Users\jamal.nasir_ncgcl\OneDrive\OneDrive - Higher Education Commission\NCGCL\Export Facility`

Files created:

- `FBR_NTN_Universe_HS01_24.xlsx`
- `FBR_Exporter_Verification_HS01_24.xlsx`
- `FBR_Exporter_Verification_HS01_24.sqlite3` — durable checkpoint database
- `FBR_Raw_Profile_Snapshots\` — raw HTML evidence when enabled

The SQLite checkpoint is intentional. Saving a large XLSX after every NTN is slower and more vulnerable to interruption. Every completed profile is committed immediately to SQLite; the Excel workbook is refreshed periodically and when the collector exits.

## Output workbook design

### `Taxpayer_Master`

One row per globally unique NTN. The first three columns are fixed as requested:

1. `ntn`
2. `legal_name_fbr`
3. `principal_activity_raw`

For a taxpayer with several FBR branch/activity rows, `principal_activity_raw` joins the distinct raw FBR activity strings with ` | ` for the one-row master view.

Other master fields include reference number, taxpayer category, sales-tax registration/status, registration date, tax office, income-tax status, registered address, masked FBR email/cell, aggregated business names/addresses/activity codes, source exporter names/chapters, identity status and verification timestamp.

### `Business_Activities`

Nothing is lost through aggregation. This sheet keeps one row per:

`NTN × FBR business/branch × Principal Activity`

with:

- `business_name`
- `business_address`
- `activity_code`
- `activity_level_1`
- `activity_level_2`
- `activity_detail`
- `principal_activity_raw`

### Other sheets

- `ALL_UNIQUE_NTN` — globally deduplicated queue/status
- `HS01` … `HS24` — one chapter-specific enriched view per HS chapter
- `RUN_LOG` — audit trail of completed/failed/skipped records

## Identity safeguards

1. NTN is the primary identifier.
2. A queried NTN must match FBR's Registration No. **or** the base of FBR's Reference No.
3. Export-dataset names are compared against FBR legal name and FBR business names.
4. A material name divergence is labelled `manual_review`; it is not silently treated as a verified downstream join.
5. One NTN is queried only once globally even if it occurs in several chapters or HS8 products.
6. Old/short NTNs are preserved as observed; the code does not zero-pad them.
7. The source chapter/exporter mapping is rebuilt from the authoritative 24-sheet workbook each run without deleting already completed FBR profiles.

## Installation — VS Code / PowerShell

Run from the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r fbr_enrichment\requirements.txt
playwright install chromium
```

## Step 1 — build the NTN universe

```powershell
python fbr_enrichment\build_ntn_universe.py
```

This reads the repository's existing `TDAP_Export_Directory_HS01_24.xlsx`, extracts unique NTNs from every HS01–HS24 sheet, globally de-duplicates them, and writes:

`FBR_NTN_Universe_HS01_24.xlsx`

with `ALL_UNIQUE_NTN` plus `HS01`–`HS24`.

Review this file before profile collection.

## Step 2 — validate one known NTN first

Use the example already manually checked on FBR:

```powershell
python fbr_enrichment\collect_profiles.py --ntn 2573554
```

A Chromium window opens the FBR public verification portal. The script attempts to open **Taxpayer Profile Inquiry**, choose `NTN`, and fill the NTN. Read the CAPTCHA shown in the browser and type those characters into the terminal. The script then submits the form, parses the result, performs NTN/name identity checks, stores the raw evidence and refreshes the output workbook.

If FBR changes the page layout and automatic form selection fails, the terminal tells you to open `Taxpayer Profile Inquiry` and choose `NTN` manually. The parser/checkpoint logic remains unchanged.

## Step 3 — pilot ten records

```powershell
python fbr_enrichment\collect_profiles.py --limit 10
```

Review the resulting `Taxpayer_Master`, `Business_Activities`, and any `manual_review` identities before scaling.

## Step 4 — process/resume the queue

```powershell
python fbr_enrichment\collect_profiles.py
```

The process is resumable. Completed NTNs are not queried again.

At a CAPTCHA prompt:

- enter the displayed characters to proceed;
- type `SKIP` to leave that NTN for later;
- type `QUIT` to stop and export the current workbook.

Stopping with `Ctrl+C` is also safe; the current workbook is exported during shutdown.

## Step 5 — rebuild the Excel workbook at any time

```powershell
python fbr_enrichment\export_results.py
```

## Research interpretation

The enrichment can support statements such as:

- an NTN resolves to a named taxpayer in FBR;
- FBR records an importer/exporter or manufacturing activity;
- FBR records a particular business/branch address;
- income/sales-tax status was displayed on the stated verification date.

It should **not** by itself be described as proof that the registered branch currently produces the relevant HS8 product, that the registered address is the physical production site, or that the taxpayer is currently exporting. Those remain questions for commercial verification.
