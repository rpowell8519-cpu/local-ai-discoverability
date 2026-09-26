from pathlib import Path
from PIL import Image, ImageDraw
from report_fonts import report_font
import argparse
import json
import shutil
import subprocess
import tempfile

parser = argparse.ArgumentParser(description='Generate the Found in Brighton AI report template.')
parser.add_argument('--output-dir', type=Path, default=Path('generated-report'))
parser.add_argument('--config', type=Path, help='Optional JSON file of placeholder replacements.')
parser.add_argument('--pdf', action='store_true', help='Also export PDF using LibreOffice.')
parser.add_argument('--libreoffice', help='Path to the LibreOffice executable.')
parser.add_argument('--font', type=Path, help='Optional regular TrueType font.')
parser.add_argument('--bold-font', type=Path, help='Optional bold TrueType font.')
args = parser.parse_args()
OUTPUT = args.output_dir.resolve()
OUTPUT.mkdir(parents=True, exist_ok=True)
ROOT = OUTPUT / 'assets'
ROOT.mkdir(parents=True, exist_ok=True)
DOCX_PATH = OUTPUT / 'Found_in_Brighton_AI_Client_Report.docx'
BASE_SOURCE = Path(__file__).resolve().with_name('report_content.py')
REPLACEMENTS = json.loads(args.config.read_text(encoding='utf-8')) if args.config else {}
if not isinstance(REPLACEMENTS, dict) or not all(isinstance(k,str) and isinstance(v,str) for k,v in REPLACEMENTS.items()):
    raise ValueError('Config must be a JSON object mapping placeholder strings to replacement strings.')
NAVY = '#173B48'
TEAL = '#168C92'
MINT = '#D6EBE7'
INK = '#172B33'
GREY = '#617079'
CORAL = '#CD7052'
PAPER = '#F1F5F4'

def font(size, bold=False):
    custom = args.bold_font if bold else args.font
    return report_font(size, bold, str(custom) if custom else None)

def canvas(name, height):
    im=Image.new('RGB',(1800,height),'white')
    return im, ImageDraw.Draw(im)

def save(im,name):
    im.save(ROOT / (name+'.png'),dpi=(300,300))

im,d=canvas('cover',590)
d.rectangle((0,0,1800,590),fill=NAVY)
for y in range(200,1200,95):
    d.arc((700,y-750,2400,y+80),20,170,fill='#2D6170',width=3)
d.ellipse((1390,85,1605,300),fill=CORAL)
d.arc((1060,120,1660,720),180,355,fill=MINT,width=19)
d.text((75,100),'Visibility.',font=font(88,True),fill='white')
d.text((75,208),'Understanding.',font=font(88,True),fill='white')
d.text((75,316),'Opportunity.',font=font(88,True),fill='white')
d.text((80,490),'CHATGPT  /  CLAUDE  /  GEMINI',font=font(30),fill=MINT)
save(im,'cover')

im,d=canvas('kpis',245)
for i,(v,l,c) in enumerate([('45%','Mention rate','+5 pp'),('30%','Recommendation rate','+5 pp'),('20%','Share of voice','+2 pp')]):
    x=i*610
    d.text((x+5,5),v,font=font(100,True),fill=NAVY)
    d.text((x+5,125),l,font=font(32),fill=INK)
    d.text((x+5,180),c+' vs previous period',font=font(27),fill=TEAL)
save(im,'kpis')

im,d=canvas('platform',560)
start,end=370,1560
for pct in [0,25,50,75,100]:
    x=start+(end-start)*pct/100
    d.line((x,65,x,480),fill='#E1E7E7',width=2)
    d.text((x,493),str(pct)+'%',font=font(26),fill=GREY,anchor='mm')
for i,(name,m,r) in enumerate([('ChatGPT',60,40),('Claude',45,30),('Gemini',30,20)]):
    y=82+i*132
    d.text((0,y+20),name,font=font(40,True),fill=INK)
    for dy,val,col in [(0,m,NAVY),(48,r,TEAL)]:
        xx=start+(end-start)*val/100
        d.rounded_rectangle((start,y+dy,xx,y+dy+32),radius=5,fill=col)
        d.text((xx+20,y+dy-2),str(val)+'%',font=font(30,True),fill=col)
d.rectangle((370,10,396,36),fill=NAVY);d.text((412,6),'Mention rate',font=font(28),fill=INK)
d.rectangle((760,10,786,36),fill=TEAL);d.text((802,6),'Recommendation rate',font=font(28),fill=INK)
save(im,'platform')

im,d=canvas('voice',300)
vals=[20,26.7,22.2,17.8,13.3]; colors=[TEAL,NAVY,'#58818D','#9BB7BC','#DCE6E7']
x=0
for i,(v,col) in enumerate(zip(vals,colors)):
    w=1800*v/100
    d.rectangle((x,20,x+w-4,118),fill=col)
    d.text((x+w/2,69),str(v)+'%',font=font(35,True),fill='white' if i<3 else INK,anchor='mm')
    x+=w
