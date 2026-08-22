# Executive readability V3

This change focuses on presentation only; the calculation engine remains unchanged.

- KPI cards now use self-explanatory labels and whole-number executive formatting.
- Metric labels/values are protected from ellipsis with responsive CSS.
- Top-exporter chart modebar is hidden so controls do not overlap bars or labels.
- Analytical charts retain a reduced Plotly control set; scroll zoom is disabled.
- HS8 chart axis labels are written in plain executive language.
- Pilot wording has been removed from the visible dashboard.
- Source caveats remain explicit.

Before extending ingestion to a 24-sheet workbook, cross-validate the loaded chapter against the source Excel totals, exporter counts, HS8 counts, concentration thresholds and top-exporter rankings.
