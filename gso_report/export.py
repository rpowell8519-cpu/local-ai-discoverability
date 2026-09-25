"""Offline HTML report (including printable charts) and spreadsheet-safe CSV bundle."""
import csv
import io
import zipfile
import json
from html import escape
from .metrics import METHODOLOGY, kpis, tables

STYLE = '''
body{font-family:Arial,sans-serif;color:#172b40;background:#f3f6fa;margin:0;padding:36px}
main{max-width:1120px;margin:auto;background:white;padding:40px;border-radius:12px}
h1{font-size:32px}h2{color:#176b70;border-bottom:1px solid #ccd9e2;padding-bottom:8px;margin-top:32px}
p{line-height:1.55;white-space:pre-wrap}.badge{background:#fff0c4;padding:12px;font-weight:bold}
table{border-collapse:collapse;width:100%;font-size:12px;margin:14px 0;overflow-wrap:anywhere}
th,td{text-align:left;border-bottom:1px solid #dde5ec;padding:8px;vertical-align:top}th{background:#eef5f6}
.cards{display:flex;flex-wrap:wrap;gap:12px}.card{background:#eef5f6;padding:16px;min-width:170px}
.card strong{display:block;font-size:25px}.bar{display:flex;align-items:center;gap:12px;margin:10px 0}
.bar span{width:150px}.bar i{display:block;height:14px;background:#176b70}.bar b{font-size:12px}
@page{size:A4 landscape;margin:14mm}
@media print{body{background:white;padding:0}main{padding:0;max-width:none}h2{break-after:avoid}
tr,.card,.bar{break-inside:avoid}thead{display:table-header-group}button{display:none}table{font-size:9px}}
'''


def display(value):
    return 'N/A' if value is None else str(value)


def html_table(rows):
    if not rows:
        return '<p>No measured data in this selection.</p>'
    keys = list(rows[0])
    return '<table><thead><tr>' + ''.join(f'<th>{escape(str(k))}</th>' for k in keys) + '</tr></thead><tbody>' + ''.join(
        '<tr>' + ''.join(f'<td>{escape(display(row.get(k)))}</td>' for k in keys) + '</tr>' for row in rows) + '</tbody></table>'


def csv_bytes(rows):
    out = io.StringIO(newline='')
    if rows:
        writer = csv.DictWriter(out, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            # Prevent formula interpretation of untrusted answer text in spreadsheet apps.
            writer.writerow({k: ("'" + v if isinstance(v, str) and v.lstrip().startswith(('=', '+', '-', '@')) else v)
                             for k, v in row.items()})
    return out.getvalue().encode('utf-8-sig')


def csv_bundle(report, observations, scope='All providers, intents and surfaces'):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, rows in tables(report, observations).items():
            z.writestr(name.lower().replace(' ', '_') + '.csv', csv_bytes(rows))
        z.writestr('summary.csv', csv_bytes([kpis(report, observations)]))
        z.writestr('methodology.txt', METHODOLOGY + '\n' + report.methodology_notes)
        z.writestr('metadata.json', json.dumps({
            'client_id': report.client_id, 'agency': report.agency,
            'start_date': str(report.start_date), 'end_date': str(report.end_date),
            'sample_data': report.sample_data, 'scope': scope,
            'included_observation_ids': [o.id for o in observations],
        }, indent=2))
    return output.getvalue()


def html_report(report, observations, scope='All providers and intents'):
    client = next(b for b in report.brands if b.id == report.client_id)
    stats = kpis(report, observations)
    sections = tables(report, observations)
    body = '<p class="badge">SAMPLE DATA — NOT CLIENT MEASUREMENTS</p>' if report.sample_data else ''
    body += '<h1>AI Visibility Report</h1>'
    body += '<p>' + escape(f'{client.name} • {report.market}\n{report.start_date} to {report.end_date} • Prepared by {report.agency}\nScope: {scope}') + '</p>'
    body += '<h2>Executive summary</h2><p>' + escape(report.executive_summary or 'Analyst summary pending.') + '</p>'
    body += '<div class="cards">' + ''.join(f'<div class="card">{escape(k)}<strong>{escape(display(stats[k]))}</strong></div>' for k in (
        'Visibility index /100', 'Mention rate %', 'Recommendation rate %', 'Recommendation persistence %')) + '</div>'
    body += html_table([{'Metric': k, 'Value': v} for k, v in stats.items()])
    body += '<h2>Provider recommendation rates</h2>'
    for row in sections['Provider performance']:
        value = row['Recommendation rate %']
        body += f'<div class="bar"><span>{escape(row["Provider"])}</span><i style="width:{(value or 0)*3}px"></i><b>{display(value)}%</b></div>'
    for name, rows in sections.items():
        body += '<h2>' + escape(name) + '</h2>'
        # Keep wide KPI tables readable on printed pages.
        if name in ('Provider performance', 'Competitor benchmarks', 'Local visibility', 'Daily trend'):
            key = list(rows[0])[0] if rows else None
            cols = [key, 'Successful answers', 'Mention rate %', 'Recommendation rate %', 'Tracked share of voice %', 'Owned-site citation rate %', 'Citation evidence coverage %', 'Recommendation persistence %']
            rows = [{k: row[k] for k in cols} for row in rows]
        body += html_table(rows)
    body += '<h2>Prompt panel</h2>' + html_table([p.model_dump() for p in report.prompts])
    body += '<h2>Methodology</h2><p>' + escape(METHODOLOGY) + '</p><p>' + escape(report.methodology_notes) + '</p>'
    return '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AI Visibility Report</title><style>' + STYLE + '</style><body><main>' + body + '</main></body></html>'
