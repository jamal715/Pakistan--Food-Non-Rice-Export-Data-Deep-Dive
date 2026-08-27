# Contact enrichment controls

Phone numbers are treated as a separate, display-only enrichment layer. They are not merged into the normalized TDAP analytical dataframe and therefore cannot enter reported export values, exporter aggregation, HS8 aggregation, shares, ranks, HHI, evidence-tier rules or reconciliation calculations.

The repository contact workbook must contain exactly three source fields: `HS_Chapter`, `exporter_name`, and `telephone`. Matching is deliberately conservative. For a sidecar phone to be displayed, the selected HS chapter and normalized exporter name must resolve to no more than one nonblank phone in the contact workbook, and the same chapter/exporter identity must resolve to exactly one nonblank NTN in the analytical source. The final display lookup is keyed by chapter + normalized exporter name + verified NTN. The phone is then repeated across that legal exporter's HS8 rows because the phone is company-level metadata, not HS8-level data.

If the same chapter/exporter name maps to more than one NTN, no sidecar phone is assigned. If conflicting nonblank phone numbers exist for the same chapter/exporter key, no sidecar phone is assigned. Missing NTNs are not guessed. Existing source-workbook telephone values, where present, take precedence. The enrichment function asserts that target row count is unchanged and that every pre-existing analytical column is unchanged after enrichment.

The Data Assurance tab reports contact rows in the selected chapter, safe phone keys, ambiguous identity keys and rows still without phone. These controls are intentionally separate from the analytical reconciliation status.
