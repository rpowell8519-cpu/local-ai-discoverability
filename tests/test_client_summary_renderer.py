import unittest
import json
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from pypdf import PdfReader
from src.client_summary import validate_report, metrics, from_records, render_pdf, ReportValidationError, ReportLayoutError
BASE=Path(__file__).resolve().parent
class ReportTests(unittest.TestCase):
    def setUp(self):
        self.d=json.loads((BASE/'client_summary_example.json').read_text())
    def test_example_math_and_no_mutation(self):
        before=deepcopy(self.d); result=metrics(self.d)
        self.assertEqual((result['appearances'],result['complete']),(22,72))
        self.assertAlmostEqual(result['percentage'],30.5555555556)
        self.assertEqual(before,self.d)
    def test_invalid_counts_and_incomplete_matrix(self):
        for field,value in [('appearances',True),('appearances',-1),('appearances',10),('complete',8)]:
            with self.subTest(field=field,value=value):
                d=deepcopy(self.d);d['questions'][0][field]=value
                with self.assertRaises(ReportValidationError): validate_report(d)
        self.d['providers'][0]['appearances']=12
        with self.assertRaisesRegex(ReportValidationError,'totals'): validate_report(self.d)
    def test_duplicate_identity_and_target_total(self):
        d=deepcopy(self.d);d['businesses'][1]['id']=d['businesses'][0]['id']
        with self.assertRaisesRegex(ReportValidationError,'duplicate'):validate_report(d)
        self.d['businesses'][-1]['appearances']=21
        with self.assertRaisesRegex(ReportValidationError,'Target'):validate_report(self.d)
    def test_verified_gap_needs_reference(self):
        self.d['actions'][0]['status']='verified_gap'
        with self.assertRaisesRegex(ReportValidationError,'requires'):validate_report(self.d)
        self.d['evidence']=[{'id':'e1','observation':'Test observation, not a real audit finding.','source':'Test fixture'}]
        self.d['actions'][0]['evidence_ids']=['e1'];validate_report(self.d)
        self.assertEqual(len(PdfReader(BytesIO(render_pdf(self.d))).pages),8)
    def test_pdf_eight_pages_and_correct_content(self):
        reader=PdfReader(BytesIO(render_pdf(self.d)));self.assertEqual(len(reader.pages),8)
        text='\n'.join(p.extract_text() for p in reader.pages)
        self.assertIn('22 of 72',text);self.assertIn('Check and improve:',text)
        self.assertIn('No sourced website or review observations',text)
    def test_markup_is_literal(self):
        self.d['business_name']='Garden <b>Bar</b> & Rest';self.d['businesses'][-1]['name']=self.d['business_name']
        self.assertIn('Garden <b>Bar</b> & Rest',PdfReader(BytesIO(render_pdf(self.d))).pages[0].extract_text())
    def test_all_zero_does_not_claim_a_strength(self):
        for key in ['questions','providers','businesses']:
            for item in self.d[key]:item['appearances']=0
        text=PdfReader(BytesIO(render_pdf(self.d))).pages[0].extract_text()
        self.assertIn('no strongest or weakest',' '.join(text.split()));self.assertIn('0 of 72',text)
    def test_record_deduplication_and_counts(self):
        records=[]
        for p in self.d['providers']:
            for q in self.d['questions']:
                for r in range(1,4):
                    records.append(dict(response_id=f'{p["id"]}-{q["id"]}-{r}',provider_id=p['id'],question_id=q['id'],repetition=r,status='complete',business_ids=['example-bar','example-bar'] if r==1 else []))
        original=deepcopy(records);result=from_records(self.d,records)
        self.assertEqual(metrics(result)['appearances'],24);self.assertEqual(records,original)
        with self.assertRaises(ReportValidationError):from_records(self.d,records[:-1])
        with self.assertRaisesRegex(ReportValidationError,'Duplicate'):from_records(self.d,records+[records[0]])
        records[0]['status']='failed'
        with self.assertRaisesRegex(ReportValidationError,'Incomplete'):from_records(self.d,records)
    def test_overflow_stops_export(self):
        for a in self.d['actions']:
            a['title']='Long action title ' * 4
            a['task']=('Detailed task description with several words. ' * 9)[:380]
            a['owner']=('Responsible person ' * 5)[:100]
            a['done_when']=('Completion criteria with several words. ' * 6)[:200]
            a['why']=('Because of a long reason. ' * 20)[:260]
        with self.assertRaises(ReportLayoutError):render_pdf(self.d)
    def test_unknown_reference_and_wrong_date(self):
        self.d['actions'][0]['question_id']='missing'
        with self.assertRaises(ReportValidationError):validate_report(self.d)
        self.d=json.loads((BASE/'client_summary_example.json').read_text());self.d['audit_date']='yesterday'
        with self.assertRaises(ReportValidationError):validate_report(self.d)


