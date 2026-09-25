"""In-memory client summary, with three extra pages when saved review sets exist.

Vendored from the streamlit-client-report package supplied on 2026-09-21, then restyled to
match the approved Garden Bar draft: same palette, stat tiles, callout boxes and bar scaling,
measured from that draft's own geometry. Every sentence is chosen from the validated data so
it stays true for any result (all equal, all zero, ties). Content that does not fit stops the
export instead of being clipped or shrunk.
"""
from datetime import date
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib.colors import HexColor, white
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph

from .model import ReportValidationError, metrics, validate_report

NAVY, BLUE, TEAL, PALE, GREY, RULE = map(
    HexColor, ['#14253B', '#345BEB', '#008C86', '#F0F4F8', '#526171', '#DCE3EA']
)
W, H = 595.28, 841.89
LEFT, RIGHT, WIDTH = 44, 551, 507
FOOTER_TOP = 785  # content may not reach below this distance from the top of the page


def safe(value):
    # Normalize unsupported dash glyphs before inserting text into Paragraph markup.
    return escape(str(value)).replace('‑', '-').replace('–', '-').replace('—', '-')


def sentence(value):
    value = safe(str(value).strip())
    return value if value.endswith(('.', '!', '?')) else value + '.'


def quoted(value):
    return '“' + safe(value) + '”'


def join_names(names):
    names = list(names)
    return ', '.join(names[:-1]) + ' and ' + names[-1] if len(names) > 1 else ''.join(names)


def long_date(iso):
    d = date.fromisoformat(iso)
    return f'{d.day} {d:%B %Y}'


class ReportLayoutError(ReportValidationError):
    pass


TOTAL_PAGES = 8