for i,(name,col) in enumerate(zip(['Client','Competitor A','Competitor B','Competitor C','Competitor D'],colors)):
    x=(i%3)*595;y=155+(i//3)*65
    d.rectangle((x,y,x+28,y+28),fill=col);d.text((x+43,y-2),name,font=font(29),fill=INK)
save(im,'voice')

im,d=canvas('trend',540)
left,right,top,bottom=130,1680,55,415
for pct in [0,10,20,30,40,50]:
    y=bottom-(bottom-top)*pct/50
    d.line((left,y,right,y),fill='#E1E7E7',width=2)
    d.text((95,y),str(pct)+'%',font=font(26),fill=GREY,anchor='rm')
for i,label in enumerate(['Period 1','Period 2','Current']):
    d.text((left+i*(right-left)/2,bottom+40),label,font=font(29),fill=INK,anchor='mm')
for label,values,col in [('Mention',[35,40,45],NAVY),('Recommendation',[20,25,30],TEAL),('Owned citation',[10,15,20],CORAL)]:
    pts=[(left+i*(right-left)/2,bottom-(bottom-top)*v/50) for i,v in enumerate(values)]
    d.line(pts,fill=col,width=7)
    for (x,y),val in zip(pts,values):
        d.ellipse((x-9,y-9,x+9,y+9),fill=col)
        d.text((x,y-27),str(val)+'%',font=font(28,True),fill=col,anchor='mm')
for i,(label,col) in enumerate([('Mention',NAVY),('Recommendation',TEAL),('Owned citation',CORAL)]):
    x=130+i*530;d.rectangle((x,502,x+28,526),fill=col);d.text((x+45,497),label,font=font(28),fill=INK)
save(im,'trend')

src=BASE_SOURCE.read_text(encoding='utf-8')
src=src.replace("s.top_margin=Inches(.75); s.bottom_margin=Inches(.65)","s.top_margin=Inches(.78); s.bottom_margin=Inches(.64)")
src=src.replace("('Normal',10.5),('Title',36),('Heading 1',25),('Heading 2',14)","('Normal',11),('Title',44),('Heading 1',29),('Heading 2',15)")
src=src.replace("line_spacing=1.13","line_spacing=1.14")
src=src.replace("space_after=Pt(9)","space_after=Pt(10)")
src=src.replace("s.header_distance=Inches(.3); s.footer_distance=Inches(.3)","s.header_distance=Inches(.31); s.footer_distance=Inches(.3); s.different_first_page_header_footer=True")
src=src.replace("f.text='CLIENT REPORT TEMPLATE  •  ILLUSTRATIVE PLACEHOLDERS'","f.text='FOUND IN BRIGHTON AI    /    ILLUSTRATIVE TEMPLATE'")
src=src.replace("f.add_run(' '*7)","f.add_run(' '*14)")
src=src.replace("p(f'{n:02d}   /   FOUND IN BRIGHTON AI').runs[0].font.size=Pt(9)","q=p(f'{n:02d}   /   '+('PERFORMANCE' if n<7 else 'EVIDENCE AND OPPORTUNITY' if n<12 else 'ACTION PLAN' if n<14 else 'MEASUREMENT NOTES')); q.runs[0].font.size=Pt(9); q.runs[0].font.color.rgb=RGBColor.from_string('168C92'); q.runs[0].bold=True")
src=src.replace("z.set(qn('w:w'),'95')","z.set(qn('w:w'),'120')")
src=src.replace("r.font.size=Pt(9);r.bold=ri==0","r.font.size=Pt(10);r.bold=ri==0")
src=src.replace("if ci>0:para.alignment=WD_ALIGN_PARAGRAPH.CENTER", "if ci>0 and len(c.text)<20:para.alignment=WD_ALIGN_PARAGRAPH.CENTER")
src=src.replace("p('').paragraph_format.space_after=Pt(1)","q=p(''); q.paragraph_format.space_after=Pt(0); q.paragraph_format.space_before=Pt(0); q.paragraph_format.line_spacing=Pt(5); q.paragraph_format.keep_with_next=True")

start=src.index("page(1,")
end=src.index("page(2,")
cover="""
def picture(name):
 q=D.add_paragraph(); q.paragraph_format.space_after=Pt(9)
 q.add_run().add_picture(str(ROOT / (name+'.png')),width=Inches(6.77))
 return q

q=p('FOUND IN\\nBRIGHTON AI');q.paragraph_format.space_after=Pt(32)
for r in q.runs:r.font.size=Pt(17);r.bold=True
D.add_heading('AI visibility\\nreport',0)
p('Generative Search Optimisation for local businesses')
q=p('[CLIENT NAME]');q.paragraph_format.space_before=Pt(14)
q.runs[0].font.size=Pt(20);q.runs[0].bold=True
p('[PRIMARY MARKET]  /  [WEBSITE]\\nReporting period  [MONTH YEAR]')
picture('cover')
p('Your performance across ChatGPT, Claude and Gemini.\\nThe evidence behind it. The actions to take next.')
note('ILLUSTRATIVE TEMPLATE. All sample figures are placeholders, not client results. Replace sample data and bracketed fields before sharing a completed report.')
"""
src=src[:start]+cover+src[end:]
needle="table(['Measure','Current','Previous','Change'],["
src=src.replace(needle,"picture('kpis')\n"+needle)
src=src.replace("h('What this means for your business')\np('Discovery  [Where customers are likely to encounter the business in the tested panel.]\\nConsideration  [Whether the answer presents the business as a suitable choice.]\\nAction  [The highest priority improvement, linked to evidence and an owner.]')\nh('Optional agency index')\np('[XX/100 or Not calculated]. A summary of eight published components, not an official platform score. Show only when every component has a documented calculation and the same method is used across periods. See page 14.')", "h('The decision this month')\np('[Summarise the most valuable opportunity and the action to approve. Include the owner and intended customer benefit.]')\nnote('Optional agency index: [XX/100 or Not calculated]. See the method and weights on page 14.')")
# Replace the dense platform summary with an immediately readable comparison.
start=src.index("table(['Illustrative results'")
end=src.index("h('Interpretation and next test')",start)
src=src[:start]+"""picture('platform')
note('Illustrative comparison. Same panel; 100 valid unbranded responses per platform.')
table(['Measure','ChatGPT','Claude','Gemini'],[
['First recommendation','15%','10%','5%'],['Top 3 recommendation','32%','24%','16%'],['Owned site citation','30%','20%','10%'],['Average mention position','[X.X]','[X.X]','[X.X]'],['Share of voice','[X%]','[X%]','[X%]'],['Recommendation consistency','[X%]','[X%]','[X%]']],[2.8,1.32,1.32,1.33])
"""+src[end:]
src=src.replace("table(['Business','Mention rate'", "picture('voice')\ntable(['Business','Mention rate'")
src=src.replace("h('What to learn from the comparison')\np('[Competitor] is recommended more often for [topic]. The observed answers cite [source] and associate that business with [attribute]. Validate whether the client has equivalent evidence before proposing a new page or third party listing.')", "")
start=src.index("table(['Illustrative trend'")
end=src.index("h('Delivery and observed outcomes')",start)
src=src[:start]+"""picture('trend')
note('Illustrative trend; the same prompt panel across equal reporting periods. Share of voice: 16% → 18% → 20%. Record model or test changes alongside the comparison.')
"""+src[end:]
# Shorter headings and language improve the visual rhythm.
src=src.replace("'Customer questions and topic coverage'","'What customers ask'")
src=src.replace("'Citations and owned website sources'","'The sources behind answers'")
src=src.replace("'Third party opportunities and authority'","'Build your wider authority'")
src=src.replace("'Priorities and the 90 day roadmap'","'Your next 90 days'")
src=src.replace("'Methodology and metric definitions'","'How we measure performance'")
src=src.replace("'Appendix A Prompt evidence'","'Appendix A Prompt records'")
src=src.replace("'Appendix B Source evidence'","'Appendix B Source records'")
src=src.replace("'Days 1 to 30'","'01   Foundation   Days 1 to 30'")
src=src.replace("'Days 31 to 60'","'02   Authority   Days 31 to 60'")
src=src.replace("'Days 61 to 90'","'03   Evaluate   Days 61 to 90'")
src=src.replace("table(['Priority','Action and evidence'", "table(['Rank','Action and evidence'")
src=src.replace("D.save('output/Found_in_Brighton_AI_Report_Template.docx')", "save_report(D)")

def save_report(document):
    paragraphs = list(document.paragraphs)
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                paragraphs.extend(cell.paragraphs)
    for paragraph in paragraphs:
        for run in paragraph.runs:
            updated = run.text
            for original, replacement in REPLACEMENTS.items():
                updated = updated.replace(original, replacement)
            if updated != run.text:
                run.text = updated
    document.save(DOCX_PATH)

exec(compile(src,'report_layout','exec'))
print('Created:', DOCX_PATH)
print('This is an illustrative template. Sample metrics and chart images must be updated together.')
if args.pdf:
    executable = args.libreoffice or shutil.which('soffice') or shutil.which('libreoffice')
    if not executable:
        mac_path = Path('/Applications/LibreOffice.app/Contents/MacOS/soffice')
        if mac_path.exists(): executable = str(mac_path)
    if not executable:
        parser.exit(1, 'Word document created. PDF export requires LibreOffice; install it or pass --libreoffice.\n')
    with tempfile.TemporaryDirectory(prefix='found-brighton-pdf-') as temporary:
        temp = Path(temporary)
        result = subprocess.run([executable, '-env:UserInstallation='+ (temp/'profile').as_uri(), '--headless', '--convert-to', 'pdf', '--outdir', str(temp), str(DOCX_PATH)], capture_output=True, text=True, timeout=120)
        pdf = temp / DOCX_PATH.with_suffix('.pdf').name
        if result.returncode != 0 or not pdf.exists():
            raise RuntimeError('Word document created, but PDF export failed: '+result.stdout+result.stderr)
        target = OUTPUT / pdf.name
        shutil.copy2(pdf, target)
        print('Created:', target)
