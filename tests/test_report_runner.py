"""The report runner: brief checks, the paid-test plan and its approval gate, and the run sequence.

No database and no AI tool is used: every write and paid call is a recorded fake.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src import report_runner as runner
from src import run_report

REPO = Path(__file__).resolve().parents[1]
EXAMPLE = REPO / "docs" / "examples" / "report-brief.example.toml"
KEYS = {"api_keys": {"OpenAI": "k1", "Claude": "k2", "Gemini": "k3"}, "models": dict(runner.DEFAULT_MODELS)}
BUSINESS = {"google_place_id": "PLACE1", "business_name": "Example Dental Studio", "primary_group": "dental_care",
            "city": "Hove"}


def saved_revision(**overrides):
    row = {
        "id": "rev-uuid-1",
        "revision": 4,
        "revision_reason": "Owner brief submitted",
        "created_by": "report_runner",
        "target_google_place_id": "PLACE1",
        "target_business_name": "Example Dental Studio",
        "known_for": "Calm private dentistry for nervous patients",
        "desired_searches": ["Dentist in Hove for nervous patients?", "Implants in Hove?"],
        "owner_competitors": [],
        "owner_context": {"priority_services": ["Nervous patients"], "service_areas": ["Hove, East Sussex, UK"]},
        "benchmark_run_id": None,
        "reviewer_decisions": {},
        "reviewer_decisions_complete": False,
        "website_evidence_state": "not_checked",
        "review_evidence_state": "not_checked",
    }
    row.update(overrides)
    return row


class FakeDeps:
    def __init__(self, final_status="completed", attached_status="completed", search_version=3):
        self.calls = []
        self.final_status = final_status
        self.attached_status = attached_status
        self.deps = runner.RunDeps(
            create_visibility_run=self._create_run,
            create_visibility_queries=self._create_queries,
            execute_calls=self._execute,
            finalise_run_from_results=self._finalise,
            attach_benchmark_revision=self._attach,
            get_visibility_run=lambda run_id: {"id": run_id, "status": self.attached_status},
            search_version=search_version,
        )

    def _create_run(self, **kwargs):
        self.calls.append(("create_run", kwargs))
        return "RUN1"

    def _create_queries(self, **kwargs):
        self.calls.append(("create_queries", kwargs))
        return [{"query_id": f"q{i}-{r}", "prompt": p["prompt"]}
                for i, p in enumerate(kwargs["prompts"]) for r in range(kwargs["repetitions"])]

    def _execute(self, **kwargs):
        self.calls.append(("execute", kwargs))

    def _finalise(self, **kwargs):
        self.calls.append(("finalise", kwargs))
        return self.final_status

    def _attach(self, **kwargs):
        self.calls.append(("attach", kwargs))
        return {}


class PromptRecordsTests(unittest.TestCase):
    def test_matches_the_page_question_table_shape(self):
        rows = [
            {"include": True, "intent": "Owner priority", "question": "  Best dentist in Hove? ",
             "report_intent": "discovery", "report_importance": "Not rated", "report_effort": "Not rated"},
            {"question": "Implants in Hove?", "report_intent": "comparison", "report_importance": "4"},
            {"question": "   "},
        ]
        self.assertEqual(
            runner.prompt_records(rows),
            [
                {"category": "Owner priority", "source": "owner_brief", "prompt": "Best dentist in Hove?",
                 "report_intent": "discovery", "report_importance": "Not rated", "report_effort": "Not rated"},
                {"category": "Owner priority", "source": "owner_brief", "prompt": "Implants in Hove?",
                 "report_intent": "comparison", "report_importance": "4", "report_effort": None},
            ],
        )

    def test_call_plan_is_each_query_on_each_tool_in_order(self):
        plan = runner.build_call_plan([{"q": 1}, {"q": 2}], ["OpenAI", "Claude"])
        self.assertEqual([(c["q"], c["provider"]) for c in plan],
                         [(1, "OpenAI"), (1, "Claude"), (2, "OpenAI"), (2, "Claude")])

    def test_the_page_uses_the_shared_helpers(self):
        page = (REPO / "app" / "pages" / "10_AI_Report_Generator.py").read_text()
        self.assertIn("from src.report_runner import DEFAULT_MODELS, MAX_RUN_QUESTIONS, build_call_plan, prompt_records", page)
        self.assertIn("build_call_plan(query_records, available_providers)", page)
        self.assertNotIn('"source": "owner_brief",', page)
        self.assertIn("load_business_records()", page)


class BriefTests(unittest.TestCase):
    def test_example_brief_parses(self):
        brief = runner.load_brief(EXAMPLE)
        self.assertEqual(brief.business_name, "Example Dental Studio")
        self.assertEqual(len(brief.questions), 3)
        self.assertEqual(brief.questions[1]["report_intent"], "comparison")
        self.assertEqual(brief.questions[2]["report_importance"], "4")
        args = brief.save_arguments()
        self.assertEqual(args["service_areas"], "Hove, East Sussex, UK")
        self.assertEqual(args["desired_searches"].count("\n"), 2)

    def _brief(self, **overrides):
        data = {"known_for": "Calm private dentistry in Hove", "business": {"google_place_id": "P1", "name": "X"},
                "questions": ["Dentist in Hove?"]}
        data.update(overrides)
        return data

    def test_problems_are_named(self):
        cases = {
            "google_place_id": self._brief(business={"name": "X"}),
            "discovery": self._brief(business={"google_place_id": "discovery:abc", "name": "X"}),
            "at least one": self._brief(questions=[]),
            "listed twice": self._brief(questions=["Dentist in Hove?", "dentist in hove?"]),
            "search_intent": self._brief(questions=[{"question": "Q?", "search_intent": "nearby"}]),
            "importance": self._brief(questions=[{"question": "Q?", "importance": "9"}]),
            "known for": self._brief(known_for="Dentist"),
            "http": self._brief(business={"google_place_id": "P1", "name": "X", "website": "www.example.co.uk"}),
            "at most 20": self._brief(questions=[f"Question {i}?" for i in range(21)]),
        }
        for expected, data in cases.items():
            with self.subTest(expected):
                with self.assertRaises(runner.BriefError) as caught:
                    runner.parse_brief(data)
                self.assertIn(expected, str(caught.exception))

    def test_changes_and_work_at_risk(self):
        brief = runner.parse_brief(self._brief())
        self.assertEqual(runner.brief_changes(brief, None), ["first brief for this business"])
        saved = saved_revision(known_for="Calm private dentistry in Hove", desired_searches=["Dentist in Hove?"],
                               owner_context={}, manual_website_url=None)
        self.assertEqual(runner.brief_changes(brief, saved), [])
        self.assertEqual(runner.current_work_at_risk(saved), [])
        busy = saved_revision(benchmark_run_id="RUN0")
        self.assertEqual(len(runner.current_work_at_risk(busy)), 1)  # no decisions saved yet
        # Any saved decision counts as work, even a partly completed review.
        busy["reviewer_decisions"] = {"name_links": {}}
        risks = runner.current_work_at_risk(busy)
        self.assertEqual(len(risks), 2)
        self.assertNotIn("review complete", risks[1])
        busy["reviewer_decisions_complete"] = True
        self.assertIn("review complete", runner.current_work_at_risk(busy)[1])


class SettingsTests(unittest.TestCase):
    def test_environment_wins_over_the_secrets_file_and_a_missing_file_is_fine(self):
        with tempfile.TemporaryDirectory() as folder:
            secrets = Path(folder) / "secrets.toml"
            secrets.write_text('OPENAI_API_KEY = "from-file"\nGEMINI_API_KEY = "g"\nGEMINI_MODEL = "gem-x"\n')
            settings = runner.load_settings({"OPENAI_API_KEY": "from-env"}, secrets)
            self.assertEqual(settings["api_keys"], {"OpenAI": "from-env", "Claude": "", "Gemini": "g"})
            self.assertEqual(settings["models"]["Gemini"], "gem-x")
            self.assertEqual(settings["models"]["Claude"], runner.DEFAULT_MODELS["Claude"])
            self.assertEqual(runner.load_settings({}, Path(folder) / "none.toml")["api_keys"]["Claude"], "")


class PlanTests(unittest.TestCase):
    def test_plan_counts_calls_and_shows_no_keys(self):
        plan = runner.plan_run(saved=saved_revision(), business=BUSINESS, settings=KEYS, repeats=3)
        self.assertEqual(plan.call_count, 2 * 3 * 3)
        self.assertEqual(plan.location, "Hove, East Sussex, UK")
        text = runner.describe_plan(plan)
        self.assertIn("Paid API calls: 18", text)
        self.assertIn(plan.approval_code, text)
        for key in KEYS["api_keys"].values():
            self.assertNotIn(f" {key}", text)

    def test_blocked_plans_say_why(self):
        with self.assertRaisesRegex(runner.PlanError, "No brief"):
            runner.plan_run(saved=None, business=BUSINESS, settings=KEYS)
        missing_key = {"api_keys": {**KEYS["api_keys"], "Claude": ""}, "models": KEYS["models"]}
        with self.assertRaisesRegex(runner.PlanError, "Claude"):
            runner.plan_run(saved=saved_revision(), business=BUSINESS, settings=missing_key)
        nowhere = saved_revision(owner_context={})
        with self.assertRaisesRegex(runner.PlanError, "service_areas"):
            runner.plan_run(saved=nowhere, business={**BUSINESS, "city": None}, settings=KEYS)
        # The business's own city is used when the brief names no area, as on the page.
        self.assertEqual(runner.plan_run(saved=nowhere, business=BUSINESS, settings=KEYS).location, "Hove")

    def test_the_approval_code_changes_with_anything_that_is_paid_for(self):
        base = runner.plan_run(saved=saved_revision(), business=BUSINESS, settings=KEYS).approval_code
        self.assertEqual(base, runner.plan_run(saved=saved_revision(), business=BUSINESS, settings=KEYS).approval_code)
        variants = [
            runner.plan_run(saved=saved_revision(), business=BUSINESS, settings=KEYS, repeats=2),
            runner.plan_run(saved=saved_revision(id="rev-uuid-2"), business=BUSINESS, settings=KEYS),
            runner.plan_run(saved=saved_revision(desired_searches=["Dentist in Hove for nervous patients?"]),
                            business=BUSINESS, settings=KEYS),
            runner.plan_run(saved=saved_revision(owner_context={"service_areas": ["Brighton"]}),
                            business=BUSINESS, settings=KEYS),
            runner.plan_run(saved=saved_revision(), business=BUSINESS,
                            settings={**KEYS, "models": {**KEYS["models"], "Claude": "other"}}),
        ]
        for plan in variants:
            self.assertNotEqual(plan.approval_code, base)


class ApprovalAndRunTests(unittest.TestCase):
    def setUp(self):
        self.saved = saved_revision()
        self.plan = runner.plan_run(saved=self.saved, business=BUSINESS, settings=KEYS)

    def test_wrong_code_and_changed_search_code_stop_before_any_call(self):
        fake = FakeDeps()
        with self.assertRaisesRegex(runner.PlanError, "does not match"):
            runner.check_approval(self.plan, "WRONG", again=False, deps=fake.deps)
        with self.assertRaisesRegex(runner.PlanError, "search version"):
            runner.check_approval(self.plan, self.plan.approval_code, again=False, deps=FakeDeps(search_version=4).deps)
        runner.check_approval(self.plan, self.plan.approval_code.lower(), again=False, deps=fake.deps)
        self.assertEqual(fake.calls, [])

    def test_a_completed_attached_test_is_not_paid_for_twice(self):
        attached = runner.plan_run(saved=saved_revision(benchmark_run_id="RUN0"), business=BUSINESS, settings=KEYS)
        with self.assertRaisesRegex(runner.PlanError, "already attached"):
            runner.check_approval(attached, attached.approval_code, again=False, deps=FakeDeps().deps)
        runner.check_approval(attached, attached.approval_code, again=True, deps=FakeDeps().deps)
        # A partial attached test does not block (it cannot be reported as it stands).
        runner.check_approval(attached, attached.approval_code, again=False,
                              deps=FakeDeps(attached_status="partial").deps)

    def test_run_follows_the_page_sequence_and_attaches_only_when_complete(self):
        fake = FakeDeps()
        records = [BUSINESS, {"google_place_id": "P2", "business_name": "Other", "city": "Brighton"}]
        outcome = runner.execute_plan(self.plan, business=BUSINESS, business_records=records, settings=KEYS,
                                      saved=self.saved, deps=fake.deps)
        self.assertEqual([name for name, _ in fake.calls], ["create_run", "create_queries", "execute", "finalise", "attach"])
        create = fake.calls[0][1]
        self.assertEqual(create["target_propositions"], ["Nervous patients"])
        self.assertEqual(create["primary_group"], "dental_care")
        self.assertEqual(create["repeat_count"], 3)
        execute = fake.calls[2][1]
        self.assertEqual(len(execute["call_plan"]), self.plan.call_count)
        self.assertEqual(execute["benchmark_mode"], "search_grounded")
        self.assertEqual(execute["location_context"], "Hove, East Sussex, UK")
        self.assertEqual(execute["known_businesses"][1], {"google_place_id": "P2", "business_name": "Other"})
        self.assertEqual(fake.calls[3][1]["expected_call_count"], self.plan.call_count)
        self.assertEqual(fake.calls[4][1], {"target_google_place_id": "PLACE1", "benchmark_run_id": "RUN1",
                                            "created_by": "report_runner"})
        self.assertTrue(outcome.attached)

        partial = FakeDeps(final_status="partial")
        outcome = runner.execute_plan(self.plan, business=BUSINESS, business_records=records, settings=KEYS,
                                      saved=self.saved, deps=partial.deps)
        self.assertNotIn("attach", [name for name, _ in partial.calls])
        self.assertFalse(outcome.attached)
        self.assertIn("Resume/retry", outcome.message)


class StatusAndCommandLineTests(unittest.TestCase):
    def test_next_step_follows_the_saved_state(self):
        self.assertIn("brief <file> --save", runner.describe_status(None, None))
        self.assertIn("plan <place-id>", runner.describe_status(saved_revision(), None))
        attached = saved_revision(benchmark_run_id="RUN1")
        self.assertIn("AI Visibility page", runner.describe_status(attached, {"status": "partial"}))
        self.assertIn("step 5", runner.describe_status(attached, {"status": "completed"}))
        done = saved_revision(benchmark_run_id="RUN1", reviewer_decisions_complete=True)
        self.assertIn("Final Beta", runner.describe_status(done, {"status": "completed"}))

    def test_run_needs_an_approval_code(self):
        parser = run_report.build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["run", "PLACE1"])
        args = parser.parse_args(["run", "PLACE1", "--approve", "ABCD1234"])
        self.assertEqual((args.repeats, args.again, args.like), (None, False, []))
        args = parser.parse_args(["plan", "PLACE1", "--like", "30f9160b", "--like", "b9ad0c8d"])
        self.assertEqual(args.like, ["30f9160b", "b9ad0c8d"])

    def test_a_bad_brief_stops_with_a_plain_message(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "brief.toml"
            path.write_text('known_for = "Calm private dentistry"\n[business]\nname = "X"\n')
            self.assertEqual(run_report.main(["brief", str(path)]), 2)



def baseline_run(run_id, questions, *, location="Brighton and Hove", repeats=3, day="2026-10-09",
                 status="completed", place="PLACE1", models=None):
    run = {"id": run_id, "target_google_place_id": place, "status": status, "location_context": location,
           "repeat_count": repeats, "started_at": day, "models": models or dict(runner.DEFAULT_MODELS)}
    queries = [
        {"prompt_text": q, "base_prompt_order": i, "repeat_index": r, "prompt_order": i * repeats + r,
         "prompt_category": "Owner priority", "report_intent": "discovery", "report_importance": None,
         "report_effort": None}
        for i, q in enumerate(questions) for r in range(repeats)
    ]
    return run, list(reversed(queries)), "core"


class RetestTests(unittest.TestCase):
    """A re-test repeats earlier tests exactly, and says what is no longer like-for-like."""

    def setUp(self):
        self.first = baseline_run("30f9160b-aaaa", ["Recommend places in Brighton for coworking.",
                                                   "Recommend places in Brighton for meeting rooms."])
        self.second = baseline_run("b9ad0c8d-bbbb", ["Event spaces with childcare",
                                                     "Recommend places in Brighton for coworking."])
        # The saved brief now lists the areas differently: the re-test must not use it.
        self.saved = saved_revision(owner_context={"service_areas": ["Brighton", "Hove"]})

    def test_questions_location_and_repeats_come_from_the_baseline(self):
        baseline = runner.baseline_from_runs("PLACE1", [self.first, self.second])
        self.assertEqual([r["question"] for r in baseline.rows], [
            "Recommend places in Brighton for coworking.", "Recommend places in Brighton for meeting rooms.",
            "Event spaces with childcare"])
        self.assertTrue(any("asked in both" in n for n in baseline.notes))
        plan = runner.plan_run(saved=self.saved, business=BUSINESS, settings=KEYS, baseline=baseline)
        self.assertEqual(plan.location, "Brighton and Hove")
        self.assertEqual(plan.repeats, 3)
        self.assertEqual(len(plan.prompts), 3)
        self.assertEqual(plan.baseline_run_ids, ("30f9160b-aaaa", "b9ad0c8d-bbbb"))
        text = runner.describe_plan(plan)
        self.assertIn("Re-test of: 30f9160b, b9ad0c8d", text)
        self.assertIn("Read before approving:", text)

    def test_the_approval_code_names_the_baseline(self):
        one = runner.baseline_from_runs("PLACE1", [self.first])
        plan = runner.plan_run(saved=self.saved, business=BUSINESS, settings=KEYS, baseline=one)
        same_questions = runner.plan_run(saved=self.saved, business=BUSINESS, settings=KEYS,
                                         rows=one.rows, repeats=3)
        self.assertNotEqual(plan.approval_code, same_questions.approval_code)

    def test_what_is_not_like_for_like_is_listed(self):
        baseline = runner.baseline_from_runs("PLACE1", [self.second])
        changed = {**KEYS, "models": {**KEYS["models"], "Claude": "claude-newer"}}
        plan = runner.plan_run(saved=self.saved, business=BUSINESS, settings=changed, baseline=baseline, repeats=2)
        warnings = " ".join(plan.warnings)
        self.assertIn("Claude now uses claude-newer", warnings)
        self.assertIn("asked 2 times; the baseline asked it 3 times", warnings)
        self.assertIn("“Event spaces with childcare” names no place", warnings)
        self.assertIn("not comparable", warnings)
        self.assertIn("differ from the baseline", warnings)
        self.assertIn("Final Beta", warnings)
        self.assertNotIn("Recommend places in Brighton for coworking.” names no place", warnings)
        later = runner.baseline_from_runs("PLACE1", [baseline_run("c1", ["Event spaces with childcare"], day="2026-11-17")])
        later_plan = runner.plan_run(saved=self.saved, business=BUSINESS, settings=KEYS, baseline=later)
        self.assertNotIn("not comparable", " ".join(later_plan.warnings))

    def test_baselines_that_cannot_be_repeated_say_why(self):
        cases = {
            "different business": [baseline_run("x1", ["Q in Brighton?"], place="OTHER")],
            "not completed": [baseline_run("x2", ["Q in Brighton?"], status="partial")],
            "different customer locations": [self.first, baseline_run("x3", ["Q in Hove?"], location="Brighton, Hove")],
            "different numbers of repeats": [self.first, baseline_run("x4", ["Q in Hove?"], repeats=2)],
            "at most 20": [baseline_run("x5", [f"Question {i} in Brighton?" for i in range(21)])],
            "not found": [({}, [], None)],
        }
        for expected, runs in cases.items():
            with self.subTest(expected):
                with self.assertRaisesRegex(runner.PlanError, expected):
                    runner.baseline_from_runs("PLACE1", runs)
        run, queries, _ = self.first
        with self.assertRaisesRegex(runner.PlanError, "free_check run"):
            runner.baseline_from_runs("PLACE1", [(run, queries, "free_check")])

    def test_place_words(self):
        self.assertTrue(runner.names_a_place("Best nurseries in Brighton & Hove", "Brighton, Hove"))
        self.assertFalse(runner.names_a_place("Recommend places for children's parties", "Brighton, Hove"))
        self.assertFalse(runner.names_a_place("Tiles near me", "Newhaven, East Sussex"))
        self.assertTrue(runner.names_a_place("Marble tiles in Newhaven", "Newhaven, East Sussex"))

if __name__ == "__main__":
    unittest.main()
