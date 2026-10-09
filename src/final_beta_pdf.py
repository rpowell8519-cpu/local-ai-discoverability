"""Lay out the Final Beta report. Presentation only: every figure and sentence comes from the report data.

Pages grow with the data. A block that will not fit starts a continuation page, so a long brief or a
long action never runs into the footer.
"""
from __future__ import annotations

from html import escape
from io import BytesIO
from typing import Any, Mapping

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, Table, TableStyle

INK, TEAL, SLATE = colors.HexColor('#203c33'), colors.HexColor('#244b3b'), colors.HexColor('#4d5f56')
CHALK, LIME, MIST = colors.HexColor('#f5f2e9'), colors.HexColor('#dae9a5'), colors.HexColor('#e7ecdf')
RULE, PAPER, AMBER = colors.HexColor('#cbd1c3'), colors.HexColor('#fffdf8'), colors.HexColor('#f1e0bd')
W, H = A4
M = 43
CW = W - 2 * M
BOTTOM = H - 66
BODY, BOLD, DISPLAY = 'Helvetica', 'Helvetica-Bold', 'Times-Roman'


def _clean(value: Any) -> str:
    return (str(value).replace('—', ' - ').replace('–', '-').replace('‑', '-').replace('→', ' > ')
            .replace(' ', ' ').replace('‘', "'").replace('’', "'").replace('“', '"').replace('”', '"')
            .replace('…', '...'))


def _e(value: Any) -> str:
    return escape(_clean(value))


def _date(value: Any) -> str:
    return f"{value.day} {value.strftime('%B %Y')}" if value else 'date not recorded'


def _of(n: Any, d: Any) -> str:
    return f'{n} of {d}'


