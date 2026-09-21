# AGENTS.md

## Project purpose

This repository powers a Streamlit application for auditing and improving local-business AI discoverability.

The core workflow is:

AI Discovery / AI Visibility
→ identify businesses AI recommends
→ resolve business entities
→ compare target vs relevant AI leaders / competitors
→ collect website and review evidence
→ synthesize observable differences
→ generate client-controllable recommendations
→ rerun later to measure change

Treat this as a working product. Preserve existing functionality unless the user explicitly asks to change it.

## Core architecture

- UI entry point: `app/streamlit_app.py` is the client report console. It lists saved
  report projects, splits them into work in progress and reports ready to generate, and
  hands off to `app/pages/10_AI_Report_Generator.py`.
- UI pages: `app/pages/`
- Domain/workflow logic: `src/`
- Database: PostgreSQL / Supabase via SQLAlchemy + psycopg
- Durable results: PostgreSQL
- Cross-page temporary workflow state: `st.session_state`

There is no separate backend service.

## Owner-services report (v4)

The accessible owner report is a read-only projection of saved evidence. It is a
conversation tool for small-business owners, not a technical audit.

- `src/owner_services_report.py` builds the report (`build_owner_report`). All counts
  come from saved answers, never narrative copy: one appearance is one resolved business
  in one valid completed answer's recommendation list. Unknown names stay in the market
  but are never upgraded to verified entities. Raw slots and answers are not modified.
- `src/owner_services_pdf.py` is the flowing PDF layout shared by client and synthetic
  reports. `src/poc_audit_pdf.py` dispatches to it for the v4 format.
- `src/owner_services_synthetic.py` holds fictional demonstration evidence. Never use it
  as client research.
- `src/owner_services_export.py` is an offline export
  (`python -m src.owner_services_export --udr-payload <evidence.json>`). It makes no
  database access, benchmark calls or snapshot writes.
- `src/report_competitors.py` selects comparison businesses. The reviewer sets the
  catchment; the default radius is 3 miles for walk-in businesses (salons, cafes, pubs
  and close peers) and 15 miles for everything else. These are provisional defaults.
- `app/pages/10_AI_Report_Generator.py` is the operator UI for all of the above.

Process and open QA items live in `docs/beta-report-process.md` (owner conversation,
question sets, what may be claimed) and `docs/udr-report-qa-required-changes.md`. Read
both before changing report wording, layout or counting rules.

## Operator workflow state

`report_audit_revisions` is the durable, append-only record of a report project. It holds
the owner brief (`known_for`, `desired_searches`), the attached benchmark run, evidence
states and reviewer decisions.

`st.session_state` is browser-session-only. It does not survive a reopened tab, an app
restart or a session timeout.

Do not source a report-critical input from `st.session_state` alone. Always reload it from
the latest durable revision and treat session state as a cache.

This rule exists because AI Visibility previously read the owner's priority questions only
from session state. A new browser session silently fell back to generic generated prompts
and still allowed a paid benchmark to start, producing a report that measured the wrong
questions. See `load_durable_owner_brief` in `app/pages/8_AI_Visibility.py`.

Specifically:
- A paid run must not start when a saved brief exists but none of its questions are selected.
  Offer to reload the owner's questions, or require an explicit opt-out.
- `ACTIVE_REPORT_PROJECT_KEY` is a navigation convenience for handoffs between pages. It is
  not a source of truth, and must not gate a correctness guard.
- Derive report status from `report_journey()` in `src/report_generator_readiness.py` rather
  than reimplementing readiness rules per page.

## Business identity rules

Google Place ID is the canonical local-business identifier across the application.

Do not introduce name-based identity where a Place ID exists.

Unmatched AI Discovery targets are the established exception: they use a synthetic identity in the form `discovery:<run UUID>` until they can be resolved to a canonical Google Place ID.

`raw_outscraper_locations` preserves historical raw import snapshots.

`business_features` is the derived/current entity layer and should contain one current feature record per Place ID.

When reading current raw business attributes such as website, category, type, subtype, ratings, or raw metadata, use the latest raw row for that Place ID, normally ordered by:

`created_at DESC, id DESC`

Do not assume there is only one raw row per Place ID.

### The report target under a shorter name

AI answers often use a shorter brand name than the Google listing ("WRAP" for
"WRAP- Coworking, Meeting Rooms & Offices"). The directory only matches variants of the
full listing name, so those answers stay unresolved and the target is credited with
nothing, which can produce a false "did not appear" headline.

Do not fix this by automatically upgrading unresolved names. `src/report_identity.py`
finds look-alike unresolved names. The reviewer confirms or rejects each one in step 5 of
the report generator, and the decision is stored in `reviewer_decisions`
(`confirmed_target_names`, `rejected_target_names`), so no schema change is needed.
Confirmed names are credited through `slot_adjudications` and disclosed in the report's
methodology. Generation refuses to run while a look-alike name is undecided.

### Question-to-priority links and comparison evidence

The owner's priority services and the tested questions are written separately, so
`src/report_priorities.py` links them. Step 5 of the report generator suggests a link from
shared wording, and the reviewer confirms each one. Links are stored in `reviewer_decisions`
(`question_priority_map`) and turned into the report's service groups. A priority with no
question is "Not tested", never a zero. Do not remove the completion gate: without links the
report shows "coverage not mapped" for every priority.

Step 4 collects website and review evidence for the target only, because the comparison set
is chosen afterwards. Step 5 therefore shows the comparison businesses' evidence and can
crawl their websites. Reviews for them go through the review tools, which apply the cost ceiling.

