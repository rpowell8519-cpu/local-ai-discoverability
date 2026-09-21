"""Six-page, in-memory client summary PDF. All data-derived markup is escaped.

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


class Page:
    """Top-down layout cursor in points from the top edge, matching the draft's spacing."""

    def __init__(self, canvas, data):
        self.c, self.data = canvas, data
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
        c.drawRightString(RIGHT, H - 41, f"CLIENT SUMMARY | {long_date(d['audit_date']).upper()}")
        c.setStrokeColor(RULE)
        c.setLineWidth(1)
        c.line(LEFT, H - 793, RIGHT, H - 793)
        c.setFont('Helvetica', 8)
        c.setFillColor(GREY)
        c.drawString(LEFT, H - 808, f"AI visibility | Baseline audit: {long_date(d['audit_date'])}")
        c.drawRightString(RIGHT, H - 808, f'{number} / 6')
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

    def scaled_bar(self, label, value, maximum, target):
        """Page-4 style: label left, bar scaled to the largest business, count at the right."""
        paragraph = Paragraph(safe(label), self.styles['label12b' if target else 'label12'])
        _, height = paragraph.wrap(190, 100)
        pitch = max(36, height + 20)
        self.need(pitch)
        paragraph.drawOn(self.c, LEFT, H - self.top - height)
        self.c.setFont('Helvetica-Bold', 12)
        self.c.setFillColor(NAVY)
        self.c.drawRightString(RIGHT, H - self.top - 12, str(value))
        if value and maximum:
            self.c.setFillColor(TEAL if target else BLUE)
            self.c.rect(240, H - self.top - 14, 270 * value / maximum, 12, stroke=0, fill=1)
        self.top += pitch


def fit_label(label, prefix, limit=135, lines=2, font='Helvetica', size=11):
    """Shorten a topic label at a word boundary until "prefix + label" fits a tile."""
    budget = limit * lines * 0.85
    words = label.split()
    while words and stringWidth(prefix + ' '.join(words), font, size) > budget:
        words.pop()
        ellipsis = '\u2026'
        if words and stringWidth(prefix + ' '.join(words) + ellipsis, font, size) <= budget:
            return prefix + ' '.join(words) + ellipsis
    return prefix + ' '.join(words) if words else prefix.strip()


def render_pdf(payload):
    """Return PDF bytes after validation; never write client data to disk."""
    d = validate_report(payload)
    m = metrics(d)
    out = BytesIO()
    canvas = Canvas(out, pagesize=(W, H))
    canvas.setTitle(f"{d['business_name']} - AI visibility summary")
    canvas.setAuthor('AI visibility report')
    page = Page(canvas, d)

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
                 (f'{best["appearances"]} of {best["complete"]}', fit_label(best['label'], 'Answers about ')),
                 (f'{weakest["appearances"]} of {weakest["complete"]}', fit_label(weakest['label'], 'Answers about '))]
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

    # ---------------------------------------------------------------- page 4
    others = [b for b in m['businesses'] if b['id'] != d['target_id']]
    page.start(4, 'Other businesses in the answers', 'Who appeared alongside you?',
               f'Appearance counts for {safe(name)} and the comparison businesses selected for this report.')
    page.eyebrow_row('Comparison businesses | appearances in the test')
    top_value = max(b['appearances'] for b in m['businesses'])
    for b in m['businesses']:
        page.scaled_bar(b['name'], b['appearances'], top_value, target=b['id'] == d['target_id'])
    target_count = next(b['appearances'] for b in m['businesses'] if b['id'] == d['target_id'])
    ahead = sorted((b for b in others if b['appearances'] > target_count), key=lambda b: b['appearances'])
    if others and ahead:
        gap_sentence = (f' The nearest business above {safe(name)} in this list was {safe(ahead[0]["name"])}, '
                        f'{ahead[0]["appearances"] - target_count} appearance{"s" if ahead[0]["appearances"] - target_count != 1 else ""} ahead.')
    elif others:
        gap_sentence = f' {safe(name)} had the most appearances of the businesses shown.'
    else:
        gap_sentence = ''
    page.para('An answer can include several businesses. These figures describe the selected test, not local market '
              'share, business quality or actual booking performance.' + gap_sentence)
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
    if d.get('evidence'):
        page.heading('Supporting observations')
        for e in d['evidence']:
            page.para('<b>' + safe(e['id']) + ':</b> ' + safe(e['observation']) + '<br/><b>Source:</b> ' + safe(e['source']), 'small', 7)
        page.para('These observations do not establish why an AI provider included a business.', 'small')
    else:
        page.heading('What we can learn from competitors')
        page.para('The other businesses give useful examples to investigate. This report does not show that a particular '
                  'page, review or listing caused their higher visibility.')
        page.para('No sourced website or review observations were supplied for this summary. Compare relevant pages and '
                  'customer information before claiming that a competitor has stronger evidence. Missing evidence is not '
                  'poor performance.', 'small')
    page.end()

    # ---------------------------------------------------------------- page 5
    any_verified = any(a['status'] == 'verified_gap' for a in d['actions'])
    page.start(5, 'Your action plan', 'Three practical priorities',
               'These are proposed checks and improvements. Where an action rests on an observation, its source is shown on page 4.'
               if any_verified else
               'These are proposed checks and improvements. This audit does not establish that the suggested information is currently missing.')
    for i, a in enumerate(d['actions'], 1):
        q = qs[a['question_id']]
        page.eyebrow_row(f'{i} | {a["title"]}')
        page.para(f'<b>Why:</b> you appeared in {q["appearances"]} of {q["complete"]} answers about {quoted(q["label"])}.', 'body')
        if a['status'] == 'suggested_check':
            page.para('<b>Check and improve:</b> ' + safe(a['task']), 'body', 12)
        else:
            page.para('<b>Action for a documented gap:</b> ' + safe(a['task']), 'body', 6)
            page.para('<b>Evidence:</b> ' + safe(', '.join(a['evidence_ids'])) + ' (observations on page 4).', 'small', 6)
        page.para('<b>Suggested owner:</b> ' + safe(a['owner']), 'small', 0)
        page.para('<b>Done when:</b> ' + sentence(a['done_when']), 'small', 20)
    page.para('These actions aim to make the business easier to understand and choose. Their effect on future AI answers '
              'is unproven; no change in recommendations is guaranteed.', 'small')
    page.end()

    # ---------------------------------------------------------------- page 6
    page.start(6, 'Delivery and follow-up', 'How to put this into practice',
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

    canvas.save()
    return out.getvalue()
