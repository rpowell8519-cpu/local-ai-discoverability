"""Call render_report(report) from any Streamlit page; owns no global page configuration."""
import pandas as pd
import streamlit as st
from .schema import Report
from .metrics import METHODOLOGY, kpis, tables
from .export import html_report, csv_bundle


def render_report(report: Report | dict, key='gso'):
    report = Report.model_validate(report)
    client = next(b for b in report.brands if b.id == report.client_id)
    st.markdown('''<style>
        [data-testid="stMetric"]{background:rgba(23,107,112,.12);border:1px solid rgba(23,107,112,.35);border-radius:10px;padding:16px}
        @media print{[data-testid="stSidebar"], [data-testid="stHeader"],
        [data-testid="stDownloadButton"]{display:none} h2,h3{break-after:avoid}}
        </style>''', unsafe_allow_html=True)
    st.title('AI Visibility Report')
    st.caption(f'{client.name} · {report.category} · {report.market} · {report.start_date} to {report.end_date} · {report.agency}')
    if report.sample_data:
        st.warning('SAMPLE DATA — fictional businesses and synthetic answers. Not client measurements.')
    left, right = st.columns(2)
    providers = left.multiselect('Providers', ['OpenAI', 'Claude', 'Gemini'], default=['OpenAI', 'Claude', 'Gemini'], key=f'{key}_providers')
    intents = right.multiselect('Search intent', ['discovery', 'comparison', 'transactional', 'branded'],
                               default=['discovery', 'comparison', 'transactional', 'branded'], key=f'{key}_intents')
    surfaces = st.multiselect('Collection surface', ['api', 'consumer', 'manual'],
                             default=['api', 'consumer', 'manual'], key=f'{key}_surfaces')
    prompt_ids = {p.id for p in report.prompts if p.intent in intents}
    observations = [o for o in report.observations if o.provider in providers and o.prompt_id in prompt_ids and o.surface in surfaces]
    scope = f'Providers: {", ".join(providers) or "none"}; intents: {", ".join(intents) or "none"}; surfaces: {", ".join(surfaces) or "none"}'
    if len({o.surface for o in observations}) > 1:
        st.warning('This selection combines collection surfaces. Select one surface for a more comparable view.')
    stats, sections = kpis(report, observations), tables(report, observations)
    st.header('Executive summary')
    st.write(report.executive_summary or 'Add an analyst summary after reviewing the evidence.')
    st.caption('The editorial summary and roadmap cover the whole reporting period. Metrics follow the active filters.')
    for row in [('Visibility index /100', 'Mention rate %', 'Recommendation rate %', 'Tracked share of voice %'),
                ('Owned-site citation rate %', 'Citation evidence coverage %', 'Recommendation persistence %', 'Brand accuracy %'),
                ('Positive/neutral sentiment %', 'Sentiment coverage %', 'Position coverage %', 'First recommendation rate %')]:
        for col, metric in zip(st.columns(4), row):
            value = stats[metric]
            col.metric(metric, 'N/A' if value is None else f'{value:.1f}')
    st.caption(f'{stats["Successful answers"]} successful answers · {stats["Failed/refused runs"]} failed/refused · {stats["Repeat groups"]} eligible repeat groups · {stats["Verified fact checks"]} verified fact checks')
    if stats['Failed/refused runs']:
        st.warning('Some runs failed or were refused. They are excluded from rates; review the evidence before interpreting performance.')
    if not stats['Successful answers']:
        st.info('No successful answers in this selection. Add observations or change the filters.')
    elif stats['Citation evidence coverage %'] != 100:
        st.warning('Citation source metadata was not captured for every successful answer. The coverage metric shows the measured share; missing citation metadata is not treated as zero citations.')
    st.dataframe(pd.DataFrame([{'Metric': k, 'Value': 'N/A' if v is None else str(v)} for k, v in stats.items()]), hide_index=True, width='stretch')

    def table(name):
        rows = sections[name]
        if rows:
            st.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch')
        else:
            st.info('No measured data in this selection.')

    st.header('Platform performance')
    st.caption('OpenAI observations carry their collection surface in the evidence. API results do not establish consumer ChatGPT visibility.')
    df = pd.DataFrame(sections['Provider performance']).set_index('Provider')
    chart_columns = ['Mention rate %', 'Recommendation rate %', 'Owned-site citation rate %']
    if any(df[column].notna().any() for column in chart_columns):
        st.bar_chart(df[chart_columns], stack=False)
    else:
        st.info('No comparable provider metrics are available in this selection.')
    table('Provider performance')
    st.subheader('Daily trend')
    if sections['Daily trend']:
        st.line_chart(pd.DataFrame(sections['Daily trend']).set_index('Date')[['Mention rate %', 'Recommendation rate %']])
    st.caption('Descriptive trend: changing prompt mixes or collection settings can affect the result.')
    st.header('Competitor benchmarking')
    competitor_chart = pd.DataFrame(sections['Competitor benchmarks']).set_index('Brand')[['Mention rate %', 'Recommendation rate %']]
    if competitor_chart.notna().any().any():
        st.bar_chart(competitor_chart, stack=False)
    else:
        st.info('No competitor benchmark metrics are available in this selection.')
    table('Competitor benchmarks')
    st.caption('Share of voice is relative to the tracked competitor set. It is not total market share.')
    st.header('Citations and sources')
    table('Sources')
    st.caption('Domains are counted once per answer. Full citation URLs are preserved in the answer evidence.')
    st.header('Recommendation consistency')
    table('Recommendation consistency')
    st.caption('Persistence is the mean recommendation rate across matched groups with at least two successful repeats.')
    st.header('Brand accuracy and sentiment')
    table('Brand accuracy evidence')
    st.bar_chart(pd.DataFrame(sections['Sentiment']).set_index('Sentiment'))
    st.header('Local visibility')
    table('Local visibility')
    st.header('Prioritised opportunities')
    table('Opportunities')
    st.caption('Priority = recommendation gap × importance/5 × evidence factor ÷ effort. Scores are shown only when importance and effort have been supplied; suggestions need analyst review.')
    st.header('30 / 60 / 90-day roadmap')
    for horizon in (30, 60, 90):
        st.subheader(f'By day {horizon}')
        items = [r for r in sections['Roadmap'] if r['horizon'] == horizon]
        if items:
            st.dataframe(pd.DataFrame(items).drop(columns='horizon'), hide_index=True, width='stretch')
        else:
            st.write('No actions assigned.')
    st.header('Methodology and evidence')
    st.write(METHODOLOGY)
    st.write(report.methodology_notes)
    with st.expander('Prompt panel'):
        st.dataframe(pd.DataFrame([p.model_dump() for p in report.prompts]), hide_index=True, width='stretch')
    with st.expander('Answer evidence and failures'):
        table('Answer evidence')
    st.header('Export report')
    st.caption('HTML and CSV use the active filters. JSON contains the complete report. Open downloaded HTML in a browser and print to PDF for a clean client copy.')
    cols = st.columns(3)
    cols[0].download_button('Print-ready HTML', html_report(report, observations, scope), 'ai-visibility-report.html', 'text/html', key=f'{key}_html')
    cols[1].download_button('CSV tables (ZIP)', csv_bundle(report, observations, scope), 'ai-visibility-tables.zip', 'application/zip', key=f'{key}_csv')
    cols[2].download_button('Full report JSON', report.model_dump_json(indent=2), 'ai-visibility-data.json', 'application/json', key=f'{key}_json')
