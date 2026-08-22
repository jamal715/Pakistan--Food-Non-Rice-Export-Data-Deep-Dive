# Pakistan Food / Non-Rice Export Data Deep Dive

A reusable decision-support pipeline for analysing Pakistan exporter-directory extracts, beginning with **HS Chapter 12** as the pilot.

## What this repository does

Upload a TDAP exporter-directory Excel workbook and the Streamlit app will:

- normalize common TDAP field names;
- run a due-diligence audit before analysis;
- calculate exporter concentration, cumulative shares and HHI;
- identify the number of exporters accounting for 60% of reported value;
- map the HS8 product landscape and capability crowding;
- produce a transparent strategic screen combining reported scale and HS8 scarcity;
- expose caveats so unsupported claims are not silently introduced;
- let the user download the strategic-screen output.

The analytical engine is chapter-independent. Chapter 12 is the validation case before scaling to HS01–24.

## Critical interpretation rules

1. `exported_value_rs` is treated as **TDAP reported export value**. Its period/year must remain unresolved unless the source explicitly establishes it.
2. `reported_record_count` / `Count(*)` is **not physical quantity**. `exported_value_rs / reported_record_count` must not be labelled unit value or export price.
3. Shares are shares of the supplied TDAP extract unless reconciled to a national denominator such as PBS.
4. Destination diversification/new-market entry cannot be measured without destination data.
5. Growth cannot be measured without a defensible time dimension.
6. True unit value requires compatible trade value and physical quantity at the same HS8/time/destination aggregation.
7. If the source contains only one retained HS8 row per firm/NTN, firm product diversification is not measurable from that extract.
8. TDAP firm attribution and PBS national HS8 × country totals are analytically complementary but must not be joined as though PBS identifies the exporter.

## Run locally

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Then upload `chapter 12 DD.xlsx` in the browser.

## Test

```bash
pytest -q
```

GitHub Actions runs the same tests on every push and pull request.

## Architecture

```text
app.py                  Streamlit decision dashboard
src/analysis.py         reusable normalization, audit and analytics engine
tests/test_analysis.py  regression tests
.github/workflows/      CI
```

## Chapter 12 pilot sequence

**Gate 1 — Due diligence:** schema, duplicates, HS-code validity, missing/non-positive values, entity counts, chapter scope, source caveats.

**Gate 2 — Descriptive structure:** total reported value, exporter count, HS8 count, concentration, cumulative shares, HHI, HS8 crowding.

**Gate 3 — Strategic screening:** identify firms combining demonstrated export scale with relatively scarce HS8 capabilities. This is a screening device, not a final policy ranking.

**Gate 4 — Enrichment:** add PBS HS8 × country/time data for market direction and national product context; add shipment-level quantity/value if legally/publicly obtainable for true unit-value analysis.

**Gate 5 — Policy intelligence:** only after enrichment should the system score destination diversification, new-market entry, growth, unit-value positioning, geopolitical opportunity/exposure, and national export contribution.

## Data policy

Raw private/sensitive working files should not be committed. `data/private/` and `outputs/` are git-ignored. The dashboard is designed to accept the workbook at runtime.
