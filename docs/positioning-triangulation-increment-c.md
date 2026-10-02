# Increment C: positioning suggestions and action tracking

Implemented on `feature/positioning-triangulation`, based on B's merge `c28c1af`.
Rob merged C as PR #17 (`006af7c`) and explicitly approved the named one-table migration
on 2 October 2026. **The migration is applied**, recorded in live history as version
`20261002093735`, name `positioning_interventions`. Action saving is now available.
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

## Action record and persistence

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

The [SQL artifact](../sql/20261002085635_positioning_interventions.sql) was created by Supabase
CLI 2.119.0 and follows the existing `sql/` convention. It was applied once through the Supabase
migration tool following the separate explicit approval above. The original DRAFT header is
retained verbatim to preserve the approved bytes/hash. **Do not replay it because its local
timestamp differs from live history.** It adds only
`public.positioning_interventions`, indexes, an insert validator and an append-only guard.
It enables RLS, removes inherited/public/client/service ALL grants, then grants the trusted
service role SELECT/INSERT only. Functions are security invoker with an empty search path;
client roles have no execute grant. Administrative PostgreSQL owners retain their capabilities.
The validator checks sequential revisions, exact JSON/relational identity, same-business captures
and evidence, baseline run/wave series, existing completed approved-action links, and actual
implementation dates/completion evidence. Existing tables/rows are not changed or backfilled.

Positioning and validated/downloadable action drafts were available before schema approval.
The post-application walkthrough confirmed saving is enabled. A historical baseline without frozen panel/wave
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
record. No production action was inserted for QA: synthetic SQL and mocked repository/form tests
verify insertion behavior; post-application live checks verify schema/guards and form readiness.
The first genuine action save remains an operator task. Opt-in live/paid tests
remain disabled.

Final full-suite run from a clean detached checkout of code commit `fb5e8c1`: **830 passed,
73 subtests passed, 13 skipped, zero failures**, in 125.57 seconds. Compilation, `pip check`,
`git diff --check` and isolated SQL tests passed. The final live read-only walkthroughs passed
again with unchanged counts. Subsequent packaging changes only add these validation details.

The applied SQL SHA-256 is
`a64ff273413eec0f5cf10b666be35b5c5c8d8f716bd68a9d486b02113d732ea6`.
Approval covered this exact one-table migration, not A/B reapplication or a backfill.

## Post-application verification, 2 October 2026

Fresh fetch confirmed PR #17 and byte-identical application/test/SQL code relative to the
previously validated feature commit. The merged SQL matched the approved SHA-256. Preflight
confirmed the C table/migration were absent, before the single successful application.

Read-only live metadata checks confirmed RLS, both enabled triggers, security invoker/empty
search path, service-role SELECT/INSERT only, no client table privileges, and no client execute
privilege on the new validator. Migration history records the version/name above.

Evidence Review and Positioning passed AppTest for both Cisco and Wild Flor against the merged
code. Selecting each existing benchmark also passed. The database refused writes throughout;
no forms were submitted, and action-save controls were enabled. Pre/post counts matched:
44 runs, 3,481 reviews, 2,390 raw listings, 98 report revisions, two captures, 112 observations,
zero evidence decisions, zero collection attempts and zero interventions.

Security advisors returned no new warnings. The new private table has the expected
[RLS-without-client-policy informational notice](https://supabase.com/docs/guides/database/database-linter?lint=0008_rls_enabled_no_policy).
Performance advisors found no uncovered C foreign keys; unused-index notices are expected on
the empty table. Four previously existing function search-path warnings and nine uncovered
foreign keys remain outside this migration. No paid collection, human approvals, benchmark
execution, historical report refresh or source-data mutation occurred during verification.