class Page:
    """Top-down layout cursor in points from the top edge, matching the draft's spacing."""

    def __init__(self, canvas, data, level=0):
        self.c, self.data, self.level = canvas, data, level
        self.top, self.number = 0, 0

        def style(name, font, size, leading, color=NAVY):
            return ParagraphStyle(name, fontName=font, fontSize=size, leading=leading, textColor=color)

        self.styles = {
            'body': style('body', 'Helvetica', 11, 16),
            'small': style('small', 'Helvetica', 9, 13, GREY),
            'heading': style('heading', 'Helvetica-Bold', 15, 19),
            'title': style('title', 'Helvetica-Bold', 27, 32),
            'label12': style('label12', 'Helvetica', 12, 16),
            'label12b': style('label12b', 'Helvetica-Bold', 12, 16),
        }

    def need(self, height):
        if self.top + height > FOOTER_TOP:
            raise ReportLayoutError(
                f'Page {self.number} is too long. Shorten the supplied text; export stopped to avoid '
                'clipping or an unreadable font size.')

    def para(self, markup, kind='body', gap=10, x=LEFT, width=WIDTH, draw=True):
        if self.level >= 2 and gap >= 8:
            gap -= 3  # tighter spacing between paragraphs; type size is never reduced
        paragraph = Paragraph(markup, self.styles[kind])
        _, height = paragraph.wrap(width, 800)
        self.need(height + gap)
        if draw:
            paragraph.drawOn(self.c, x, H - self.top - height)
        self.top += height + gap
        return height

    def heading(self, title):
        self.para(safe(title), 'heading', 9)

    def eyebrow(self, text, x=LEFT, size=9, baseline_offset=9):
        self.c.setFont('Helvetica-Bold', size)
        self.c.setFillColor(TEAL)
        self.c.drawString(x, H - self.top - baseline_offset, text.upper())

    def eyebrow_row(self, text):
        self.need(26)
        self.eyebrow(text)
        self.top += 26

    def start(self, number, eyebrow, title, subtitle):
        self.number = number
        c, d = self.c, self.data
        c.setFillColor(BLUE)
        c.rect(0, H - 8, W, 8, stroke=0, fill=1)
        c.setFont('Helvetica-Bold', 9)
        c.setFillColor(GREY)
        c.drawString(LEFT, H - 41, d['business_name'].upper())
        c.setFont('Helvetica', 8)
        label = 'CLIENT SUMMARY DRAFT' if d.get('draft', True) else 'CLIENT SUMMARY'
        c.drawRightString(RIGHT, H - 41, f"{label} | {long_date(d['audit_date']).upper()}")
        c.setStrokeColor(RULE)
        c.setLineWidth(1)
        c.line(LEFT, H - 793, RIGHT, H - 793)
        c.setFont('Helvetica', 8)
        c.setFillColor(GREY)
        c.drawString(LEFT, H - 808, f"AI visibility | Baseline audit: {long_date(d['audit_date'])}")
        extra = 3 if d.get('review_analysis') else 0
        c.drawRightString(RIGHT, H - 808, f'{number} / {TOTAL_PAGES + extra}')
        self.top = 78
        self.eyebrow(eyebrow)
        self.top = 102
        self.para(safe(title), 'title', 12)
        self.para(subtitle, 'body', 22)

    def end(self):
        self.c.showPage()

    def callout(self, eyebrow, paragraphs):
        """Pale box with a teal label, as on the draft. paragraphs: (markup, kind) pairs."""
        parts = []
        for markup, kind in paragraphs:
            paragraph = Paragraph(markup, self.styles[kind])
            _, height = paragraph.wrap(WIDTH - 32, 800)
            parts.append((paragraph, height))
        text_height = sum(h for _, h in parts)
        box = text_height + 52
        self.need(box + 19)
        self.c.setFillColor(PALE)
        self.c.rect(LEFT, H - self.top - box, WIDTH, box, stroke=0, fill=1)
        self.top += 16
        self.eyebrow(eyebrow, x=LEFT + 16, size=10, baseline_offset=6)
        self.top += 22
        for paragraph, height in parts:
            paragraph.drawOn(self.c, LEFT + 16, H - self.top - height)
            self.top += height
        self.top += 14 + 19

    def tiles(self, items):
        """Three stat tiles; the first is navy. items: (number, label) pairs."""
        self.need(95 + 22)
        for index, (number, label) in enumerate(items):
            x = LEFT + index * 173
            self.c.setFillColor(NAVY if index == 0 else PALE)
            self.c.rect(x, H - self.top - 95, 161, 95, stroke=0, fill=1)
            self.c.setFillColor(white if index == 0 else TEAL)
            self.c.setFont('Helvetica-Bold', 25)
            self.c.drawString(x + 13, H - self.top - 37, number)
            paragraph = Paragraph(safe(label), ParagraphStyle(
                'tile', fontName='Helvetica', fontSize=11, leading=16, textColor=white if index == 0 else NAVY))
            _, height = paragraph.wrap(135, 200)
            if height > 34:
                raise ReportLayoutError('A tile label is too long; provide a shorter question label.')
            paragraph.drawOn(self.c, x + 13, H - self.top - 51 - height)
        self.top += 95 + 22

    def track_bar(self, label, value, total, highlight):
        """Page-3 style: label and count above a full-width track."""
        paragraph = Paragraph(safe(label), self.styles['body'])
        _, height = paragraph.wrap(430, 100)
        pitch = height + 32
        self.need(pitch)
        paragraph.drawOn(self.c, LEFT, H - self.top - height)
        self.c.setFont('Helvetica-Bold', 11)
        self.c.setFillColor(NAVY)
        self.c.drawRightString(RIGHT, H - self.top - 12, f'{value} of {total}')
        bar_top = self.top + height + 6
        self.c.setFillColor(PALE)
        self.c.rect(LEFT, H - bar_top - 8, WIDTH, 8, stroke=0, fill=1)
        if value:
            self.c.setFillColor(TEAL if highlight else BLUE)
            self.c.rect(LEFT, H - bar_top - 8, WIDTH * value / total, 8, stroke=0, fill=1)
        self.top += pitch

    def scaled_bar(self, label, value, maximum, target, count=4):
        """Page-4 style: label left, bar scaled to the largest business, count at the right."""
        if self.level >= 1:
            label = one_line(label, 'Helvetica-Bold' if target else 'Helvetica', 12, 186)
        paragraph = Paragraph(safe(label), self.styles['label12b' if target else 'label12'])
        _, height = paragraph.wrap(190, 100)
        floor = 36 if count <= 4 else 31 if count <= 6 else 27  # closer bars when eight are shown
        if self.level >= 4:
            floor = 24
        pitch = max(floor, height + (20 if count <= 4 else 12 if self.level < 4 else 8))
        self.need(pitch)
        paragraph.drawOn(self.c, LEFT, H - self.top - height)
        self.c.setFont('Helvetica-Bold', 12)
        self.c.setFillColor(NAVY)
        self.c.drawRightString(RIGHT, H - self.top - 12, str(value))
        if value and maximum:
            self.c.setFillColor(TEAL if target else BLUE)
            self.c.rect(240, H - self.top - 14, 270 * value / maximum, 12, stroke=0, fill=1)
        self.top += pitch


