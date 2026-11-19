"""Choosing which earlier test(s) Final Beta compares with. Pure checks: no database."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.final_beta_report import choose_earlier_runs

REPO = Path(__file__).resolve().parents[1]


def at(day: str, hour: int = 14) -> datetime:
    return datetime.fromisoformat(f"{day}T{hour:02d}:00:00").replace(tzinfo=timezone.utc)


# As list_earlier_runs returns them for WRAP coworking (newest first).
CANDIDATES = [
    {"id": "b110209d-0000-4000-8000-000000000001", "started_at": at("2026-11-17"), "prompt_count": 3,
     "shared": ["Event spaces with childcare", "Recommend places in Brighton for event spaces."]},
    {"id": "b9ad0c8d-3d78-48f4-8885-89406e295f76", "started_at": at("2026-10-09", 15), "prompt_count": 5,
     "shared": ["Event spaces with childcare", "Flexible working spaces in Brighton"]},
    {"id": "30f9160b-1145-4a41-8d6f-ca156f8f1dac", "started_at": at("2026-10-09", 14), "prompt_count": 8,
     "shared": ["Recommend places in Brighton for event spaces.", "Recommend places in Brighton for coworking."]},
    {"id": "022be437-8d45-4eeb-9c8c-49be556b7e32", "started_at": at("2026-09-23"), "prompt_count": 7,
     "shared": ["Event spaces with childcare"]},
]


class ChooseEarlierRunsTests(unittest.TestCase):
    def test_two_tests_from_one_day_with_different_questions(self):
        ids, started = choose_earlier_runs(CANDIDATES, ["30f9160b", "b9ad0c8d-3d78-48f4-8885-89406e295f76", "30F9160B"])
        self.assertEqual(ids, ["30f9160b-1145-4a41-8d6f-ca156f8f1dac", "b9ad0c8d-3d78-48f4-8885-89406e295f76"])
        self.assertEqual(started, at("2026-10-09", 15))

    def test_refusals_say_why(self):
        with self.assertRaisesRegex(ValueError, "not an earlier completed test"):
            choose_earlier_runs(CANDIDATES, ["deadbeef"])
        with self.assertRaisesRegex(ValueError, "is not an earlier"):
            choose_earlier_runs(CANDIDATES, ["30f9"])
        with self.assertRaisesRegex(ValueError, r"different days \(23 Sep 2026, 9 Oct 2026\)"):
            choose_earlier_runs(CANDIDATES, ["30f9160b", "022be437"])
        with self.assertRaisesRegex(ValueError, "at least one"):
            choose_earlier_runs(CANDIDATES, [])
        overlapping = [dict(CANDIDATES[1]), {**CANDIDATES[2], "shared": ["Event  spaces with childcare"]}]
        with self.assertRaisesRegex(ValueError, "more than one of the chosen tests"):
            choose_earlier_runs(overlapping, ["b9ad0c8d", "30f9160b"])

    def test_the_page_and_runner_offer_the_choice(self):
        page = (REPO / "app" / "pages" / "10_AI_Report_Generator.py").read_text()
        self.assertIn("compare_run_ids=beta_compare_runs", page)
        self.assertIn('"Earlier tests to compare with"', page)
        runner = (REPO / "src" / "report_runner.py").read_text()
        self.assertIn("Earlier tests to compare with", runner)


if __name__ == "__main__":
    unittest.main()
