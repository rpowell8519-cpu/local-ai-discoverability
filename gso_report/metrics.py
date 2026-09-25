"""Pure calculations shared by the interactive page and static export."""
from collections import defaultdict
from statistics import mean
from urllib.parse import urlsplit
from .schema import Report


def rate(n, d):
    return round(100 * n / d, 2) if d else None


def host(url):
    return (urlsplit(url).hostname or '').lower().removeprefix('www.')


def owned(url, brand):
    domain = host(url)
    return any(domain == d or domain.endswith('.' + d) for d in brand.domains)


def group_key(obs):
    return (obs.prompt_id, obs.provider, obs.model, obs.surface, obs.configuration)


def consistency(observations, brand_id):
    groups = defaultdict(list)
    for obs in observations:
        if obs.status == 'ok':
            groups[group_key(obs)].append(any(m.brand_id == brand_id and m.recommended for m in obs.mentions))
    return [{'Prompt': k[0], 'Provider': k[1], 'Model': k[2], 'Surface': k[3],
             'Configuration': k[4], 'Successful repeats': len(v),
             'Recommendations': sum(v), 'Persistence %': rate(sum(v), len(v))}
            for k, v in groups.items() if len(v) >= 2]


def kpis(report, observations, brand_id=None):
    bid = brand_id or report.client_id
    brand = next(b for b in report.brands if b.id == bid)
    ok = [o for o in observations if o.status == 'ok']
    mentions = [m for o in ok for m in o.mentions if m.brand_id == bid]
    total_mentions = sum(len(o.mentions) for o in ok)
    checks = [f for o in ok for f in o.fact_checks if f.brand_id == bid]
    verified = [f for f in checks if f.verdict != 'unverifiable']
    known_sentiment = [m for m in mentions if m.sentiment != 'unknown']
    positions = [m.position for m in mentions if m.position is not None]
    repeated = consistency(ok, bid)
    mention_rate = rate(len(mentions), len(ok))
    rec_rate = rate(sum(m.recommended for m in mentions), len(ok))
    citation_observations = [o for o in ok if o.citation_status == 'measured']
    cite_rate = (
        rate(sum(any(owned(c.url, brand) for c in o.citations) for o in citation_observations),
             len(citation_observations))
        if brand.domains and citation_observations else None
    )
    citation_coverage = rate(len(citation_observations), len(ok))
    return {
        'Successful answers': len(ok), 'Failed/refused runs': len(observations) - len(ok),
        'Mention rate %': mention_rate, 'Recommendation rate %': rec_rate,
        'Tracked share of voice %': rate(len(mentions), total_mentions),
        'Average mention position': round(mean(positions), 2) if positions else None,
        'First recommendation rate %': rate(sum(m.recommendation_position == 1 for m in mentions), len(ok)),
        'Owned-site citation rate %': cite_rate,
        'Citation evidence coverage %': citation_coverage,
        'Recommendation persistence %': round(mean(r['Persistence %'] for r in repeated), 2) if repeated else None,
        'Repeat groups': len(repeated),
        'Brand accuracy %': rate(sum(f.verdict == 'correct' for f in verified), len(verified)),
        'Verified fact checks': len(verified), 'Unverifiable facts': len(checks) - len(verified),
        'Positive/neutral sentiment %': rate(sum(m.sentiment in ('positive', 'neutral') for m in known_sentiment), len(known_sentiment)),
        'Sentiment coverage %': rate(len(known_sentiment), len(mentions)),
        'Position coverage %': rate(len(positions), len(mentions)),
        'Visibility index /100': (
            round(.5 * mention_rate + .3 * rec_rate + .2 * cite_rate, 2)
            if ok and cite_rate is not None else None
        ),
    }


