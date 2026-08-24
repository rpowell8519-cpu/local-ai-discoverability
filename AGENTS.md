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

- UI: `app/streamlit_app.py` and `app/pages/`
- Domain/workflow logic: `src/`
- Database: PostgreSQL / Supabase via SQLAlchemy + psycopg
- Durable results: PostgreSQL
- Cross-page temporary workflow state: `st.session_state`

There is no separate backend service.

## Business identity rules

Google Place ID is the canonical local-business identifier across the application.

Do not introduce name-based identity where a Place ID exists.

Unmatched AI Discovery targets are the established exception: they use a synthetic identity in the form `discovery:<run UUID>` until they can be resolved to a canonical Google Place ID.

`raw_outscraper_locations` preserves historical raw import snapshots.

`business_features` is the derived/current entity layer and should contain one current feature record per Place ID.

When reading current raw business attributes such as website, category, type, subtype, ratings, or raw metadata, use the latest raw row for that Place ID, normally ordered by:

`created_at DESC, id DESC`

Do not assume there is only one raw row per Place ID.

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
- automated tests are currently absent;
- database migrations/schema bootstrap are not stored in the repo;
- Data Admin's full feature rebuild reads all historical raw rows ordered by `source_row_number` and repeatedly upserts `business_features`; with multiple imports, this may not leave the latest `created_at DESC, id DESC` snapshot as the current feature record and should be investigated as a separate potential defect.

Treat these as backlog items, not automatic refactoring instructions.
