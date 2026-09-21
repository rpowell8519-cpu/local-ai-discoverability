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
        self.assertEqual(len(PdfReader(BytesIO(render_pdf(self.d))).pages),6)
    def test_pdf_six_pages_and_correct_content(self):
        reader=PdfReader(BytesIO(render_pdf(self.d)));self.assertEqual(len(reader.pages),6)
        text='\n'.join(p.extract_text() for p in reader.pages)
        self.assertIn('22 of 72',text);self.assertIn('Suggested check:',text)
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
        self.d['businesses'] += [{'id': f'extra-{i}', 'name': 'Additional comparison business', 'appearances': 1} for i in range(2)]
        self.d['evidence'] = [{'id': f'e{i}', 'observation': 'W' * 220, 'source': 'W' * 200} for i in range(3)]
        with self.assertRaises(ReportLayoutError):render_pdf(self.d)
    def test_unknown_reference_and_wrong_date(self):
        self.d['actions'][0]['question_id']='missing'
        with self.assertRaises(ReportValidationError):validate_report(self.d)
        self.d=json.loads((BASE/'client_summary_example.json').read_text());self.d['audit_date']='yesterday'
        with self.assertRaises(ReportValidationError):validate_report(self.d)
