"""Validated contract for the six-page client summary. No network or AI calls.

Vendored from the streamlit-client-report package supplied on 2026-09-21."""
from copy import deepcopy
from datetime import date
from collections import Counter

class ReportValidationError(ValueError):
    pass


def fail(message):
    raise ReportValidationError(message)


def text(value, field, maximum=500):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        fail(f'{field}: supply non-empty text of at most {maximum} characters.')
    if any(ord(c) < 32 and c not in '\n\t' for c in value):
        fail(f'{field}: unsupported control character.')
    # The bundled PDF font deliberately has a defined character repertoire.
    try:
        value.encode('cp1252')
    except UnicodeEncodeError:
        fail(f'{field}: use Western European text; add an embedded Unicode font for other scripts.')
    return value


def count(value, field, maximum=None):
    if type(value) is not int or value < 0 or (maximum is not None and value > maximum):
        fail(f'{field}: expected a non-negative whole number' + (f' no greater than {maximum}.' if maximum is not None else '.'))
    return value


def collection(value, field, low, high):
    if not isinstance(value, list) or not low <= len(value) <= high:
        fail(f'{field}: expected {low}-{high} items.')
    if not all(isinstance(v, dict) for v in value):
        fail(f'{field}: each item must be an object.')
    return value


def indexed(items, field):
    result = {}
    for item in items:
        key = text(item.get('id'), f'{field}.id', 80)
        if key in result:
            fail(f'{field}: duplicate ID {key}.')
        result[key] = item
    return result


def validate_report(payload):
    """Return an isolated validated copy; never mutate the caller's audit data.

    The aggregate contract checks arithmetic, not the truth of supplied evidence.
    Use from_records() for a stronger record-level counting path.
    """
    if not isinstance(payload, dict):
        fail('Report must be a JSON object.')
    d = deepcopy(payload)
    if type(d.get('schema_version')) is not int or d['schema_version'] != 1:
        fail('schema_version must be 1.')
    for field, limit in [('business_name', 90), ('location', 80), ('source_note', 400)]:
        text(d.get(field), field, limit)
    try:
        date.fromisoformat(d['audit_date'])
    except (ValueError, TypeError, KeyError):
        fail('audit_date must be YYYY-MM-DD.')
    if d.get('counting_rule') != 'unique_business_per_response':
        fail('counting_rule must be unique_business_per_response.')
    if type(d.get('web_search_enabled')) is not bool:
        fail('web_search_enabled must be true or false.')
    if type(d.get('owner_reviewed_questions')) is not bool:
        fail('owner_reviewed_questions must be true or false.')
    if d.get('evidence_basis') not in ('source_report_aggregates', 'saved_response_records'):
        fail('evidence_basis must identify source_report_aggregates or saved_response_records.')
    text(d.get('target_id'), 'target_id', 80)
    reps = count(d.get('repetitions'), 'repetitions', 20)
    if reps == 0:
        fail('repetitions must be positive.')
    providers = indexed(collection(d.get('providers'), 'providers', 1, 3), 'providers')
    questions = indexed(collection(d.get('questions'), 'questions', 1, 8), 'questions')
    expected_provider = len(questions) * reps
    expected_question = len(providers) * reps
    for p in providers.values():
        text(p.get('name'), 'provider.name', 40)
        text(p.get('model'), 'provider.model', 80)
        if count(p.get('complete'), 'provider.complete') != expected_provider:
            fail('This six-page baseline requires a complete, balanced test. Resolve failed/missing runs before exporting.')
        count(p.get('appearances'), 'provider.appearances', expected_provider)
    for q in questions.values():
        text(q.get('label'), 'question.label', 65)
        text(q.get('text'), 'question.text', 300)
        if count(q.get('complete'), 'question.complete') != expected_question:
            fail('Each question must have one complete response per provider and repetition.')
        count(q.get('appearances'), 'question.appearances', expected_question)
    total = sum(p['complete'] for p in providers.values())
    appearances = sum(q['appearances'] for q in questions.values())
    if sum(p['appearances'] for p in providers.values()) != appearances:
        fail('Question and provider appearance totals do not agree.')
    businesses = indexed(collection(d.get('businesses'), 'businesses', 1, 6), 'businesses')
    if d['target_id'] not in businesses:
        fail('businesses must include target_id.')
    if businesses[d['target_id']].get('name') != d['business_name']:
        fail('Target business name must match business_name.')
    for b in businesses.values():
        text(b.get('name'), 'business.name', 75)
        count(b.get('appearances'), 'business.appearances', total)
    if businesses[d['target_id']]['appearances'] != appearances:
        fail('Target business total does not match the question results.')
    evidence = indexed(collection(d.get('evidence', []), 'evidence', 0, 3), 'evidence')
    for e in evidence.values():
        text(e.get('observation'), 'evidence.observation', 220)
        text(e.get('source'), 'evidence.source', 200)
    actions = collection(d.get('actions'), 'actions', 3, 3)
    indexed(actions, 'actions')
    for a in actions:
        for key, limit in [('title', 75), ('task', 380), ('owner', 100), ('done_when', 200)]:
            text(a.get(key), f'action.{key}', limit)
        if not isinstance(a.get('question_id'), str) or a['question_id'] not in questions:
            fail('Each action must reference a measured question_id.')
        if a.get('status') not in ('suggested_check', 'verified_gap'):
            fail('action.status must be suggested_check or verified_gap.')
        refs = a.get('evidence_ids', [])
        if not isinstance(refs, list) or any(not isinstance(r, str) or r not in evidence for r in refs):
            fail('Action evidence_ids must reference supplied evidence.')
        if a['status'] == 'verified_gap' and not refs:
            fail('A verified gap requires an observation and source reference.')
    limitations = d.get('limitations', [])
    if not isinstance(limitations, list) or len(limitations) > 4:
        fail('limitations: expected up to four notes.')
    for limitation in limitations:
        text(limitation, 'limitation', 240)
    return d


