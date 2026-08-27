# Exporter / Product Deep Dive methodology

The deep-dive layer is deliberately separate from the existing selected-chapter analytics. The current chapter is still normalized, audited, ranked, concentrated, strategically screened and reconciled exactly as before. Only after those calculations are complete does the app build a read-only cross-chapter universe from every valid HS-labelled sheet in the available workbook. A sheet is rejected from this cross-chapter universe if its observed HS2 codes conflict with the chapter encoded in its sheet name.

## Exporter view

NTN is the authoritative exporter identity. Company name is used for search and for displaying observed aliases, but rows carrying different NTNs are never silently combined. For a selected NTN, every source row carrying that NTN across all loaded HS chapters is aggregated by HS8. The denominator is the exporter's total TDAP-reported value across all loaded chapter sheets:

`HS8 share of exporter = exporter value in HS8 / exporter total reported value across all loaded chapters`

The resulting HS8 shares must sum to 100% and the sum of HS8 values must equal the selected exporter's directly observed source total. Both identities are shown as calculation controls in the app.

## HS8 view

An HS8 search requires an exact eight-digit code. All source rows carrying that HS8 are aggregated into exporter identities. NTN remains authoritative when available. A source row without NTN is retained in the HS8 denominator and is grouped only by its observed exporter name; it is explicitly labelled as `NTN unavailable` and receives no sidecar phone assignment. The denominator is the complete observed value of the selected HS8 across the loaded chapter universe:

`Exporter share of HS8 = exporter reported value in HS8 / total reported value of HS8`

Exporter shares must sum to 100% and their reported values must sum to the direct HS8 source total.

## Contact information

Phone numbers remain display-only metadata. The cross-chapter contact directory applies the same conservative principle as the Strategic Shortlist contact layer: a sidecar phone is accepted only when chapter + normalized exporter name resolves to exactly one nonblank NTN in the analytical universe and exactly one nonblank phone in the contact sidecar. If multiple safe phone numbers are observed for the same NTN across chapters, the app displays all unique verified numbers rather than choosing one arbitrarily. Ambiguous identities and conflicting phone assignments are withheld.

## Scope

All values and shares describe the loaded TDAP workbook. They do not become national market shares merely because the deep-dive spans all 24 chapter sheets. Record count remains a source-frequency field and is never used as physical quantity or unit price in these calculations.