def tables(report: Report, observations):
    ok = [o for o in observations if o.status == 'ok']
    client = next(b for b in report.brands if b.id == report.client_id)
    benchmarks = [{'Brand': b.name, **kpis(report, observations, b.id)} for b in report.brands]
    providers = [{'Provider': provider, **kpis(report, [o for o in observations if o.provider == provider])}
                 for provider in ('OpenAI', 'Claude', 'Gemini')]
    citation_observations = [o for o in ok if o.citation_status == 'measured']
    sources = defaultdict(lambda: {'count': 0, 'types': set(), 'owned': False})
    for obs in citation_observations:
        for domain in {host(c.url) for c in obs.citations}:
            sources[domain]['count'] += 1
        for c in obs.citations:
            row = sources[host(c.url)]
            row['types'].add(c.source_type)
            row['owned'] = row['owned'] or owned(c.url, client)
    source_rows = [{'Domain': d, 'Answers citing domain': v['count'], 'Answer citation rate %': rate(v['count'], len(citation_observations)),
                    'Types': ', '.join(sorted(v['types'])), 'Client owned': v['owned']}
                   for d, v in sorted(sources.items(), key=lambda item: -item[1]['count'])]
    local = []
    for location in sorted({p.location for p in report.prompts if p.location}):
        ids = {p.id for p in report.prompts if p.location == location}
        local.append({'Location': location, **kpis(report, [o for o in observations if o.prompt_id in ids])})
    opportunities = []
    for p in report.prompts:
        runs = [o for o in ok if o.prompt_id == p.id]
        if not runs:
            continue
        score = kpis(report, runs)
        if p.importance is None or p.effort is None:
            opportunities.append({'Prompt': p.text, 'Topic': p.topic, 'Location': p.location or 'Non-local',
                                  'Successful answers': len(runs), 'Recommendation gap %': None,
                                  'Importance (1–5)': p.importance, 'Effort (1–5)': p.effort,
                                  'Evidence factor': None, 'Priority /100': None,
                                  'Suggested action': 'Review the evidence and set importance and effort before scoring.'})
            continue
        gap = 100 - score['Recommendation rate %']
        confidence = min(len(runs) / 5, 1)
        priority = round(gap * (p.importance / 5) * confidence / p.effort, 1)
        opportunities.append({'Prompt': p.text, 'Topic': p.topic, 'Location': p.location or 'Non-local',
                              'Successful answers': len(runs), 'Recommendation gap %': gap,
                              'Importance (1–5)': p.importance, 'Effort (1–5)': p.effort,
                              'Evidence factor': confidence, 'Priority /100': priority,
                              'Suggested action': 'Review winning sources and answer gaps; improve relevant service evidence.'})
    sentiment = [{'Sentiment': s, 'Mentions': sum(m.brand_id == report.client_id and m.sentiment == s for o in ok for m in o.mentions)}
                 for s in ('positive', 'neutral', 'negative', 'mixed', 'unknown')]
    accuracy = [{'Observation': o.id, 'Field': f.field, 'Expected': f.expected, 'Observed': f.observed,
                 'Verdict': f.verdict, 'Evidence': f.evidence}
                for o in ok for f in o.fact_checks if f.brand_id == report.client_id]
    trends = [{'Date': day.isoformat(), **kpis(report, [o for o in observations if o.collected_at.date() == day])}
              for day in sorted({o.collected_at.date() for o in observations})]
    evidence = [{'Observation': o.id, 'Prompt ID': o.prompt_id, 'Provider': o.provider, 'Model': o.model,
                 'Surface': o.surface, 'Configuration': o.configuration, 'Collected': o.collected_at.isoformat(),
                 'Status': o.status, 'Citation capture': o.citation_status, 'Error': o.error or '', 'Answer': o.answer,
                 'Citations': '\n'.join(c.url for c in o.citations)} for o in observations]
    return {'Provider performance': providers, 'Competitor benchmarks': benchmarks,
            'Sources': source_rows, 'Recommendation consistency': consistency(observations, report.client_id),
            'Brand accuracy evidence': accuracy, 'Sentiment': sentiment, 'Local visibility': local,
            'Opportunities': sorted(
                opportunities,
                key=lambda r: r['Priority /100'] if r['Priority /100'] is not None else -1,
                reverse=True,
            ),
            'Daily trend': trends, 'Roadmap': [r.model_dump() for r in report.roadmap], 'Answer evidence': evidence}

METHODOLOGY = '''Each successful answer is one observation with equal weight. Errors and refusals are excluded from rates and shown separately. Missing measurements are N/A, never zero. The prompt roster is the sampling frame; results describe that sample, not all real-world searches. Branded and discovery prompts should usually be analysed separately.

Mention rate = answers mentioning the brand / successful answers. Recommendation rate = answers explicitly recommending the brand / successful answers. First recommendation rate = answers with recorded recommendation rank 1 / successful answers; a single unranked recommendation is not automatically first. Average mention position includes recorded ranks only; lower is better. Position coverage shows the fraction of mentions with a recorded rank.

Tracked share of voice = brand-answer mentions / all tracked brand-answer mentions. Each tracked brand counts once per answer. This is relative to the supplied competitor set, not the entire market. Owned-site citation rate = successful answers citing a configured client domain or its subdomains / successful answers with citation capture measured. Citation evidence coverage = successful answers with citation capture measured / all successful answers. If citations or the client's domain were not captured, citation rate is N/A rather than zero. A domain's citation rate counts each answer once, even if it cites several URLs from that domain. URLs labelled owned are still checked against configured domains.

Recommendation persistence = the equal-weight mean recommendation rate of groups with at least two successful repeats. Groups must have the same prompt ID, provider, model, surface and configuration. A never-recommended repeated group scores zero; a single run is not evidence of consistency. Failed repeats are excluded and may bias results; inspect failed-run counts. Persistence is descriptive, not a confidence interval or an estimate of consumer exposure.

Brand accuracy = correct fact checks / (correct + incorrect checks); unverifiable facts are excluded and counted separately. Checks require recorded truth and rationale, and are human-review annotations, not automated truth detection. Positive/neutral sentiment uses classified brand mentions only; unknown is excluded and coverage disclosed. Mixed is classified but is not positive/neutral.

Visibility index = 50% mention rate + 30% recommendation rate + 20% owned-site citation rate, on a 0–100 scale. It is N/A when citation coverage or a client domain is unavailable. These are transparent agency defaults, not an industry standard or forecast. Opportunity priority = recommendation gap (0–100) × importance/5 × min(successful answers/5, 1) ÷ effort. Importance and effort are editorial inputs; when they are not supplied, opportunity scores remain N/A. The evidence factor is a heuristic, not statistical confidence. Actions require analyst review.

Local visibility groups prompts by their explicitly recorded location. It does not infer the searcher's physical location. Daily trends may reflect different prompt mixes, models or configurations and are descriptive. There is no automatic previous-period comparison without a matched sampling frame. Exports reflect the active provider, intent and surface filters; the roadmap and editorial summary remain report-wide.

API, consumer and manual observations are labelled separately in the evidence. An API model response is not evidence of visibility in a consumer product. Record exact model/version, web-search availability, geography, locale, date, prompt wording, session state, sampling settings and collection method in configuration and methodology notes. Use fresh independent sessions for repeated runs. Model outputs vary; citations are evidence of what was returned, not endorsements of source quality. No lead, traffic or revenue attribution is inferred.
'''
