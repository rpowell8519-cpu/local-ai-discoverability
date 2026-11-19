# Report runner (v1)

Runs a client report's brief and paid AI Visibility test from the command line, so the setup no
longer needs the report generator's screens. It is meant to be driven by Claude Code with the
`run-found-report` skill (`.claude/skills/run-found-report/SKILL.md`), stopping for Rob at each gate.

**v1 covers steps 1 to 3** of the report generator: the owner brief, the paid test and attaching it.
Website and review evidence (step 4), the review (step 5) and generating Final Beta (step 6) stay in
the report generator for now. Generation moves here only once step 5's checks live in `src/`,
because those checks decide whether a report may be generated.

## What it shares with the page

Nothing is re-implemented. Both use:

- `save_owner_brief_revision` and `attach_benchmark_revision` (`src/report_audit_repository.py`);
- `create_visibility_run`, `create_visibility_queries`, `execute_calls`, `finalise_run_from_results`;
- `prompt_records`, `build_call_plan`, `DEFAULT_MODELS` and `MAX_RUN_QUESTIONS` (`src/report_runner.py`);
- the business list query (`src/report_business_records.py`);
- `resolve_run_location`, so there is still no default location.

Revisions the runner writes carry `created_by = "report_runner"`.

## Settings

Run from the repository root with the app's virtual environment. `DATABASE_URL` comes from `.env`
as for the app. API keys and models come from the environment, else from the ignored
`.streamlit/secrets.toml` (the same names as the pages: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`,
`GEMINI_API_KEY`, and optionally `OPENAI_MODEL`, `ANTHROPIC_MODEL`, `GEMINI_MODEL`). Keys are never printed.

## The brief file

TOML, one file per business. See `docs/examples/report-brief.example.toml` (a fictional business).
**Real briefs hold client details and must stay outside this public repository**, for example in
`~/found-briefs/`. `.gitignore` also ignores `briefs/` and `*.brief.toml` as a backstop.

The business must already be in the database with a confirmed Google listing. `find` looks it up;
a business that is not there is imported in Data Admin first, as before.

Write service areas the same way as earlier tests of that area, because the wording is given to the AI
tools as the customer's location and a different wording is a different test (Brighton and Hove tests
have used "Brighton and Hove").

Each question's label, search intent, importance and effort are saved with the brief, in
`owner_context["question_details"]` (no schema change), and used in the paid test. The brief check and the
plan show them. A brief saved from the page has none, and its questions get the page's defaults; the page's
question table does not read them yet.

## Commands

```
python -m src.run_report find "Business name"                 # read-only
python -m src.run_report brief ~/found-briefs/x.toml          # read-only check
python -m src.run_report brief ~/found-briefs/x.toml --save   # gate 1 approved
python -m src.run_report plan <place-id>                      # read-only: plan + approval code
python -m src.run_report run <place-id> --approve <CODE>      # gate 2 approved: PAID
python -m src.run_report status <place-id>                    # read-only
```

## Re-tests

A re-test repeats earlier tests exactly instead of rebuilding them from the saved brief:

```
python -m src.run_report plan <place-id> --like <test-id> [--like <test-id>]
python -m src.run_report run  <place-id> --approve <CODE> --like <test-id> [--like <test-id>]
```

A test id may be given in full or by its first 8 characters, as reports and notes quote it. The
re-test takes the baseline tests' exact questions (with their labels and search intents), the exact
customer location they gave the AI tools and their number of repeats. Several baselines can be
repeated as one test (WRAP coworking's two 9 October tests, for example) when they share a location
and number of repeats; a question asked in both is asked once. Baselines must be completed client
(core) tests of the same business.

Before approval the plan lists what is no longer like-for-like: a model that has changed, a different
number of repeats, the saved brief's questions differing from the baseline's, and every question that
names no place (if the baseline ran before 10 November 2026, Claude's answers to those questions are not
comparable, because of the location fix). The approval code includes the baseline ids.

In Final Beta, tick "Compare with the earlier test" and choose the baselines under "Earlier tests to
compare with". Left empty, it compares with the most recent earlier completed core test that shares a
question, which may be a later internal check. The plan and the run's outcome both name the tests to choose.

## The gates, enforced in code

- **Gate 1, the brief.** `brief` only writes with `--save`. When the business already has a test
  attached or review decisions saved, saving a new brief makes them no longer current (they are kept,
  and can be restored from step 1 of the page), so it also needs `--replace-current`.
- **Gate 2, the spend.** `plan` prints the questions, location, tools, models, number of paid calls
  and an approval code. The code is a fingerprint of all of those plus the saved brief revision, so
  `run` refuses a code from a different plan. A code works once: saving a brief or attaching a test
  creates a new revision, so the next run needs a fresh `plan` (as the 19 November end-to-end test showed). A completed test already attached to the brief is not
  paid for again without `--again`. `run` also refuses if `anthropic_provider.REQUIRED_SEARCH_VERSION`
  is not the version this module expects (`EXPECTED_SEARCH_VERSION`), the same guard as the pages.
- **No cost in pounds yet.** Nothing records the cost per call today, so the plan shows the number of
  calls and warns that search-tool charges may apply.

A test that finishes `partial` or `failed` is not attached, exactly as on the page. Retry only the
missing calls on the AI Visibility page, then attach it from step 2 of the report generator.

## Tests

`tests/test_report_runner.py` uses no database and no AI tool: every write and paid call is a
recorded fake. Run with `env -u DATABASE_URL PYTHONPATH=. .venv/bin/pytest -q tests/test_report_runner.py`.