## Database safety

Do not apply changes to the Supabase/PostgreSQL schema without the user's explicit approval.

If a requested feature requires a schema change, explain why it is required and ask for approval before applying it.

Do not invent or silently apply SQL migrations.

Before changing persistence logic:
1. inspect existing repository/query behaviour;
2. preserve historical raw-data semantics;
3. preserve existing table relationships and keys.

If a required schema detail is unknown, first investigate it through safe read-only sources such as existing repository queries, `information_schema`, PostgreSQL catalog metadata, or available Supabase metadata. If it remains unknown, stop and ask for the schema rather than guessing.

Do not delete or truncate production data during QA.

## Secrets and external services

Never print, expose, commit, or rewrite secrets.

Local secrets may be supplied through ignored `.streamlit/secrets.toml` files or environment configuration such as an ignored `.env` file. They must remain ignored by Git.

External services include:
- OpenAI
- Anthropic
- Gemini
- Outscraper
- Supabase/PostgreSQL

Do not trigger paid API calls during QA unless the user explicitly authorises them.

Preserve the default application-side Outscraper cost ceiling of £7.50 unless the user explicitly asks to change it.

Preserve manual CSV/XLSX import fallbacks when adding direct API integrations.

## AI measurement semantics

Current AI Visibility / Discovery testing is primarily a model-memory benchmark unless explicitly implemented otherwise.

Do not describe observed website/review differences as proven AI ranking factors.

Use language such as:
- observable difference
- evidence-backed opportunity
- client-controllable action
- correlation / comparison

Do not claim causality unless directly supported.

Share of Recommendation and related metrics should only use valid completed responses according to existing logic.

## Recommendation logic

Recommendation synthesis should remain evidence-driven and explainable.

Do not use an LLM to invent client recommendations where deterministic evidence logic already exists.

A competitor difference should not automatically become a recommendation.

Respect:
- business relevance
- evidence strength
- AI-leader prevalence
- client proposition relevance
- client controllability
- confidence

Preserve strengths and suppressed/non-priority observations where relevant.

## Change discipline

Make the smallest safe change that solves the requested problem.

Do not wholesale-rewrite working Streamlit pages to fix isolated bugs.

Before editing:
1. inspect the relevant files and data flow;
2. identify the likely root cause;
3. describe the intended minimal change.

Prefer modifying existing modules over duplicating logic.

Do not refactor unrelated code as part of a feature or bug fix unless the user explicitly asks for refactoring.

Preserve existing UI workflows unless the requested change requires altering them.

## Git workflow

Assume `main` is production-sensitive.

Before making code changes:
- run `git status`;
- ensure the worktree state is understood.

Do not push directly to `main` unless the user explicitly asks.

Prefer a feature/fix branch for substantive authorised code changes. Do not create or switch branches for read-only work unless the user explicitly asks.

Do not rewrite Git history.

Do not commit secrets or local environment files.

## Validation

For any Python code change, run at minimum:

`python -m compileall -q app src`

Also run:

`python -m pip check`

Where practical, run a local Streamlit smoke launch:

`streamlit run app/streamlit_app.py --server.headless true`

A single page can be executed headlessly, without a browser, using Streamlit's own
harness. This runs the real script against the configured database and reports any
exception:

`AppTest.from_file("app/pages/8_AI_Visibility.py", default_timeout=180).run()`
(from `streamlit.testing.v1`)

Keep this read-only: it renders the page, it must not be used to click import, rebuild,
save, delete, audit-run, review-pull or AI-run controls.

Do not trigger paid APIs as part of smoke testing.

The configured local database may be a production database. QA and smoke testing must remain read-only unless the user explicitly authorises mutations. Do not use import, rebuild, save, delete, audit-run, review-pull, or AI-run controls during routine smoke testing against an unconfirmed database.

For a targeted change, also run the narrowest relevant validation available.

If validation cannot be completed, state exactly what was and was not verified.

## Completion report

After making substantive changes, report:

1. root cause / rationale;
2. files changed;
3. behaviour changed;
4. validation performed;
5. anything not verified;
6. any manual deployment or SQL step required.

Do not claim success merely because code compiles.

For trivial documentation or similarly low-risk changes, keep the completion report proportional: summarise the files changed, the effective change, and any relevant validation or unverified items without forcing every heading above.

## Known architectural cautions

Be especially careful around:

- historical raw business imports;
- browser-session-only diagnostic cohorts;
- synchronous long-running AI/crawl work;
- fuzzy entity resolution;
- website crawling of JS-heavy sites;
- heuristic review sentiment/themes;
- hard-coded AI model identifiers;
- direct SQL embedded in Streamlit pages.

Do not address these opportunistically unless they directly affect the requested task.

## Known code-quality observations

Codex previously identified:
- `requests` is used directly but may only be installed transitively;
- `vertical_profiles.py` appears to contain two definitions of `get_profile_for_business`;
- `get_engine()` may create a new SQLAlchemy engine on every call;
- automated tests now exist under `tests/` and are run with pytest, so this earlier
  observation is resolved; run them with
  `env PYTHONPATH=<repo root> .venv/bin/pytest -q`;
- database migrations/schema bootstrap are not stored in the repo;
- Data Admin's full feature rebuild reads all historical raw rows ordered by `source_row_number` and repeatedly upserts `business_features`; with multiple imports, this may not leave the latest `created_at DESC, id DESC` snapshot as the current feature record and should be investigated as a separate potential defect.

Treat these as backlog items, not automatic refactoring instructions.
