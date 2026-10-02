# Increment C: positioning suggestions and action tracking

Implemented on `feature/positioning-triangulation`, based on B's merge `c28c1af`.
The [two-business pilot](evidence-pilot-2026-10-02.md) has two verified live archives and an
operator review packet. Human excerpt approvals remain outstanding. No paid calls were made.

## Result

`app/pages/13_Positioning.py` compares three separate observations: the latest saved owner's
priority list, customer evidence approved in the selected immutable capture, and reviewer-confirmed
question mappings for the selected run. It reuses `ai_visibility_runs.target_propositions` and
`question_priority_map`; context labels alone never establish tested questions. Unresolved labels,
unreviewed excerpts, original source dates, exact decision IDs and missing provenance are visible.
Free-text `known_for` remains context, without automated interpretation. Unlisted priorities are
unknown, not owner rejections. Issued reports and their measurements are unaffected.

Default support thresholds are two distinct saved customer records in at least one source class.
These are provisional, adjustable operator rules, preserved with each finding. Records are not
independent customers. Multiple excerpts from one source record count once per proposition.
Owner and syndicated claims never become customer corroboration. A later UNCERTAIN revision
withdraws that excerpt's affirmative support. A reviewed contradiction takes precedence.

| Suggestion | Transparent rule |
|---|---|
| STRATEGIC_CORE | Recorded owner priority, customer support meeting both thresholds, and at least one confirmed tested question |
| HIDDEN_STRENGTH | Same owner/customer support, but no matching question in a completely mapped selected panel; does not claim low visibility elsewhere |
| CUSTOMER_STRENGTH | Customer support meets thresholds, while the owner/test combination does not qualify for either rule above |
| UNPROVEN_AMBITION | Recorded owner priority and every matching customer excerpt reviewed as NO_SUPPORT with confirmed identity/customer origin; scoped to those excerpts |
| CONFLICTED_EVIDENCE | At least one reviewed contradiction; investigate before changing positioning |
| NEEDS_REVIEW | Insufficient evidence or mappings; includes no matches and wholly uncertain evidence |

An opportunity in the market is **not inferred from tested intent**: prompt selection is not demand.
That suggestion requires separate market evidence outside this increment. A fully mapped panel
is required for negative tested claims; positive confirmed links still work within an incomplete
map. Thresholds don't change raw evidence or AI measurements.

## Action record and proposed persistence

An action holds one proposition, an explained finding/hypothesis, selected exact-capture evidence
IDs, responsible owner, agreed priority/unknown effort, lifecycle status, optional planned/actual
implementation dates, completion URLs, an explicit simultaneous-action bundle, baseline run/series,
focused-family labels, and optional existing approved report action/revision IDs. It does not create
an approved recommendation. Each saved revision preserves the positioning inputs/rules/dates and
has a recording operator and explanation. Implementation is never inferred from a report or crawl.

`src/interventions.py` validates drafts; `intervention_repository.py` is the explicit writer.
Edits append under a transaction lock and require the revision the operator actually loaded.
Concurrent changes cause a reload message rather than overwriting history. Action identity,
business, proposition and source capture cannot drift between revisions. To use a newer capture,
create a new action linked through an explicit bundle as appropriate.

The [draft SQL](../sql/20261002085635_positioning_interventions.sql) was created by Supabase
CLI 2.119.0 and follows the existing `sql/` convention. **It has NOT been applied.** It adds only
`public.positioning_interventions`, indexes, an insert validator and an append-only guard.
It enables RLS, removes inherited/public/client/service ALL grants, then grants the trusted
service role SELECT/INSERT only. Functions are security invoker with an empty search path;
client roles have no execute grant. Administrative PostgreSQL owners retain their capabilities.
The validator checks sequential revisions, exact JSON/relational identity, same-business captures
and evidence, baseline run/wave series, existing completed approved-action links, and actual
implementation dates/completion evidence. Existing tables/rows are not changed or backfilled.

Until explicit migration approval/application, Positioning remains useful and action drafts can
be validated/downloaded. Saving is disabled. A historical baseline without frozen panel/wave
metadata can be linked by run ID; its series stays null, so no compatible before/after is implied.
Collector integration, execution scheduling and before/after analysis belong to later increments.

## Verification

Offline tests cover unknowns, unresolved aliases, repeated source excerpts/questions, configurable
thresholds, origins, support withdrawal, contradictions, reviewed absence, business/capture identity,
draft validation, implementation requirements and stale revision rejection. AppTest mocks all writes
and checks missing schema/archive, drafts, explicit save and invalid implementation states.

Synthetic in-memory PGlite tests reproduce hosted default grants and validate the exact proposed SQL,
including forged/mismatched evidence, cross-business baselines/recommendations, revision predecessors,
implementation proof, append-only history and client/service permissions/RLS. No live DDL is tested
by applying it. Run with:

```bash
EVIDENCE_SQL_TEST_ENGINE=/path/to/node_modules/@electric-sql/pglite/dist/index.js \
  node tests/positioning_interventions_migration.mjs
```

Live read-only Cisco/Wild Flor walkthrough details and unchanged source counts are in the pilot
record. The new writer's live insert remains unverified until schema approval; synthetic SQL and
mocked repository/form tests establish its behavior before that approval. Opt-in live/paid tests
remain disabled. Final regression results are recorded below after the clean-checkout run.
