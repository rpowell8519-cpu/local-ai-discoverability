# Report downloads release — 25 September 2026

Step 6 of AI Report Generator offers four report formats:

- Full evidence report (RP): existing PDF and evidence exports.
- Client summary (LS): PDF, including provider comparisons and saved-review analysis.
- AI Visibility Report (GSO): interactive saved-scan report with print-ready HTML,
  CSV tables (ZIP), and full report JSON. Open the HTML and print to PDF if needed.
- Found in Brighton AI Report: Word document populated from the selected saved scan.
  Sections beyond the measured visibility evidence remain explicitly labelled worksheets.

Select a format and generate it before its download controls appear. Generation uses
the attached completed scan and does not rerun paid AI tests.

## Deployment

Streamlit installs the root requirements.txt. The GSO package and Found in Brighton
template sources must be deployed with the application. Word generation uses Python
and Pillow; it does not require Microsoft Word or LibreOffice on the server.

The existing database schema is supported. The optional SQL in
`sql/20260925_gso_visibility_report_metadata.sql` enables persistent citation metadata
and prompt ratings for future scans; it must not be applied without explicit schema
approval. Historical citation coverage is reported as unavailable, not zero.

The standalone AI Visibility Report page labels its historical aggregate import and
fictional sample explicitly. Use AI Report Generator for the selected live saved scan.

GSO and Found in Brighton consume the scan's persisted identity analysis. RP and LS
also use the report review's later name decisions; their counts can therefore differ
when names were reconciled after the scan.

## Validation

Before release: 625 tests passed, 13 skipped and 73 subtests passed; Python compilation,
dependency consistency and whitespace checks passed. Tests include saved-scan mapping,
report choice controls, Word generation and removal of illustrative metric values.