class _Doc:
    def __init__(self, title: str, header: str, footer: str, total: int | None):
        self.buffer = BytesIO()
        self.c = canvas.Canvas(self.buffer, pagesize=A4, pageCompression=1)
        self.c.setTitle(_clean(title))
        self.c.setAuthor('Found.in.Brighton')
        self.header, self.footer, self.total, self.n, self.y = header, footer, total, 0, 0.0
        self.kicker = self.title = ''

    def style(self, size=10.7, leading=None, color=INK, font=BODY):
        return ParagraphStyle('p', fontName=font, fontSize=size, leading=leading or size * 1.35, textColor=color, spaceAfter=0)

    def _height(self, text, width, style):
        return Paragraph(_clean(text), style).wrap(width, H)[1]

    def _draw(self, text, x, top, width, style):
        p = Paragraph(_clean(text), style)
        _, height = p.wrap(width, H)
        p.drawOn(self.c, x, H - top - height)
        return height

    def start(self, kicker, title, subtitle=None):
        if self.n:
            self._finish()
        self.kicker, self.title = kicker, title
        self._open(kicker, title, subtitle)

    def _open(self, kicker, title, subtitle=None, continued=False):
        self.n += 1
        c = self.c
        c.setFillColor(PAPER); c.rect(0, 0, W, H, fill=1, stroke=0)
        c.setFillColor(INK); c.setFont(BOLD, 12); c.drawString(M, H - 34, 'Found.in.Brighton')
        c.setFont(BODY, 8); c.setFillColor(SLATE); c.drawRightString(W - M, H - 34, _clean(self.header))
        c.setFillColor(RULE); c.rect(M, H - 48, CW, .6, fill=1, stroke=0)
        self.y = 69
        self.y += self._draw(_e(str(kicker).upper()) + (' (CONTINUED)' if continued else ''), M, self.y, CW, self.style(8.8, 11, TEAL, BOLD)) + 9
        if continued:
            self.y += self._draw(_e(title), M, self.y, CW, self.style(15, 19, INK, DISPLAY)) + 12
            return
        self.y += self._draw(_e(title), M, self.y, CW, self.style(26, 30, INK, DISPLAY)) + 12
        if subtitle:
            self.y += self._draw(_e(subtitle), M, self.y, CW, self.style(11.2, 15, SLATE)) + 16

    def _finish(self):
        c = self.c
        c.setFillColor(RULE); c.rect(M, 47, CW, .5, fill=1, stroke=0)
        c.setFillColor(SLATE); c.setFont(BODY, 8); c.drawString(M, 32, _clean(self.footer))
        c.drawRightString(W - M, 32, f'{self.n:02d} / {self.total:02d}' if self.total else f'{self.n:02d}')
        c.showPage()

    def room(self, height):
        if self.y + height > BOTTOM:
            self._finish()
            self._open(self.kicker, self.title, continued=True)

    def para(self, text, size=10.7, gap=9, color=INK):
        style = self.style(size, color=color)
        self.room(self._height(text, CW, style))
        self.y += self._draw(text, M, self.y, CW, style) + gap

    def heading(self, text):
        style = self.style(13, 17, INK, BOLD)
        self.room(self._height(text, CW, style) + 60)
        self.y += 6
        self.y += self._draw(text, M, self.y, CW, style) + 6

    def note(self, text):
        self.para(text, size=8.5, gap=7, color=SLATE)

    def callout(self, label, text, tone='green'):
        bg = {'green': MIST, 'lime': LIME, 'amber': AMBER, 'dark': INK}[tone]
        fg = PAPER if tone == 'dark' else INK
        pad = 14
        h1 = self._height(_e(str(label).upper()), CW - 2 * pad, self.style(8.5, 11, fg, BOLD))
        h2 = self._height(text, CW - 2 * pad, self.style(11, 15, fg))
        height = pad * 2 + h1 + 6 + h2
        self.room(height)
        top = self.y
        self.c.setFillColor(bg); self.c.roundRect(M, H - top - height, CW, height, 7, fill=1, stroke=0)
        self._draw(_e(str(label).upper()), M + pad, top + pad, CW - 2 * pad, self.style(8.5, 11, fg, BOLD))
        self._draw(text, M + pad, top + pad + h1 + 6, CW - 2 * pad, self.style(11, 15, fg))
        self.y += height + 13

    def table(self, headers, rows, widths, size=9.6, pad=7):
        """Rows are drawn in page-sized groups, repeating the header on a continuation page."""
        rows = list(rows)
        while rows:
            take = len(rows)
            while True:
                t = self._table(headers, rows[:take], widths, size, pad)
                height = t.wrap(CW, H)[1]
                if self.y + height <= BOTTOM or take == 1:
                    break
                take -= 1
            if self.y + height > BOTTOM:
                self.room(height)
                continue
            t.drawOn(self.c, M, H - self.y - height)
            self.y += height + 12
            rows = rows[take:]
            if rows:
                self.room(BOTTOM)

    def _table(self, headers, rows, widths, size, pad):
        data = [[Paragraph(_clean(h), self.style(size, size * 1.25, PAPER, BOLD)) for h in headers]]
        data += [[Paragraph(_clean(x), self.style(size, size * 1.28)) for x in row] for row in rows]
        t = Table(data, colWidths=[CW * x for x in widths], hAlign='LEFT')
        t.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), INK), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                               ('LEFTPADDING', (0, 0), (-1, -1), 7), ('RIGHTPADDING', (0, 0), (-1, -1), 5),
                               ('TOPPADDING', (0, 0), (-1, -1), pad), ('BOTTOMPADDING', (0, 0), (-1, -1), pad),
                               ('ROWBACKGROUNDS', (0, 1), (-1, -1), [CHALK, PAPER]), ('LINEBELOW', (0, 1), (-1, -1), .45, RULE)]))
        return t

    def stats(self, items):
        gap = 12
        cw = (CW - gap * (len(items) - 1)) / len(items)
        height = 99
        self.room(height)
        for i, (value, label, detail) in enumerate(items):
            x = M + i * (cw + gap)
            self.c.setFillColor(INK if i == 0 else MIST); self.c.roundRect(x, H - self.y - height, cw, height, 6, fill=1, stroke=0)
            fg = PAPER if i == 0 else INK
            self._draw(_e(value), x + 12, self.y + 12, cw - 24, self.style(24, 27, fg, DISPLAY))
            self._draw(_e(label), x + 12, self.y + 45, cw - 24, self.style(10, 13, fg, BOLD))
            self._draw(_e(detail), x + 12, self.y + 73, cw - 24, self.style(8, 10, fg))
        self.y += height + 16

    def bars(self, items, total):
        for label, n in items:
            self.room(26)
            self._draw(f'<b>{_e(label)}</b>', M, self.y, CW * .46, self.style(9.8, 12))
            self.c.setFillColor(MIST); self.c.roundRect(M + CW * .47, H - self.y - 11, CW * .36, 9, 2, fill=1, stroke=0)
            if n and total:
                self.c.setFillColor(TEAL); self.c.roundRect(M + CW * .47, H - self.y - 11, CW * .36 * min(n / total, 1), 9, 2, fill=1, stroke=0)
            self.c.setFillColor(INK); self.c.setFont(BOLD, 9.5); self.c.drawRightString(W - M, H - self.y - 10, _of(n, total))
            self.y += 24

    def save(self):
        self._finish()
        self.c.save()
        return self.buffer.getvalue(), self.n


