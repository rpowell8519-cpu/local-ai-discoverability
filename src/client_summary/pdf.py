"""Six-page, in-memory PDF renderer. All data-derived markup is escaped.

Vendored from the streamlit-client-report package supplied on 2026-09-21."""
from io import BytesIO
from xml.sax.saxutils import escape
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.colors import HexColor, white
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph
from .model import validate_report, metrics, ReportValidationError

NAVY, BLUE, TEAL, LIGHT, GREY = map(HexColor, ['#14253B','#345BEB','#008C86','#EDF2F7','#526171'])
W, H = 595.28, 841.89


def safe(value):
    # Normalize unsupported dash glyphs before inserting text into Paragraph markup.
    return escape(str(value)).replace('\u2011', '-').replace('\u2013', '-').replace('\u2014', '-')


class ReportLayoutError(ReportValidationError):
    pass


class Page:
    def __init__(self, canvas, data):
        self.c, self.data = canvas, data
        self.y, self.number = 0, 0
        self.styles = {
            'body': ParagraphStyle('body', fontName='Helvetica', fontSize=11, leading=15.5, textColor=NAVY),
            'small': ParagraphStyle('small', fontName='Helvetica', fontSize=9, leading=12, textColor=GREY),
            'heading': ParagraphStyle('heading', fontName='Helvetica-Bold', fontSize=15, leading=19, textColor=NAVY),
            'title': ParagraphStyle('title', fontName='Helvetica-Bold', fontSize=25, leading=29, textColor=NAVY),
        }

    def reserve(self, height):
        if self.y - height < 65:
            raise ReportLayoutError(f'Page {self.number} is too long. Shorten the supplied text; export stopped to avoid clipping or an unreadable font size.')

    def p(self, text, kind='body', gap=10):
        paragraph = Paragraph(text, self.styles[kind])
        _, height = paragraph.wrap(507, 800)
        self.reserve(height + gap)
        paragraph.drawOn(self.c, 44, self.y-height)
        self.y -= height + gap

    def heading(self, title):
        self.p(safe(title), 'heading')

    def start(self, number, title, subtitle):
        self.number = number
        c = self.c
        c.setFillColor(BLUE); c.rect(0,H-8,W,8,stroke=0,fill=1)
        c.setFont('Helvetica',8); c.setFillColor(GREY)
        c.drawString(44,H-35,'AI VISIBILITY | CLIENT SUMMARY')
        c.drawRightString(W-44,H-35,self.data['audit_date'])
        self.y = H-67
        self.p(safe(title),'title',12)
        self.p(safe(subtitle),'body',20)
        c.setStrokeColor(LIGHT); c.line(44,49,W-44,49)
        c.setFont('Helvetica',8); c.drawString(44,34,'A snapshot of the selected questions and test settings')
        c.drawRightString(W-44,34,f'{number} / 6')

    def end(self):
        self.c.showPage()

    def bar(self, name, value, total, target=False, suffix=None):
        self.reserve(45)
        style = self.styles['body']
        paragraph = Paragraph(safe(name),style)
        _,height = paragraph.wrap(408,100)
        if height > 31:
            raise ReportLayoutError('Chart label is too long; provide a shorter label.')
        paragraph.drawOn(self.c,44,self.y-height)
        self.c.setFont('Helvetica-Bold',11); self.c.setFillColor(NAVY)
        self.c.drawRightString(551,self.y-12,suffix or f'{value} of {total}')
        self.c.setFillColor(LIGHT); self.c.roundRect(44,self.y-35,507,7,3,stroke=0,fill=1)
        if value:
            self.c.setFillColor(TEAL if target else BLUE)
            self.c.rect(44,self.y-35,507*value/total,7,stroke=0,fill=1)
        self.y -= max(47,height+23)


