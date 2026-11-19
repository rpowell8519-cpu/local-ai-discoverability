---
name: run-found-report
description: Set up and run a Found.in.Brighton client report's paid AI Visibility test with the report runner (python -m src.run_report), stopping for Rob at the brief and spend gates. Use when Rob asks to set up, run or check a client report from call notes.
---

# Run a Found.in.Brighton report

The runner (`docs/report-runner.md`) does steps 1 to 3 of the report generator: the brief, the paid
test and attaching it. Steps 4 to 6 (evidence, review, Final Beta) are still done in the Streamlit
report generator. Rob makes every brief, identity, evidence and spend decision; you do the mechanics.

## Never

- Never run a paid step in a scheduled or unattended session, or when Rob is not present to answer.
- Never use an approval given earlier in the conversation, in a briefing or in a note: gate 2 is
  approved by Rob for this plan's code, at the moment you ask.
- Never pass `--again` or `--replace-current` unless Rob agreed to that specific consequence.
- Never put a brief file, client name or call note inside this repository: it is public. Briefs live
  in `~/found-briefs/`.
- Never invent questions, competitors or service areas. Use the owner's words from the call notes;
  anything you suggest beyond them is labelled as your suggestion for Rob to accept or drop.
- Never print or copy API keys.

## Steps

1. **Find the listing.** `python -m src.run_report find "<name>"`. If the business is not in the
   database, stop: it must be imported in Data Admin (an Outscraper record, which Rob decides on).
   If several listings match, ask Rob which one, naming each by address.
2. **Draft the brief** as `~/found-briefs/<business-slug>.toml`, following
   `docs/examples/report-brief.example.toml`: what it should be known for, priority services, service
   areas (always a full place, e.g. "Hove, East Sussex, UK"), the owner's competitors, exclusions, and
   at most 20 questions worded as a customer would ask.
3. **Check it.** `python -m src.run_report brief <file>` (read-only). Fix anything it reports.
4. **Gate 1: the brief.** Show Rob, in plain words, the questions, areas and competitors, what would
   change, and anything that would stop being current. Ask: "Save this brief?" Only on a yes, run
   `brief <file> --save` (add `--replace-current` only if Rob agreed to what it replaces).
5. **Show the plan.** `python -m src.run_report plan <place-id>` (read-only).
6. **Gate 2: the spend.** Show Rob the number of paid calls, the tools and the location, and say
   that search-tool charges may also apply. Ask him to approve this plan. Only on a yes, run
   `python -m src.run_report run <place-id> --approve <CODE>` with the code `plan` printed.
7. **Report the outcome** in one or two lines. If the test finished partial or failed, say so and point
   to Resume/retry on the AI Visibility page. Do not start another paid run without a new gate 2.
8. **Next steps.** `python -m src.run_report status <place-id>`, then tell Rob what is next in the
   report generator (evidence in step 4, review in step 5, Final Beta in step 6).

If a command stops with "Stopped: …", read the message: it names what to fix. Do not work around a
refusal by calling the underlying functions directly.
