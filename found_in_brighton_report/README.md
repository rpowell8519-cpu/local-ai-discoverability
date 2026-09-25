# Found in Brighton AI report generator

Creates the redesigned AI Visibility Report as an editable Word document, with an optional PDF. The default template is 16 A4 pages and includes the scorecard, platform comparison, competitor share of voice, trend chart, local signals, 90 day roadmap and evidence appendices.

## Give this folder to Codex

Open this folder as a project in Codex, or attach the files to a task. Paste the following request:

> Use the supplied Python report generator to create the Found in Brighton AI client report. Read README.md, install the listed dependencies in an appropriate Python environment, and run generate_report.py. Use client.example.json for the client fields, or ask me for the actual client details if needed. Produce the editable Word report and a PDF if LibreOffice is available. Render and visually inspect every page. Preserve the illustrative labels unless I provide actual measured data. Do not fabricate audit results. Use the bundled document runtime if your Codex environment provides one.

## Run locally

Requires Python 3.10 or newer. From this folder:

```sh
python -m venv .venv
```

Activate the environment on macOS or Linux:

```sh
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Install and generate:

```sh
python -m pip install -r requirements.txt
python generate_report.py --config client.example.json --output-dir generated-report
```

To also export PDF, install LibreOffice and run:

```sh
python generate_report.py --config client.example.json --output-dir generated-report --pdf
```

Use `--libreoffice "/path/to/soffice"` if it is not found automatically. Font discovery supports common macOS, Windows and Linux fonts. For another setup, supply `--font` and `--bold-font` with TrueType font paths. Page breaks can vary with installed fonts; inspect the exported PDF after edits.

## Files and editing

- `generate_report.py`: visual design, colours, charts, portable paths, configuration and PDF export.
- `report_content.py`: base report copy, tables and metric definitions. This is loaded by the generator; do not run it directly.
- `client.example.json`: replace the example business details with client details. Values are treated as text.
- `requirements.txt`: Python dependencies. LibreOffice is optional and installed separately.

Output includes a `.docx`, optional `.pdf`, and generated chart images in an `assets` folder. The document text and tables are editable in Word. Charts are embedded images: edit the sample data in `generate_report.py` and regenerate them. They are not native editable Word charts, and changing a table in Word will not update a chart automatically.

## Data integrity

The standalone CLI produces an illustrative template, not a live audit. All sample numbers and findings are illustrative. The JSON configuration replaces text placeholders only; it does not recalculate metrics or replace chart data. No API keys or network access are required for generation, and no platform monitoring is performed.

For measured reports, update the text, tables and chart values together from the same verified dataset. Retain the declared denominators, prompt panel, model settings and evidence references. Long client names or extra content may change pagination. The generator overwrites its named output files within the chosen output directory; use a different directory for each client or report period.

## Streamlit integration

The Streamlit AI Report Generator calls `src.found_brighton_report.generate_filled_report()` with the validated report built from the selected saved AI Visibility scan. It replaces the example scorecard, provider results, response classifications, tracked-business comparison, citation results, prompt appendix and performance charts with calculations from that scan. It makes no provider calls. A single scan has no historical trend, so its trend-page space shows visibility by prompt intent instead.

Other pages cover source authority, brand accuracy, local profiles, reviews, website readiness and action planning. Those items are not measured by the visibility scan and are identified as analyst worksheets in the generated report. The app currently offers the editable Word file; PDF export remains available only through the standalone CLI when LibreOffice is installed.