class RestyledSummaryTests(unittest.TestCase):
    """The draft's wording must stay true whatever the results are."""

    def setUp(self):
        self.d = json.loads((BASE / 'client_summary_example.json').read_text())

    def pages(self, data=None):
        reader = PdfReader(BytesIO(render_pdf(data or self.d)))
        return [' '.join(page.extract_text().split()) for page in reader.pages]

    def make_all(self, value):
        for key in ('questions', 'providers', 'businesses'):
            for item in self.d[key]:
                item['appearances'] = value(item) if callable(value) else value

    def test_all_zero_says_so_and_claims_no_strength(self):
        self.make_all(0)
        first = self.pages()[0]
        self.assertIn('did not appear in any of the 72 test answers', first)
        self.assertIn('no strongest or weakest', first)
        self.assertNotIn('clear strength', ' '.join(self.pages()))

    def test_all_equal_claims_no_strength_or_weakness(self):
        for q in self.d['questions']:
            q['appearances'] = 3
        self.d['providers'][0]['appearances'] = 8
        self.d['providers'][1]['appearances'] = 8
        self.d['providers'][2]['appearances'] = 8
        self.d['businesses'][-1]['appearances'] = 24
        text = ' '.join(self.pages())
        self.assertIn('no strongest or weakest', text)
        self.assertNotIn('clear strength', text)
        self.assertNotIn('Build on', text)

    def test_a_modest_best_result_is_not_called_a_strength(self):
        for q, value in zip(self.d['questions'], [3, 2, 2, 1, 1, 1, 1, 1]):
            q['appearances'] = value
        self.d['providers'] = [{**p, 'appearances': v} for p, v in zip(self.d['providers'], [4, 4, 4])]
        self.d['businesses'][-1]['appearances'] = 12
        first = self.pages()[0]
        self.assertNotIn('clear strength', first)
        self.assertIn('where you appeared most often', first)

    def test_target_in_front_is_not_told_a_competitor_is_ahead(self):
        self.d['businesses'][-1]['appearances'] = 40
        for q, value in zip(self.d['questions'], [8, 6, 6, 5, 5, 4, 3, 3]):
            q['appearances'] = value
        self.d['providers'] = [{**p, 'appearances': v} for p, v in zip(self.d['providers'], [14, 13, 13])]
        text = self.pages()[4]
        self.assertIn('had the most appearances of the businesses shown', text)
        self.assertNotIn('nearest business above', text)

    def test_a_provider_with_no_appearances_is_named(self):
        for q, value in zip(self.d['questions'], [4, 3, 3, 3, 3, 3, 3, 3]):
            q['appearances'] = value
        self.d['providers'] = [{**p, 'appearances': v} for p, v in zip(self.d['providers'], [13, 12, 0])]
        self.d['businesses'][-1]['appearances'] = 25
        self.assertIn('did not appear in any answer from Gemini', self.pages()[5])

    def test_actions_do_not_end_with_doubled_full_stops(self):
        self.assertNotIn('..', self.pages()[6])

    def test_short_name_is_used_in_headlines_and_full_name_in_the_header(self):
        self.d['business_name'] = 'WRAP- Coworking, Meeting Rooms & Offices'
        self.d['short_name'] = 'WRAP'
        self.d['businesses'][-1]['name'] = self.d['business_name']
        first = self.pages()[0]
        self.assertIn('How often does AI recommend WRAP?', first)
        self.assertIn('WRAP- COWORKING, MEETING ROOMS & OFFICES', first)

    def test_long_topic_label_still_fits_the_tiles(self):
        self.d['questions'][0]['label'] = ('A very long customer topic name that goes on ' * 2)[:65].rstrip()
        self.assertEqual(len(self.pages()), 8)

    def test_every_page_carries_the_draft_header_and_footer(self):
        for number, text in enumerate(self.pages(), 1):
            self.assertIn('CLIENT SUMMARY DRAFT | 18 SEPTEMBER 2026', text)
            self.assertIn(f'{number} / 8', text)


