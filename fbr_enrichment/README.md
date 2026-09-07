# FBR Exporter Enrichment Pipeline

This folder is intentionally isolated from the existing export-intelligence dashboard and analytical calculations. It reads `TDAP_Export_Directory_HS01_24.xlsx`, builds a deduplicated NTN universe, and enriches that universe with FBR taxpayer-profile information without modifying the source workbook or any existing ranking/share/HHI logic.

## Route review

The official FBR site currently provides downloadable Active Taxpayer Lists (Income Tax and Sales Tax), which are suitable for bulk status matching. The public IRIS Taxpayer Profile Inquiry exposes the richer fields needed here (legal name, registration details, registered address, branch/business records and principal activity) but its public browser workflow is CAPTCHA-gated. No documented public bulk API for those richer Taxpayer Profile Inquiry fields was identified during the route review.

`api.fbr.gov.pk` exists as FBR's API-management host, but no public documentation was found for a taxpayer-profile endpoint that returns the required principal-activity and branch-address fields for arbitrary NTNs. This project therefore does **not** depend on undocumented/reverse-engineered endpoints or CAPTCHA bypassing.

The collector is built with a provider boundary so an authorized FBR/PRAL API or bulk extract can be plugged in later without changing the output schema.

## Output location

Default Windows output directory:

`C:\Users\jamal.nasir_ncgcl\OneDrive\OneDrive - Higher Education Commission\NCGCL\Export Facility`

Final workbook:

`FBR_Exporter_Verification_HS01_24.xlsx`

## Output workbook

The workbook contains:

- `Taxpayer_Master`: one row per NTN.
- `Business_Activities`: one row per NTN × FBR business/branch/activity record.
- `ALL_UNIQUE_NTN`: globally deduplicated NTN list with processing status.
- `HS01` ... `HS24`: chapter-specific NTN views linked back to the globally deduplicated identities.
- `Manual_Review`: identity or parsing exceptions.
- `Run_Log`: processing/audit log.

`principal_activity_raw` is the third column in `Taxpayer_Master`. Where FBR lists more than one distinct principal activity, the master sheet joins the distinct raw activities using ` | ` while `Business_Activities` preserves each row separately.

## Identity rules

1. NTN is the authoritative exporter identity.
2. A globally unique NTN is queried only once, regardless of the number of chapters/HS8s in which it appears.
3. FBR Registration No/Reference No must reconcile to the queried NTN before automatic enrichment.
4. Exporter names are retained for comparison and review but do not override an NTN mismatch.
5. Ambiguous or inconsistent records are placed in `Manual_Review`; no guessed enrichment is written.
6. The export source workbook is never overwritten.

## Usage

Install dependencies:

```powershell
pip install -r fbr_enrichment/requirements.txt
playwright install chromium
```

Build the 24-sheet + global NTN universe:

```powershell
python fbr_enrichment/extract_ntns.py
```

Run the profile collector:

```powershell
python fbr_enrichment/collect_profiles.py
```

The collector uses a visible browser. It can fill the NTN and parse/save the result, but the user must complete FBR's CAPTCHA in the normal browser workflow. The job checkpoints after every NTN and can resume after interruption.

## Authorized bulk/API route

If FBR/PRAL supplies an authorized API or structured extract later, implement the same normalized record contract used by `collect_profiles.py` and the downstream workbook assembly will remain unchanged.