def render_pdf(payload):
    """Return PDF bytes after validation; never write client data to disk."""
    d = validate_report(payload)
    m = metrics(d)
    out = BytesIO(); canvas = Canvas(out,pagesize=(W,H))
    canvas.setTitle(f"{d['business_name']} - AI visibility")
    canvas.setAuthor('AI visibility report')
    page = Page(canvas,d)
    total, appearances = m['complete'], m['appearances']
    qs = {q['id']:q for q in d['questions']}
    qsorted = m['questions']
    best, weakest = qsorted[0], qsorted[-1]
    same = best['appearances'] == weakest['appearances']
    appearance_text = f'{appearances} of {total} test answers included your business ({m["percentage"]:.0f}%).'

    page.start(1,'How often does AI include your business?',f"{d['business_name']} | {d['location']}")
    page.heading('Your result at a glance')
    page.p(f'<b>{safe(appearance_text)}</b>')
    page.p('AI visibility means whether your business appears when someone asks an AI assistant for a relevant recommendation. Inclusion is an opportunity to be considered; it is not a visit or a booking.')
    page.heading('What stands out')
    if same:
        page.p(f'All tested questions recorded the same number of appearances: <b>{best["appearances"]} of {best["complete"]}</b> each. There is no strongest or weakest topic within this test.')
    else:
        page.p(f'The highest result was <b>{safe(best["label"])}</b>, at <b>{best["appearances"]} of {best["complete"]}</b> answers. The lowest was <b>{safe(weakest["label"])}</b>, at <b>{weakest["appearances"]} of {weakest["complete"]}</b>. Other topics may tie with these results; all are shown on page 3.')
    page.heading('Where to start')
    first = d['actions'][0]
    page.p(f'<b>{safe(first["title"])}</b>')
    page.p(safe(first['task']))
    page.p('The action order reflects the supplied business priorities. A lower appearance count alone does not establish commercial value or a website defect.')
    page.heading('Read this as a baseline')
    page.p('These figures apply to the selected questions and test date. They do not represent all customer searches, market share or lost revenue. The test does not establish what caused an AI assistant to include a business.')
    page.p('Source: '+safe(d['source_note']),'small')
    page.end()

    page.start(2,'What we tested','Customer questions, repeated across the selected AI providers.')
    page.heading('A question from your test')
    page.p('“'+safe(qs[first['question_id']]['text'])+'”')
    page.p('An answer can contain several venues or businesses. We count your business at most once in each answer, even if its name appears more than once. This measures inclusion, not an endorsement or a first-place ranking.')
    page.heading('How the test works')
    n, pcount, reps = len(qs),len(d['providers']),d['repetitions']
    page.p(f'<b>{n} questions x {pcount} providers x {reps} repetitions = {total} complete test answers.</b> Each question has {best["complete"]} answers.')
    names = ', '.join(p['name'] for p in d['providers'])
    page.p('Providers: '+safe(names)+'. '+('The supplied audit records web search as enabled.' if d['web_search_enabled'] else 'The supplied audit records web search as disabled.'))
    page.p('The questions were reviewed by the owner.' if d['owner_reviewed_questions'] else 'Owner review of these questions has not been confirmed.')
    page.heading('Why repeat a question?')
    page.p('Answers can vary between runs. Repeating each question shows how consistently you appeared within this small test. It does not establish a statistically reliable forecast of future answers.')
    page.heading('What the figures mean')
    page.p(f'For example, “2 of {best["complete"]}” would mean two test answers included the business. It would not mean two customers visited or booked.' if best['complete']>=2 else '“1 of 1” means one test answer included the business. It does not mean one customer visited or booked.')
    page.p('These questions do not measure real customer search volumes. Tests through automated provider connections may differ from public apps. Changes in wording, location settings, personalisation or models can affect results.','small')
    page.end()

    page.start(3,'Where you appeared','Results by customer need. Topic labels are shortened; exact questions remain in the audit data.')
    for q in qsorted:
        page.bar(q['label'],q['appearances'],q['complete'],target=q['appearances']==best['appearances'])
    page.y-=8
    page.heading('How to use this page')
    page.p('Use the results to decide which commercially important topics deserve investigation. Confirm the facts before treating low visibility as evidence that information is missing.')
    page.p('One additional appearance changes a topic result by one answer. Treat small movements cautiously and compare repeated tests using the same questions and settings.','small')
    page.end()

    page.start(4,'Who else appeared?','Appearance counts for the comparison businesses supplied for this report.')
    for b in m['businesses']:
        page.bar(b['name'],b['appearances'],total,target=b['id']==d['target_id'])
    page.p('Each figure is out of all complete answers. An answer can name several businesses, so counts across businesses can exceed the number of answers. This selected comparison is not a market ranking.','small')
    page.heading('Your results by provider')
    page.p(' | '.join(f'<b>{safe(p["name"])}:</b> {p["appearances"]} of {p["complete"]}' for p in d['providers']))
    if d.get('evidence'):
        page.heading('Supporting observations')
        for e in d['evidence']:
            page.p('<b>'+safe(e['id'])+':</b> '+safe(e['observation'])+'<br/><b>Source:</b> '+safe(e['source']),'small')
        page.p('These observations do not establish why an AI provider included a business.','small')
    else:
        page.heading('What still needs checking')
        page.p('No sourced website or review observations were supplied for this summary. Compare relevant pages and customer information before claiming that a competitor has stronger evidence. Missing evidence is not poor performance.','small')
    page.end()

    page.start(5,'Your three practical priorities','Actions linked to the measured questions, with clear responsibility and completion criteria.')
    for i,a in enumerate(d['actions'],1):
        q=qs[a['question_id']]
        page.heading(f'{i}. {a["title"]}')
        page.p(f'<b>Test result:</b> {safe(q["label"])}: {q["appearances"]} of {q["complete"]}.','small',5)
        if a['status']=='suggested_check':
            page.p('<b>Suggested check:</b> '+safe(a['task']),gap=6)
        else:
            page.p('<b>Action for a documented gap:</b> '+safe(a['task']),gap=6)
            page.p('<b>Evidence:</b> '+safe(', '.join(a['evidence_ids']))+' (observations on page 4).','small',5)
        page.p('<b>Suggested owner:</b> '+safe(a['owner'])+'<br/><b>Done when:</b> '+safe(a['done_when']),'small',16)
    page.p('Suggested checks are not confirmed defects. Improving customer information may help people decide; no change in AI appearances is guaranteed.','small')
    page.end()

    page.start(6,'Delivery and follow-up','Agree the priorities, improve verified gaps, then repeat a comparable test.')
    page.heading('A suggested sequence')
    page.p('<b>Weeks 1-2:</b> agree the business priorities, check the existing information and assign tasks.<br/><b>Weeks 3-6:</b> publish verified improvements and test the customer journey.<br/><b>8-12 weeks after completion:</b> repeat the original test. This is a suggested review interval, not a promised time to improvement.')
    page.heading('Measure three things separately')
    page.p(f'<b>Delivery:</b> confirm the agreed work is complete and accurate.<br/><b>Visibility:</b> compare against {appearances} of {total}, then inspect topic and provider results.<br/><b>Business outcomes:</b> monitor enquiries and bookings where possible; do not attribute a change to AI without supporting evidence.')
    page.heading('Evidence and limitations')
    basis = ('Counts were calculated from the supplied saved response records.' if d['evidence_basis']=='saved_response_records' else 'Counts were supplied as source-report aggregates. They have been checked for arithmetic consistency, not independently verified against saved answers.')
    page.p(safe(basis),'small')
    for item in d.get('limitations',[]):
        page.p(safe(item),'small',7)
    page.p('The report renderer does not independently verify source material or the cause of a result. Retain the exact questions and evidence with the full audit. Before comparing a later run, record changes to questions, business identity matching, models and settings.','small')
    page.p('<b>Models recorded:</b> '+safe('; '.join(f'{p["name"]}: {p["model"]}' for p in d['providers'])),'small')
    page.p('<b>Source:</b> '+safe(d['source_note']),'small')
    page.end()
    canvas.save()
    return out.getvalue()