def one_line(text, font, size, width):
    """The text on one line, ending in an ellipsis if it has to be cut at a word boundary."""
    text = ' '.join(str(text).split())
    if stringWidth(text, font, size) <= width:
        return text
    words = text.split()
    while len(words) > 1:
        words.pop()
        candidate = ' '.join(words).rstrip(' ,;:-|&') + '\u2026'
        if stringWidth(candidate, font, size) <= width:
            return candidate
    while text and stringWidth(text + '\u2026', font, size) > width:
        text = text[:-1]
    return text.rstrip() + '\u2026'


def compact_source(source):
    """Drop the scheme and a leading www. so a source line fits on one line."""
    for prefix in ('https://www.', 'http://www.', 'https://', 'http://'):
        source = source.replace(prefix, '')
    return source


def tile_label(label, prefix='Answers about '):
    """Tile text that measurably fits two lines: shortened at a word boundary, ending in an ellipsis."""
    style = ParagraphStyle('tile', fontName='Helvetica', fontSize=11, leading=16)
    words = str(label).split()
    trimmed = False
    while True:
        text = prefix + ' '.join(words) + ('\u2026' if trimmed else '')
        _, height = Paragraph(safe(text), style).wrap(135, 200)
        if height <= 34 or not words:
            return text
        words.pop()
        trimmed = True


LAST_LEVEL = 4


def render_pdf(payload):
    """Return PDF bytes after validation; never write client data to disk.

    Content that does not fit is first condensed, step by step and each step strictly shorter:
    single-line names, tighter spacing, dropping one optional explanatory paragraph, then closer bars
    with the closing caveat folded into its heading. Type is never made smaller and nothing is
    clipped. Only if every step fails does the export stop with the layout error.
    """
    validated = validate_report(payload)
    error = None
    for level in range(LAST_LEVEL + 1):
        try:
            return _render(validated, level)
        except ReportLayoutError as exc:
            error = exc
    raise error


