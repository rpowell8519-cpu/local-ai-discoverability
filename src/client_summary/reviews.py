"""Describe saved review samples alongside visibility, without inferring causality."""
from src.review_analysis import _normalise_text, _term_pattern
from src.review_profiles import get_review_profile


CLEANING_THEMES = [
    ('Commercial / office', ['commercial', 'office', 'offices']),
    ('End of tenancy', ['end of tenancy', 'end-of-tenancy', 'tenancy', 'moving out']),
    ('Carpet cleaning', ['carpet', 'carpets']),
    ('Upholstery cleaning', ['upholstery', 'sofa', 'sofas']),
    ('Laundry services', ['laundry', 'laundering', 'linen', 'ironing']),
    ('Airbnb / changeovers', ['airbnb', 'changeover', 'holiday let', 'short let']),
]


def build_review_summary(report, group):
    """Use only frozen text records; review counts never contribute to AI counts."""
    target = str(report['audit']['target_google_place_id'])
    themes = (CLEANING_THEMES if group == 'cleaning_services' else
              [(t['label'], t['terms']) for t in get_review_profile(group or 'generic')['themes'][:6]])
    businesses = []
    for sample in report['review_sets']:
        pid = str(sample['google_place_id'])
        records = {str(r['review_id']): r for r in sample.get('records', [])
                   if str(r.get('review_text') or '').strip()}
        rows = list(records.values())
        dates = sorted(str(r['review_datetime_utc'])[:10] for r in rows if r.get('review_datetime_utc'))
        ratings = [float(r['review_rating']) for r in rows if r.get('review_rating') is not None
                   and 1 <= float(r['review_rating']) <= 5]
        counts = {}
        for label, terms in themes:
            patterns = [_term_pattern(t) for t in terms]
            counts[label] = sum(any(p.search(_normalise_text(r['review_text'])) for p in patterns) for r in rows)
        businesses.append({'id': pid, 'name': sample['business_name'], 'sample_size': len(rows),
                           'rating': round(sum(ratings) / len(ratings), 2) if ratings else None,
                           'rated_count': len(ratings), 'low_ratings': sum(r <= 2 for r in ratings),
                           'date_range': ' to '.join([dates[0], dates[-1]]) if dates else 'Dates unavailable',
                           'themes': counts})
    if not businesses:
        return None
    businesses.sort(key=lambda b: (b['id'] != target, b['name'].casefold()))
    target_sample = next((b for b in businesses if b['id'] == target), None)
    links = []
    for label, terms in themes:
        query_terms = ['commercial cleaning', 'office cleaning'] if label == 'Commercial / office' else terms
        patterns = [_term_pattern(t) for t in query_terms]
        questions = [q for q in report['questions'] if any(p.search(_normalise_text(q['prompt'])) for p in patterns)]
        links.append({'label': label, 'reviews': target_sample['themes'][label] if target_sample else 0,
                      'answers': sum(q['answers'] for q in questions),
                      'appearances': sum(q['appearances'] for q in questions),
                      'question_orders': [q['order'] for q in questions]})
    return {'businesses': businesses, 'themes': links, 'target_id': target,
            'source': 'Saved review text sets, identified by Google Place ID and review ID. '
                      'Each review counts once per theme; one review can mention several themes.'}