class DraftLabelTests(unittest.TestCase):
    def setUp(self):
        self.d = json.loads((BASE / 'client_summary_example.json').read_text())

    def header(self, data):
        reader = PdfReader(BytesIO(render_pdf(data)))
        return [' '.join(page.extract_text().split()) for page in reader.pages]

    def test_a_summary_is_a_draft_unless_it_says_otherwise(self):
        for text in self.header(self.d):
            self.assertIn('CLIENT SUMMARY DRAFT | 18 SEPTEMBER 2026', text)

    def test_the_draft_label_can_be_removed_after_sign_off(self):
        self.d['draft'] = False
        for text in self.header(self.d):
            self.assertIn('CLIENT SUMMARY | 18 SEPTEMBER 2026', text)
            self.assertNotIn('DRAFT', text)

    def test_draft_must_be_a_real_boolean(self):
        self.d['draft'] = 'no'
        with self.assertRaises(ReportValidationError):
            render_pdf(self.d)

    def test_the_file_title_says_draft_too(self):
        self.assertIn('(draft)', PdfReader(BytesIO(render_pdf(self.d))).metadata.title)
        self.d['draft'] = False
        self.assertNotIn('(draft)', PdfReader(BytesIO(render_pdf(self.d))).metadata.title)


class TiedResultTests(unittest.TestCase):
    """A tie must never be described as being ahead."""

    def setUp(self):
        self.d = json.loads((BASE / 'client_summary_example.json').read_text())

    def page_five(self):
        return ' '.join(PdfReader(BytesIO(render_pdf(self.d))).pages[4].extract_text().split())

    def test_a_tie_for_the_lead_is_described_as_level_not_as_the_most(self):
        # Regression: the first WRAP report said "had the most appearances" while level with Plus X at 30.
        self.d['businesses'][-1]['appearances'] = 35   # level with the top competitor, who has 35
        for q, value in zip(self.d['questions'], [9, 8, 6, 4, 3, 2, 2, 1]):
            q['appearances'] = value
        self.d['providers'] = [{**p, 'appearances': v} for p, v in zip(self.d['providers'], [12, 12, 11])]
        self.d['businesses'][-1]['appearances'] = 35
        self.d['businesses'][-1]['appearances'] = sum(q['appearances'] for q in self.d['questions'])
        top = self.d['businesses'][-1]['appearances']
        self.d['businesses'][0]['appearances'] = top
        text = self.page_five()
        self.assertIn('was level with', text)
        self.assertNotIn('had the most appearances', text)

    def test_only_a_clear_lead_is_described_as_the_most(self):
        for q, value in zip(self.d['questions'], [9, 8, 6, 4, 3, 2, 2, 1]):
            q['appearances'] = value
        self.d['providers'] = [{**p, 'appearances': v} for p, v in zip(self.d['providers'], [12, 12, 11])]
        total = sum(q['appearances'] for q in self.d['questions'])
        self.d['businesses'][-1]['appearances'] = total
        for b in self.d['businesses'][:-1]:
            b['appearances'] = total - 5
        self.assertIn('had the most appearances of the businesses shown', self.page_five())