def metrics(payload):
    d = validate_report(payload)
    total = sum(p['complete'] for p in d['providers'])
    appearances = sum(q['appearances'] for q in d['questions'])
    ordered = sorted(d['questions'], key=lambda q: q['appearances'] / q['complete'], reverse=True)
    return {'complete': total, 'appearances': appearances,
            'percentage': 100 * appearances / total,
            'questions': ordered,
            'businesses': sorted(d['businesses'], key=lambda b: b['appearances'], reverse=True)}


def from_records(metadata, records):
    """Map canonical saved records into this contract; no fuzzy identity matching.

    Each record: response_id, question_id, provider_id, repetition (1-based),
    status='complete', business_ids=[canonical IDs]. Repeated IDs within an
    answer count once. The upstream adapter must supply reconciled identities.
    Empty business_ids is a valid complete answer, not a failed response.
    Metadata supplies editorial fields and question/provider/business identities;
    all aggregate counts are overwritten from records.
    """
    if not isinstance(metadata, dict) or not isinstance(records, list):
        fail('Supply metadata object and a list of canonical response records.')
    d = deepcopy(metadata)
    text(d.get('target_id'), 'target_id', 80)
    indexed(collection(d.get('businesses'), 'businesses', 1, 6), 'businesses')
    ps = indexed(collection(d.get('providers'), 'providers', 1, 3), 'providers')
    qs = indexed(collection(d.get('questions'), 'questions', 1, 8), 'questions')
    reps = count(d.get('repetitions'), 'repetitions', 20)
    if not reps:
        fail('repetitions must be positive.')
    for obj in list(ps.values()) + list(qs.values()):
        obj['complete'] = obj['appearances'] = 0
    ids, cells, counts = set(), set(), Counter()
    for r in records:
        if not isinstance(r, dict):
            fail('Every record must be an object.')
        rid = text(r.get('response_id'), 'response_id', 100)
        pid, qid = r.get('provider_id'), r.get('question_id')
        if not isinstance(pid, str) or not isinstance(qid, str) or pid not in ps or qid not in qs:
            fail('Record references unknown question/provider.')
        repetition = count(r.get('repetition'), 'record.repetition', reps)
        if repetition < 1:
            fail('Record repetition must start at 1.')
        cell = (pid, qid, repetition)
        if rid in ids or cell in cells:
            fail('Duplicate response ID or provider/question/repetition run.')
        if r.get('status') != 'complete':
            fail('Incomplete response: resolve or rerun before baseline export.')
        names = r.get('business_ids')
        if not isinstance(names, list) or any(not isinstance(b, str) or not b.strip() for b in names):
            fail('business_ids must be a list of canonical non-empty IDs.')
        ids.add(rid); cells.add(cell)
        names = set(names)
        counts.update(names)
        for obj in (ps[pid], qs[qid]):
            obj['complete'] += 1
            obj['appearances'] += int(d['target_id'] in names)
    for b in collection(d.get('businesses'), 'businesses', 1, 6):
        b['appearances'] = counts[b['id']]
    d['evidence_basis'] = 'saved_response_records'
    return validate_report(d)