def _render(payload, level):
    d = validate_report(payload)
    m = metrics(d)
    out = BytesIO()
    canvas = Canvas(out, pagesize=(W, H))
    canvas.setTitle(f"{d['business_name']} - AI visibility summary" + (' (draft)' if d.get('draft', True) else ''))
    canvas.setAuthor('AI visibility report')
    page = Page(canvas, d, level)

    name = d.get('short_name') or d['business_name']
    total, appearances = m['complete'], m['appearances']
    qs = {q['id']: q for q in d['questions']}
    qsorted = m['questions']
    best, weakest = qsorted[0], qsorted[-1]
    same = best['appearances'] == weakest['appearances']
    per_q = best['complete']
    n_questions, providers, reps = len(qs), d['providers'], d['repetitions']
    provider_names = join_names(p['name'] for p in providers)
    per_provider = providers[0]['complete']
    named_for = sum(1 for q in d['questions'] if q['appearances'])
    first = d['actions'][0]
    bname = '<b>' + safe(name) + '</b>'

    # ---------------------------------------------------------------- page 1
    if appearances == 0:
        headline_sub = 'No test answer included your business.'
    elif same:
        headline_sub = 'Visibility was the same across every topic tested.'
    elif weakest['appearances'] == 0:
        headline_sub = f'Strongest visibility for {quoted(best["label"])}. No appearances for {quoted(weakest["label"])}.'
    else:
        headline_sub = f'Strongest visibility for {quoted(best["label"])}. Less consistent visibility for {quoted(weakest["label"])}.'
    page.start(1, 'Your results at a glance', f'How often does AI recommend {name}?', headline_sub)
    if same:
        tiles = [(f'{appearances} of {total}', 'Test answers included you'),
                 (str(n_questions), 'Customer questions tested'),
                 (str(len(providers)), 'AI providers used')]
    else:
        tiles = [(f'{appearances} of {total}', 'Test answers included you'),
                 (f'{best["appearances"]} of {best["complete"]}', tile_label(best['label'])),
                 (f'{weakest["appearances"]} of {weakest["complete"]}', tile_label(weakest['label']))]
    page.tiles(tiles)
    page.heading('What we found')
    if appearances == 0:
        page.para(f'{bname} did not appear in any of the {total} test answers.')
    else:
        pct = 100 * appearances / total
        coverage = ('It was named at least once for every customer question tested'
                    if named_for == n_questions
                    else f'It was named at least once for {named_for} of {n_questions} customer questions tested')
        page.para(f'{bname} appeared in approximately {pct:.0f}% of the {total} test answers. {coverage}'
                  + ('.' if same else ', but the frequency varied by topic.'))
    if same:
        page.para(f'All tested questions recorded the same number of appearances: <b>{best["appearances"]} of '
                  f'{best["complete"]}</b> each. There is no strongest or weakest topic within this test.')
    else:
        low = (f'{quoted(weakest["label"])} appeared in {weakest["appearances"]} of {weakest["complete"]}'
               if weakest['appearances'] else
               f'{quoted(weakest["label"])} did not appear in any of its {weakest["complete"]} answers')
        page.para(f'{quoted(best["label"])} was your strongest result: <b>{best["appearances"]} of '
                  f'{best["complete"]} answers</b>. {low}.')
    page.heading('What this means for you')
    if appearances == 0:
        page.para('This shows where to start looking, not why. The results do not establish what caused the outcome. '
                  'A sensible first step is to check that customers can easily find accurate information about your business.')
    elif same:
        page.para('No topic stood out as clearly stronger or weaker in this test. The results do not establish why.')
    else:
        strength = (f'{quoted(best["label"])} is a clear strength in this test.'
                    if best['appearances'] / best['complete'] >= 0.5 else
                    f'{quoted(best["label"])} was the topic where you appeared most often.')
        page.para(f'{strength} If {quoted(weakest["label"])} matters to your business, it is a sensible place to '
                  'investigate first. The results do not establish why the differences occurred.')
    page.callout('Our recommended starting point', [(safe(first['task']), 'body')])
    page.para('These are test answers, not customer visits or bookings. Appearing creates an opportunity to be '
              'considered; this audit does not measure whether anyone chose the business.', 'small')
    page.end()

    # ---------------------------------------------------------------- page 2
    page.start(2, 'Understanding the test', 'What AI visibility means',
               'A simple check of whether your business appears when someone asks for a local recommendation.')
    page.heading('Start with a real customer question')
    page.callout('One of the questions we tested', [('“' + safe(qs[first['question_id']]['text']) + '”', 'body')])
    page.para('An AI assistant may respond with several businesses. In this report, visibility means whether '
              f'{bname} was included in the answer. Being listed is different from being the first suggestion, '
              'receiving a website visit or winning a booking.')
    page.heading('How we checked')
    topics = ', '.join(q['label'] for q in d['questions'])
    if len(topics) > 210:
        topics = topics[:207].rsplit(', ', 1)[0] + ', plus others'
    chosen = 'chosen around your priorities' if d['owner_reviewed_questions'] else 'chosen for this test'
    page.para(f'<b>{n_questions} customer question{"s were" if n_questions != 1 else " was"} {chosen}:</b> {safe(topics)}.')
    page.para(f'Each question was asked {reps} time{"s" if reps != 1 else ""} through each of {len(providers)} '
              f'provider{"s" if len(providers) != 1 else ""}: {safe(provider_names)}. This produced {per_q} answers per '
              f'question and {total} answers overall. The saved audit records web search as '
              f'{"enabled" if d["web_search_enabled"] else "disabled"}, and all {total} answers were saved.')
    page.heading('Why ask the same question more than once?')
    page.para('AI answers can vary. Repeating each question lets us see whether your business appeared consistently '
              'within this small test, rather than relying on a single answer.')
    page.heading('What the test can and cannot tell us')
    page.para('It shows how often you appeared for these questions on the audit date. The questions '
              + ('reflect your priorities; they' if d['owner_reviewed_questions'] else 'were not all set by the owner; they')
              + ' do not measure how often customers ask each question in the real world.')
    page.para('The tests used automated connections to the providers, known as APIs. Answers may differ from those in '
              'their public apps. Location settings, personalisation, model changes and the wording of a question can '
              'affect comparability.')
    page.para(f'<b>Reading the figures:</b> “2 of {per_q}” means the business was included in two test answers '
              'to that question. It does not mean two customers visited or booked. A business counts once per answer, '
              'however often its name appears.', 'small')
    page.end()

    # ---------------------------------------------------------------- page 3
    page.start(3, 'Visibility by customer need', 'Where you appeared most often',
               f'Each topic below represents one customer question, tested {per_q} times. Labels are shortened for readability.')
    for q in qsorted:
        page.track_bar(q['label'], q['appearances'], q['complete'],
                       highlight=(not same and q['appearances'] == best['appearances']))
    page.heading('What stands out')
    if same:
        page.para(f'Every topic recorded the same result, <b>{best["appearances"]} of {best["complete"]}</b>, so there is '
                  'no strongest or weakest topic in this test.')
    else:
        if best['appearances']:
            page.para(f'<b>Build on {quoted(best["label"])}.</b> Keep useful information about it accurate and current. '
                      'This is your strongest measured topic, although the test does not explain what caused that result.')
        page.para(f'<b>Investigate {quoted(weakest["label"])}.</b> It appeared less consistently. If it matters '
                  'commercially, start by checking the information customers need to decide and enquire.')
    page.para(f'<b>Keep the sample in perspective.</b> One additional appearance changes a topic result by one out of '
              f'{per_q}. Small changes in a later test should not automatically be treated as a lasting improvement.', 'small')
    page.end()

    # ---------------------------------------------------------------- pages 4 and 5: competitors
    by_id = {b['id']: b for b in d['businesses']}
    target_b = by_id[d['target_id']]
    target_count = target_b['appearances']
    named = [by_id[i] for i in d.get('named_ids') or []]
    unverified = set(d.get('unverified_ids') or [])
    visible_ids = d.get('visible_ids')
    visible = ([by_id[i] for i in visible_ids] if visible_ids is not None
               else [b for b in m['businesses'] if b['id'] != d['target_id']][:9])

    def bars(rows):
        ranked = sorted([target_b, *rows], key=lambda b: (-b['appearances'], b['id'] != d['target_id'], b['name']))
        if all('provider_appearances' in b for b in ranked):
            table_rows = [[b['name'], *[str(b['provider_appearances'][p['id']]) for p in providers],
                           str(b['appearances'])] for b in ranked]
            draw_table(page, ['Business', *[p['name'] for p in providers], 'Total'], table_rows,
                       [215, *([222 / len(providers)] * len(providers)), 70])
            page.para('Completed answers per tool: ' + safe('; '.join(f"{p['name']}: {p['complete']}" for p in providers))
                      + '. Each row adds up to its total; zero means no appearances.', 'small')
            return
        top_value = max(b['appearances'] for b in ranked)
        for b in ranked:
            is_target = b['id'] == d['target_id']
            shown = d.get('short_name') if is_target and level >= 1 and d.get('short_name') else b['name']
            page.scaled_bar(shown, b['appearances'], top_value, target=is_target, count=len(ranked))

    def comparison(rows):
        more = [b for b in rows if b['appearances'] > target_count]
        level_with = [b for b in rows if b['appearances'] == target_count]
        fewer = [b for b in rows if b['appearances'] < target_count]
        parts = []
        if more:
            parts.append(f'{len(more)} appeared more often than {safe(name)}')
        if level_with:
            parts.append(f'{len(level_with)} equally often')
        if fewer:
            parts.append(f'{len(fewer)} less often')
        return parts

    page.start(4, 'Competitors you named', 'Who you told us you compete with',
               f'These are the businesses you named as competitors, compared with {safe(name)} in the same test answers.')
    if named:
        page.eyebrow_row('Businesses you named | appearances in the test')
        bars(named)
        parts = comparison(named)
        page.para(f'Of the {len(named)} business{"es" if len(named) != 1 else ""} you named, ' + join_names(parts) + '.'
                  + f' {bname} appeared in {target_count} of {total} answers.')
        not_in_db = [b for b in named if b['id'] in unverified]
        if not_in_db:
            page.para(safe(join_names(b['name'] for b in not_in_db)) + (' is' if len(not_in_db) == 1 else ' are')
                      + ' not in our business database, so the count shown includes only AI answer names a reviewer matched to '
                      + ('it' if len(not_in_db) == 1 else 'them') + '.', 'small')
    else:
        page.para('No competitors were named for this audit, so there is nothing to compare here. The next page shows the '
                  'businesses the AI assistants recommended most often for your questions.')
    page.para('An answer can include several businesses. These figures describe the selected test, not local market '
              'share, business quality or actual booking performance.', 'small')
    page.end()

    page.start(5, 'What the AI assistants think', 'Who AI treats as your competitors',
               f'For the {n_questions} question{"s" if n_questions != 1 else ""} we tested, these are the businesses the assistants recommended most often.')
    page.eyebrow_row('Most often recommended | appearances in the test')
    bars(visible)
    named_ids = set(d.get('named_ids') or [])
    both = [b for b in visible if b['id'] in named_ids]
    new_names = [b for b in visible if b['id'] not in named_ids]
    ahead = sorted((b for b in visible if b['appearances'] > target_count), key=lambda b: b['appearances'])
    def were(count):
        return 'was' if count == 1 else 'were'

    if named and visible:
        if len(both) == len(visible):
            overlap = 'This business was also on your list.' if len(visible) == 1 else 'All of these were also on your list.'
        elif not both:
            overlap = 'None of these were on your list.'
        else:
            overlap = f'{len(both)} of these {len(visible)} {were(len(both))} also on your list: {safe(join_names(b["name"] for b in both))}.'
    else:
        overlap = ''
    difference = ''
    if named and new_names and level < 3:
        difference = (f' The assistants also treat {safe(join_names(b["name"] for b in new_names))} as '
                      f'{"alternatives" if len(new_names) != 1 else "an alternative"} for these questions, which you did not name.')
    if ahead:
        gap_sentence = (f' The nearest business above {safe(name)} was {safe(ahead[0]["name"])}, '
                        f'{ahead[0]["appearances"] - target_count} appearance{"s" if ahead[0]["appearances"] - target_count != 1 else ""} ahead.')
    elif visible and any(b['appearances'] == target_count for b in visible):
        gap_sentence = f' {safe(name)} was level with the most visible businesses shown.'
    else:
        gap_sentence = f' {safe(name)} had the most appearances of the businesses shown.'
    page.para((overlap + difference + gap_sentence).strip())
    page.para('An answer can include several businesses. These figures describe the selected test, not local market share, '
              'business quality or actual booking performance. This report does not show that any page, review or listing '
              'caused another business\'s higher visibility.', 'small')
    page.end()

    # ---------------------------------------------------------------- page 6
    page.start(6, 'Providers and evidence', 'What sits behind the recommendations',
               'How the providers compared, and what we looked at to shape the suggested actions.')
    page.heading('Your results differed by provider')
    counts = [p['appearances'] for p in providers]
    if all(c == counts[0] for c in counts):
        provider_note = f'{bname} appeared equally often across the providers.'
    elif all(counts):
        provider_note = (f'Your business appeared across all {len(providers)}, but the frequency varied. This does not '
                         'establish why one provider included you more often.')
    else:
        missing = join_names(p['name'] for p in providers if not p['appearances'])
        provider_note = f'Your business did not appear in any answer from {safe(missing)}. This does not establish why.'
    page.callout(f'{name} | out of {per_provider} answers per provider', [
        ('<b>' + ('&nbsp;' * 4).join(f'{safe(p["name"])}: {p["appearances"]} of {p["complete"]}' for p in providers) + '</b>', 'body'),
        (provider_note, 'body'),
    ])
    page.heading('What we can learn from competitors')
    layers = d.get('evidence_layers') or []
    if layers:
        looked = ' and '.join(layers)
        page.para(f'The businesses recommended most often give useful examples to investigate. We looked at their {looked}, alongside '
                  'yours, to shape the actions in this report. This report does not show that a particular page, review or '
                  'listing caused their higher visibility.')
    else:
        page.para('The businesses recommended most often give useful examples to investigate. This report does not show that a '
                  'particular page, review or listing caused their higher visibility.')
    if d.get('evidence'):
        page.heading('What we checked')
        for e in d['evidence']:
            page.para('<b>' + safe(e['id']) + ':</b> ' + safe(e['observation']) + '<br/><b>Source:</b> ' + safe(compact_source(e['source']) if level >= 2 else e['source']), 'small', 7)
        page.para('These observations do not establish why an AI provider included a business.', 'small')
    else:
        page.para('No sourced website or review observations were supplied for this summary. Compare relevant pages and '
                  'customer information before claiming that a competitor has stronger evidence. Missing evidence is not '
                  'poor performance.', 'small')
    page.end()

    # ---------------------------------------------------------------- page 7
    any_verified = any(a['status'] == 'verified_gap' for a in d['actions'])
    page.start(7, 'Your action plan', 'Three practical priorities',
               'These are proposed checks and improvements. Where an action rests on an observation, its source is shown on page 6.'
               if any_verified else
               'These are proposed checks and improvements. This audit does not establish that the suggested information is currently missing.')
    for i, a in enumerate(d['actions'], 1):
        q = qs[a['question_id']]
        page.eyebrow_row(f'{i} | {a["title"]}')
        if a['status'] == 'verified_gap':
            observed = next((e['observation'] for e in d.get('evidence', []) if e['id'] in a['evidence_ids']), '')
            page.para('<b>Why:</b> ' + safe(observed), 'body')
        elif a.get('why'):
            page.para('<b>Why:</b> ' + safe(a['why']), 'body')
        else:
            page.para(f'<b>Why:</b> you appeared in {q["appearances"]} of {q["complete"]} answers about {quoted(q["label"])}.', 'body')
        if a['status'] == 'suggested_check':
            page.para('<b>Check and improve:</b> ' + safe(a['task']), 'body', 12)
        else:
            page.para('<b>Action for a documented gap:</b> ' + safe(a['task']), 'body', 6)
            page.para('<b>Evidence:</b> ' + safe(', '.join(a['evidence_ids'])) + ' (observations on page 6).', 'small', 6)
        page.para('<b>Suggested owner:</b> ' + safe(a['owner']), 'small', 0)
        page.para('<b>Done when:</b> ' + sentence(a['done_when']), 'small', 20)
    page.para('These actions aim to make the business easier to understand and choose. Their effect on future AI answers '
              'is unproven; no change in recommendations is guaranteed.', 'small')
    page.end()

    # ---------------------------------------------------------------- page 8
    page.start(8, 'Delivery and follow-up', 'How to put this into practice',
               'Agree the priorities, check and improve the information, then repeat the test using a comparable approach.')
    page.heading('A simple delivery sequence')
    page.para('<b>Weeks 1-2 | Confirm and check.</b> Agree which customer needs matter most commercially, review the '
              'relevant pages and profiles, and assign an owner to each task.', 'body', 8)
    page.para('<b>Weeks 3-6 | Update and verify.</b> Publish the agreed improvements and test the enquiry routes. '
              'This is an illustrative schedule; timing depends on the work identified.', 'body', 8)
    page.para(f'<b>8-12 weeks after the updates are complete | Remeasure.</b> Repeat the original {n_questions} '
              'question' + ('s' if n_questions != 1 else '') + ' with the same repetitions and comparable settings, and record '
              'any changes in models or method. This is a proposed interval, not a promised time to results.')
    page.heading('What progress would look like')
    compare = f'compare against {appearances} of {total} overall'
    if not same:
        compare += (f', {best["appearances"]} of {best["complete"]} for {quoted(best["label"])} and '
                    f'{weakest["appearances"]} of {weakest["complete"]} for {quoted(weakest["label"])}')
    page.para('<b>Delivery:</b> accurate pages, usable enquiry routes and consistent business details.<br/>'
              f'<b>AI visibility:</b> {compare}.<br/>'
              '<b>Business outcomes:</b> separately monitor relevant enquiries and bookings where records allow. Do not '
              'attribute changes to AI visibility without supporting evidence.')
    page.heading('Evidence and limits')
    basis = ('Counts were calculated from the saved response records.' if d['evidence_basis'] == 'saved_response_records'
             else 'Counts were supplied as source-report aggregates. They have been checked for arithmetic consistency, '
                  'not independently verified against saved answers.')
    limits = ' '.join(safe(item) for item in d.get('limitations', []))
    page.para(f'This report summarises the saved audit dated {long_date(d["audit_date"])}. {safe(basis)} Websites and '
              'reviews have not been independently checked.' + (' ' + limits if limits else ''), 'small', 8)
    page.para('Before a later comparison, keep the exact questions, counting rule and provider settings. <b>Models:</b> '
              + safe('; '.join(f'{p["name"]}: {p["model"]}' for p in providers))
              + '. <b>Source:</b> ' + safe(d['source_note']), 'small', 12)
    decision = (f'Confirm whether {quoted(weakest["label"])} is a priority you want to develop. Then approve a focused '
                'information check so the work addresses verified gaps.'
                if not same else
                'Confirm which of the tested topics matter most commercially. Then approve a focused information check so '
                'the work addresses verified gaps.')
    page.callout('First decision', [(decision, 'body')])
    page.end()

    if d.get('review_analysis'):
        render_reviews(page, d)
    canvas.save()
    return out.getvalue()


