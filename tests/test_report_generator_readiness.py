from __future__ import annotations

import unittest

from src.report_generator_readiness import (
    normalise_owner_brief,
    owner_brief_missing_fields,
    owner_prompt_records,
)


class ReportGeneratorReadinessTests(unittest.TestCase):
    def test_owner_competitors_are_optional(self):
        brief = normalise_owner_brief(
            known_for="Wedding hair and natural colour in Brighton",
            desired_searches="Who is best for wedding hair in Brighton?",
        )
        self.assertEqual(owner_brief_missing_fields(brief), [])
        self.assertEqual(brief["owner_competitors"], [])

    def test_multiline_answers_are_normalised(self):
        brief = normalise_owner_brief(
            known_for="  Friendly   independent salon  ",
            desired_searches="- Best salon in Brighton?\n• Who offers balayage?\n\n",
            owner_competitors="Salon One\nSalon Two",
        )
        self.assertEqual(brief["known_for"], "Friendly independent salon")
        self.assertEqual(
            brief["desired_searches"],
            ["Best salon in Brighton?", "Who offers balayage?"],
        )
        self.assertEqual(brief["owner_competitors"], ["Salon One", "Salon Two"])

    def test_missing_required_owner_answers_are_reported(self):
        self.assertEqual(
            owner_brief_missing_fields({}),
            [
                "what the business should be known for",
                "at least one realistic customer search",
            ],
        )

    def test_owner_questions_become_visibility_prompts(self):
        brief = normalise_owner_brief(
            known_for="Commercial cleaning for Brighton businesses",
            desired_searches="Best office cleaners in Brighton?\nWho cleans carpets?",
            owner_competitors="Optional Competitor",
        )

        prompts = owner_prompt_records(brief)
        self.assertEqual([item["source"] for item in prompts], ["owner_brief", "owner_brief"])
        self.assertEqual(
            [item["prompt"] for item in prompts],
            ["Best office cleaners in Brighton?", "Who cleans carpets?"],
        )


if __name__ == "__main__":
    unittest.main()
