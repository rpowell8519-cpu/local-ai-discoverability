"""Deterministic synthetic evidence; never represent this as client measurement."""
from datetime import date, datetime, timezone
from .schema import Report, Brand, Prompt, Observation, Mention, Citation, FactCheck, RoadmapItem


def sample_report():
    brands = [Brand(id='client', name='Harbour Dental (fictional)', domains=['harbour.example']),
              Brand(id='rival-a', name='City Dental (fictional)', domains=['city.example']),
              Brand(id='rival-b', name='Coast Dental (fictional)', domains=['coast.example'])]
    prompts = [Prompt(id='p1', text='Which dentists in Brighton offer family appointments?', topic='Family dentistry', location='Brighton', importance=5, effort=2),
               Prompt(id='p2', text='Compare emergency dentists in Hove', topic='Emergency care', intent='comparison', location='Hove', importance=5, effort=3),
               Prompt(id='p3', text='What should I look for when choosing a dentist?', topic='Choosing a provider', importance=3, effort=2),
               Prompt(id='p4', text='Does Harbour Dental offer weekend appointments?', topic='Brand facts', intent='branded', location='Brighton', importance=4, effort=1)]
    observations = []
    for pi, provider in enumerate(('OpenAI', 'Claude', 'Gemini')):
        for qi, prompt in enumerate(prompts):
            for repeat in range(3):
                n = pi * 12 + qi * 3 + repeat
                failed = n == 19
                mentioned = (n + pi) % 4 != 0
                recommended = mentioned and (n + qi) % 3 != 0
                ids = (['client'] if mentioned else []) + ['rival-a'] + (['rival-b'] if n % 2 == 0 else [])
                if n % 2:
                    ids = list(reversed(ids))
                rec_rank = 0
                mentions = []
                for rank, bid in enumerate(ids, 1):
                    rec = recommended if bid == 'client' else True
                    if rec:
                        rec_rank += 1
                    mentions.append(Mention(brand_id=bid, recommended=rec, position=rank,
                                            recommendation_position=rec_rank if rec else None,
                                            sentiment=('positive', 'neutral', 'mixed', 'unknown', 'negative')[n % 5]))
                citations = [Citation(url='https://directory.example/dentists', title='Example directory', source_type='directory')]
                if mentioned and n % 3:
                    citations.append(Citation(url='https://harbour.example/services', source_type='owned'))
                verdict = ('correct', 'incorrect', 'unverifiable')[n % 3]
                checks = [FactCheck(brand_id='client', field='Weekend hours', expected='Saturday 09:00–13:00',
                                    observed={'correct':'Saturday 09:00–13:00', 'incorrect':'Closed Saturday', 'unverifiable':'Hours vary'}[verdict],
                                    verdict=verdict, evidence='Synthetic source of truth: fictional practice profile.')] if mentioned else []
                answer = 'SYNTHETIC EXAMPLE. ' + '; '.join(
                    f'{m.position}. {next(b.name for b in brands if b.id == m.brand_id)} '
                    f'({"recommended" if m.recommended else "mentioned"}; sentiment: {m.sentiment})' for m in mentions)
                if checks:
                    answer += '. Harbour weekend hours: ' + checks[0].observed
                observations.append(Observation(id=f'run-{n}', prompt_id=prompt.id, provider=provider,
                    model='demo-model', surface='manual', configuration='synthetic-v1; en-GB; no live search',
                    collected_at=datetime(2026, 9, 20 + repeat, 10, pi, tzinfo=timezone.utc),
                    status='error' if failed else 'ok', error='Synthetic timeout' if failed else None,
                    answer='' if failed else answer, mentions=[] if failed else mentions,
                    citations=[] if failed else citations, fact_checks=[] if failed else checks))
    return Report(client_id='client', agency='Your agency', category='Dentistry', market='Brighton & Hove',
        start_date=date(2026,9,1), end_date=date(2026,9,30), sample_data=True, brands=brands,
        prompts=prompts, observations=observations,
        executive_summary='Illustrative report only. Review service-level recommendation gaps, cited sources and inconsistent opening-hours answers before agreeing priorities.',
        methodology_notes='All businesses, prompts and answer annotations in this example are synthetic. Three planned repeats per prompt/provider; one simulated failure.',
        roadmap=[RoadmapItem(horizon=30, action='Verify opening hours and reconcile business profiles', owner='Client operations', success_measure='All owned profiles match the approved hours', evidence='Illustrative accuracy checks'),
                 RoadmapItem(horizon=60, action='Improve priority service pages with verifiable details', owner='Content team', success_measure='Priority pages reviewed, published and crawlable', evidence='Review opportunity table and cited sources'),
                 RoadmapItem(horizon=90, action='Repeat the matched prompt panel and review persistence', owner='GSO analyst', success_measure='Complete three independent repeats per prompt/provider; compare matched configurations', evidence='Recommendation consistency baseline')])