def draw_table(page, headers, rows, widths):
    """Wrapped cells with measured row heights; no truncation or font shrinking."""
    for index, row in enumerate([headers, *rows]):
        cells = [Paragraph(('<b>' + safe(value) + '</b>') if index == 0 else safe(value),
                           page.styles['small']) for value in row]
        heights = [cell.wrap(width - 12, 800)[1] for cell, width in zip(cells, widths)]
        height = max(heights) + 14
        page.need(height)
        if index % 2 == 0:
            page.c.setFillColor(PALE)
            page.c.rect(LEFT, H - page.top - height, WIDTH, height, stroke=0, fill=1)
        x = LEFT
        for cell, width, cell_height in zip(cells, widths, heights):
            cell.drawOn(page.c, x + 6, H - page.top - 7 - cell_height)
            x += width
        page.top += height
    page.top += 14


def render_reviews(page, data):
    review = data['review_analysis']
    samples = review['businesses']
    target = next((b for b in samples if b['id'] == data['target_id']), None)
    page.start(9, 'Customer review evidence', 'What customers say about the businesses',
               'The selected review comparison uses saved customer text. It is a different set from the most-visible businesses on page 5.')
    rows = []
    for sample in samples:
        n = sample['sample_size']
        rating = f"{sample['rating']:.2f} / 5 ({sample['rated_count']} rated)" if sample['rating'] is not None else 'Unavailable'
        rows.append([sample['name'], str(n) if n else 'Unavailable', rating, sample['date_range']])
    draw_table(page, ['Business', 'Text reviews', 'Sample mean rating', 'Review dates'], rows, [190, 65, 112, 140])
    if target and target['sample_size']:
        page.heading('Your review evidence')
        page.para(f"{safe(data['business_name'])}: {target['sample_size']} usable text reviews, dated {safe(target['date_range'])}. "
                  f"{target['low_ratings']} of {target['rated_count']} rated reviews scored one or two stars. "
                  'Ratings describe the saved sample, not the current Google listing or the sentiment of every sentence.')
    else:
        page.para('No usable customer review text was saved for your business. Review themes cannot be assessed.')
    page.heading('How to read the comparison')
    page.para('The saved sets may cover different dates and sample sizes. Missing text means unavailable, not no reviews or poor service. '
              'A one-review sample cannot support a reliable view of a business. More reviews or a higher rating does not establish why an AI tool recommended it.', 'body')
    page.para(safe(review['source']), 'small')
    page.end()
    page.start(10, 'Comparing customer evidence', 'Which themes stand out in the reviews?',
               'The most-mentioned tracked themes for each business. Counts and percentages refer to its own saved text sample.')
    rows = []
    for sample in samples:
        n = sample['sample_size']
        ranked = sorted(sample['themes'].items(), key=lambda item: (-item[1], item[0]))
        positive = [(label, count) for label, count in ranked if count]
        threshold = positive[min(1, len(positive) - 1)][1] if positive else 0
        leaders = [(label, count) for label, count in positive if count >= threshold]
        description = '; '.join(f'{label}: {count}/{n} ({100 * count / n:.0f}%)' for label, count in leaders)
        rows.append([sample['name'], description or ('No tracked terms found' if n else 'Review text unavailable')])
    draw_table(page, ['Business', 'Leading tracked themes (including ties)'], rows, [205, 302])
    page.para('These are mentions, not endorsements. Percentages help compare unequal sample sizes, but a small or older sample '
              'can still mislead. Only the tracked themes are ranked; customers may describe other benefits in different words. '
              'Use these differences to guide a closer read, not to rank service quality or infer an AI ranking factor.', 'body')
    page.para(safe(review['source']), 'small')
    page.end()
    page.start(11, 'Reviews and AI visibility', 'Does customer proof match the work you want?',
               'Service mentions in your saved reviews are shown beside appearances for related test questions. These are two separate measurements.')
    rows = []
    for theme in review['themes']:
        n = target['sample_size'] if target else 0
        proof = f"{theme['reviews']} / {n}" if n else 'Unavailable'
        visibility = f"{theme['appearances']} / {theme['answers']}" if theme['answers'] else 'Not mapped'
        questions = ', '.join(f'Q{o}' for o in theme['question_orders']) or '-'
        rows.append([theme['label'], proof, visibility, questions])
    draw_table(page, ['Service / theme', 'Reviews mentioning it', 'AI appearances / answers', 'Questions'], rows, [170, 110, 137, 90])
    page.heading('What this means for your visibility')
    gaps = [t for t in review['themes'] if t['reviews'] and t['answers'] and not t['appearances']]
    if gaps:
        page.para('Customer proof exists for ' + safe(join_names(t['label'] for t in gaps))
                  + ', despite no appearances in the related test answers. This shows that having relevant reviews alone '
                  'did not ensure visibility in this test. Check how clearly the existing service pages present that proof.')
    else:
        page.para('Compare the service-specific proof with the questions that matter commercially. A theme match shows what customers '
                  'mentioned; it does not explain the AI result. Where proof or visibility is absent, investigate before calling it a gap.')
    page.heading('A practical next step')
    page.para('Choose one priority service. Read its matched reviews in full, including critical feedback. With appropriate permission, '
              'place accurate customer examples beside the relevant service information. Invite honest feedback across the work you actually deliver; '
              'do not script praise or ask customers to insert keywords. Repeat the same AI test after changes and track relevant enquiries separately.')
    page.para('Method: keyword matching, not an assessment of meaning or sentiment. A mention can be positive, negative or incidental; '
              'no match does not mean the service was never delivered. Themes and linked question groups can overlap, so do not add the rows together. '
              'The benchmark does not establish whether an AI tool read these reviews or used them to select a business.', 'small')
    page.end()