def _summary_lines(d: Mapping[str, Any]) -> list[str]:
    asked = [q for q in d['questions'] if q['complete']]
    lines = []
    strong = [q for q in asked if q['recommended'] * 3 >= q['complete'] * 2][:3]
    if strong:
        lines.append('<b>Strongest:</b> ' + '; '.join(f"{_e(q['label']).lower()} ({_of(q['recommended'], q['complete'])})" for q in strong) + '.')
    absent = [q for q in asked if q['recommended'] == 0]
    if absent:
        lines.append('<b>Absent:</b> ' + ', '.join(_e(q['label']).lower() for q in absent[:5])
                     + f" ({_of(0, sum(q['complete'] for q in absent))}).")
    moved = [q for q in asked if q['previous'] and q['previous']['complete'] == q['complete']
             and abs(q['recommended'] - q['previous']['recommended']) >= 3][:3]
    if moved:
        lines.append('<b>Changed since the earlier test:</b> ' + '; '.join(
            f"{_e(q['label']).lower()} {q['previous']['recommended']} to {q['recommended']} of {q['complete']}" for q in moved) + '.')
    ahead = [c for c in d['competitors']['ai'] if not c['target'] and c['recommended'] > d['competitors']['target_recommended']][:3]
    if ahead:
        lines.append('<b>Who else:</b> ' + ', '.join(_e(c['name']) for c in ahead) + (' is' if len(ahead) == 1 else ' are') + ' recommended more often.')
    s = d['sources']
    if s['available']:
        lines.append(f"<b>Sources:</b> your own website was cited in {_of(s['own_answers'], s['answers'])} answers.")
    r = d['reviews']
    if r:
        lines.append(f"<b>Customers:</b> {r['read']} reviews read, {r['five_star']} of them five-star.")
    return lines


def _render(d: Mapping[str, Any], total: int | None):
    short = d['short_name']
    doc = _Doc(f"{d['business']}: AI visibility findings", f"AI VISIBILITY FINDINGS / {_date(d['test_date']).split(' ', 1)[-1].upper()}",
               f"{d['business']} | Test of {_date(d['test_date'])}" + (f"; earlier test {_date(d['previous_date'])}" if d['previous_date'] else ''), total)
    asked = [q for q in d['questions'] if q['complete']]
    best = asked[0] if asked else None
    absent = [q for q in asked if q['recommended'] == 0]

    doc.start(f"{d['business']} / AI visibility: findings for discussion",
              f"{short} was recommended in {_of(d['recommended'], d['total'])} answers.",
              'How often the AI tools recommended you for the needs in your brief, who else they recommended, where they get their information, and what we would like to explore with you.')
    prev = d['previous_total']
    tiles = [(_of(d['recommended'], d['total']), 'All questions',
              _date(d['test_date']) + (f". It was {_of(prev['recommended'], prev['complete'])} earlier" if prev and prev['all_questions'] else ''))]
    if best:
        tiles.append((_of(best['recommended'], best['complete']), best['label'], 'Your strongest question'))
    tiles.append((_of(0, sum(q['complete'] for q in absent)), f"{len(absent)} question{'s' if len(absent) != 1 else ''} with no recommendation",
                  'Where you were not named at all') if absent else (str(len(asked)), 'Questions tested', 'Every one returned a recommendation'))
    doc.stats(tiles[:3])
    doc.heading('Summary')
    doc.para('<br/>'.join(_summary_lines(d)) or 'No completed answers are available.', size=10.6)
    has_cites = d['sources']['available']
    doc.table(['AI tool', f'Recommended {_e(short)} in'] + (['Cited your website in'] if has_cites else []),
              [[_e(p['name']), f"{_of(p['recommended'], p['complete'])} answers"] + ([f"{_of(p['cited_own'], p['complete'])} answers"] if has_cites else [])
               for p in d['providers']], [.42, .29, .29] if has_cites else [.5, .5], 10)
    doc.note(f"{len(asked)} questions, {len(d['providers'])} AI tools, {d['repetitions']} repeats each"
             + (', live web search on.' if d['web_search'] else ', web search off.'))

    tools = [p['name'] for p in sorted(d['providers'], key=lambda p: p['name'] != 'OpenAI')]
    tools = [n for n in ('OpenAI', 'Claude', 'Gemini') if n in {p['name'] for p in d['providers']}] or tools
    has_prev = any(q['previous'] for q in asked)
    doc.start('02 / Where you appear', 'Named and recommended, question by question.',
              f"Named: {short} is mentioned anywhere in the answer. Recommended: it is in the list of suggestions.")
    headers = ['Priority', 'Question asked', 'Named', 'Recommended'] + tools + (['Earlier'] if has_prev else [])
    spare = 1 - (.155 + .085 + .15 + .083 * len(tools) + (.081 if has_prev else 0))
    widths = [.155, spare, .085, .15] + [.083] * len(tools) + ([.081] if has_prev else [])
    rows = []
    for q in d['questions']:
        if not q['complete']:
            rows.append([f"<b>{_e(q['label'])}</b>", 'Not tested in this run.', '-', '<b>Unknown</b>'] + ['-'] * len(tools) + (['-'] if has_prev else []))
            continue
        rows.append([f"<b>{_e(q['label'])}</b>", _e(q['text']), _of(q['named'], q['complete']), f"<b>{_of(q['recommended'], q['complete'])}</b>"]
                    + [_of(q['providers'][t]['recommended'], q['providers'][t]['complete']) if t in q['providers'] else '-' for t in tools]
                    + ([_of(q['previous']['recommended'], q['previous']['complete']) if q['previous'] else 'New'] if has_prev else []))
    doc.table(headers, rows, widths, 8.5, 4)
    if d['named'] == d['recommended']:
        doc.callout('Named versus recommended', f"In all {d['total']} answers the two figures match: whenever an AI tool names {_e(short)}, it is recommending it, never mentioning it in passing.", 'lime')
    else:
        doc.callout('Named versus recommended', f"{_e(short)} was named in {d['named']} answers and recommended in {d['recommended']}. In the other {d['named'] - d['recommended']} it was mentioned without being one of the suggestions.", 'lime')
    if has_prev:
        doc.note(f"\"Earlier\" is the same question in the test of {_date(d['previous_date'])}, counted by matching your business name in the answers.")

    comp = d['competitors']
    doc.start('03 / Who else appears', "Your list, and the AI's list.", f"Recommendations across the {comp['total']} answers, for the businesses we verified.")
    doc.heading('You told us your competitors are')
    if comp['named']:
        doc.table(['Competitor you named', 'Recommended in', f"Compared with {_e(short)} ({_of(comp['target_recommended'], comp['total'])})"],
                  [[_e(c['name']), _of(c['recommended'], comp['total']),
                    'More often' if c['recommended'] > comp['target_recommended'] else 'As often' if c['recommended'] == comp['target_recommended'] else 'Less often']
                   for c in sorted(comp['named'], key=lambda c: -c['recommended'])], [.46, .22, .32], 9)
    else:
        doc.para('No competitors were named in your brief.')
    doc.heading('In AI answers you are competing with')
    rank, last, shown = 0, None, []
    for i, c in enumerate(comp['ai'], 1):
        rank = i if c['recommended'] != last else rank
        last = c['recommended']
        name = f"{rank}. {_e(c['name'])}"
        shown.append([f'<b>{name}</b>' if c['target'] else name, f"<b>{_of(c['recommended'], comp['total'])}</b>" if c['target'] else _of(c['recommended'], comp['total'])])
    doc.table(['Most recommended', 'Recommended in'], shown, [.64, .36], 9)
    if comp['unlisted']:
        names = comp['unlisted'][:3]
        doc.callout('Worth discussing', f"{_e(', '.join(names))} {'was' if len(names) == 1 else 'were'} not on your list, yet {'is' if len(names) == 1 else 'are'} recommended at least as often as {_e(short)}. Do you see {'it' if len(names) == 1 else 'them'} as a rival?", 'amber')

    s = d['sources']
    if s['available']:
        top_business = max([s['own_answers']] + [n for _, n in s['business_sites']] or [0])
        doc.start('04 / Where the AI gets its information',
                  'Your own website is the most-cited business website.' if s['own_answers'] >= top_business and s['own_answers'] else 'The sources behind the answers.',
                  f"{s['answers_with_citations']} of the {s['answers']} answers cited their sources: {s['citations']} citations across {s['websites']} websites. They fall into two kinds.")
        doc.heading("Businesses' own websites: answers citing each")
        doc.bars(sorted([(f'{short} (your website)', s['own_answers'])] + list(s['business_sites']), key=lambda item: -item[1]), s['answers'])
        if s['independent']:
            doc.heading('Independent sources the AI tools rely on')
            doc.table(['Source', 'Answers citing it', f'Is {_e(short)} on the pages cited?'],
                      [[_e(i['domain']), str(i['answers']), f"<b>{i['status']}</b>" if i['status'] != 'To check' else 'To check'] for i in s['independent']],
                      [.46, .22, .32], 8.8, 5)
            gaps = [i['domain'] for i in s['independent'] if i['status'] == 'Not found']
            doc.callout('Why this matters', 'These independent sources are where the AI tools look when they compare businesses, for you and for everyone you compete with.'
                        + (f" You were not found on the pages cited from {_e(', '.join(gaps[:4]))}." if gaps else ''), 'lime')
        doc.note('Checked by reading the pages the AI tools cited, where they could be read. A source shows what an AI tool referred to, not why it chose a business.'
                 + (f" {s['unnamed_citations']} citations had an incomplete website name and are left out." if s['unnamed_citations'] else ''))
    else:
        doc.start('04 / Where the AI gets its information', 'The sources behind the answers.',
                  'When an AI tool searches the web, it reads particular sites before it answers.')
        doc.callout('Not available for this test', 'This test was run before the sources each AI tool cites were being saved. A fresh run of the same questions will record them.', 'amber')

    r = d['reviews']
    if r:
        doc.start('05 / What your customers say', f"{r['read']} reviews read. {r['five_star']} are five-star.",
                  f"We read {r['read']}" + (f" of your {r['google_total']}" if r['google_total'] and r['google_total'] >= r['read'] else '') + ' Google reviews'
                  + (f" ({_date(r['first'])} to {_date(r['last'])})" if r['first'] else '') + '.'
                  + (f" Google shows an overall rating of {r['google_rating']:g}." if r['google_rating'] else ''))
        if r['themes']:
            doc.bars(r['themes'], r['read'])
        extra = []
        if r['also']:
            extra.append('<b>Also mentioned:</b> ' + ', '.join(f"{_e(l).lower()} ({n})" for l, n in r['also']) + '.')
        if r['rated']:
            extra.append(f"<b>Ratings:</b> {r['five_star']} five-star, {r['four_star']} four-star, {r['three_or_below']} three-star or below.")
        if r['first']:
            extra.append(f"<b>Recency:</b> {r['recent']} of the {r['read']} are from the last twelve months.")
        doc.para('<br/>'.join(extra), size=10.6)
        if r['quote']:
            doc.callout("In a customer's words", f"\"{_e(r['quote']['text'][:420])}\" (Google review, {_date(r['quote']['date']).split(' ', 1)[-1] if r['quote']['date'] else 'undated'})", 'green')
        doc.note('Counts are reviews that mention each topic, found by keyword; a review can mention several.')
    else:
        doc.start('05 / What your customers say', 'No reviews have been read yet.', 'Customer reviews were not collected for this report.')

    doc.start('06 / What the evidence shows', 'Actions the evidence supports, and what to investigate.',
              'Observations from the results, the cited sources, your website and your reviews. They are not proven causes.')
    if d['actions']:
        doc.heading('Actions the evidence supports')
        for i, action in enumerate(d['actions'], 1):
            doc.para(f"<b>{i}. {_e(action['title'])}</b><br/>" + '<br/>'.join(x for x in (
                f"<b>Why:</b> {_e(action['why'])}" if action['why'] else '', f"<b>What to do:</b> {_e(action['action'])}" if action['action'] else '',
                f"<b>Based on:</b> {_e(action['basis'])}" if action['basis'] else '') if x), size=10.4, gap=11)
    else:
        doc.para('No actions are recommended yet. We suggest only what the evidence supports.')
    if d['investigate']:
        doc.heading('To investigate')
        doc.para('<br/>'.join(_e(line) for line in d['investigate']), size=10.6)

    doc.start('07 / What we take away together', 'Shared conclusions and your feedback.',
              'For the end of the meeting. We would like to leave with one agreed next step, not a list.')
    doc.table(['To agree', 'Notes'], [[f'<b>{t}</b>', ''] for t in (
        f'What we understood correctly about {_e(short)}', 'What needs correcting in the brief or the questions',
        'Which finding deserves further investigation', 'What you would want from a future report', 'One agreed next step, and who owns it')], [.52, .48], 11, 9)
    doc.heading('Four questions about the report itself')
    doc.para('Which finding changes anything for you?<br/>Which questions have we misunderstood or missed?<br/>What would you need before acting on any of this?<br/>Which parts would you share with a colleague or supplier?', size=11.2)
    doc.note(f'Nothing in this document commits {_e(short)} to any work or cost.')

    doc.start('Reference / 08', 'Tests, counting and limits.', 'How the figures in this report were produced.')
    doc.table(['Test', 'Date', 'Size'], [['Current test', _date(d['test_date']), f"{len(asked)} questions, {d['total']} answers"]]
              + ([['Earlier comparison', _date(d['previous_date']), 'The same questions, where they were asked']] if d['previous_date'] else []), [.34, .30, .36], 9.8)
    doc.heading('How the figures were counted')
    doc.para('AI tools used: ' + ', '.join(f"{_e(k)} ({_e(v)})" if v else _e(k) for k, v in d['models'].items()) + '. '
             + f"Each was asked every question {d['repetitions']} times" + (' with live web search on' if d['web_search'] else '')
             + (f", location set to {_e(d['location'])}" if d['location'] else '') + '. A business counts once per answer.', size=10.2)
    doc.para('A source counts once per answer that cites it. Google\'s tool reports only the website name, not the page.', size=10.2)
    doc.heading('Limits')
    doc.para('Small samples from single days, through the AI tools\' developer services, which can differ from the consumer apps (ChatGPT, Gemini). Answers to broad questions change from week to week. The results show what was returned, not why, and do not count customers.', size=10.2)
    return doc.save()


def render_final_beta_pdf(data: Mapping[str, Any]) -> bytes:
    """Two passes: the first counts pages so every footer can say "n / total"."""
    _, pages = _render(data, None)
    pdf, _ = _render(data, pages)
    return pdf
