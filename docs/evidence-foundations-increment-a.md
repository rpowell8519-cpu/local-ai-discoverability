# Increment A: evidence foundations

Prepared on `feature/evidence-foundations`, from merged PR #14 (`origin/main` at `52361cb`).
Rob authorized starting local Increment A implementation and explicitly approved its migration
on 1 October 2026 ("Great, please proceed", in reply to the specific migration/verification step).
The schema and a permission correction are now applied. No backfill, paid API call, snapshot
freeze or business-data backfill has been performed. Rob subsequently approved committing and
pushing this implementation for a feature PR. Application code is not merged/deployed by that approval.

## What is implemented locally

* A vertical-neutral starter catalogue and exact reviewed-alias resolver. Unknown and ambiguous
  labels are retained; misspellings are not silently fixed. Catalogue definitions describe
  propositions, not strengths attributed to businesses.
* Tested-intent inspection uses **existing `ai_visibility_runs.target_propositions`**, retaining
  original labels/run IDs, alongside the completed review's `question_priority_map` for that exact
  run. Run context alone does not establish a tested question. Repeats are one sampled intent.
* Visibility run creation now accepts owner priorities in that existing column. Discovery
  creation retains its existing context write. The report generator, Visibility and Discovery
  controls pass the exact selected prompts to the new metadata path. Reload guards recognize
  the expanded creation APIs before paid-run controls are available.
* Separate adapters for published Google profile rating/count observations and saved review-text
  samples. Profile provenance includes raw capture ID, capture timestamp, adapter version and
  raw-data hash. Sample windows describe sampled texts only; platform velocity/latest published
  review date remain unknown. Nothing treats Cisco's 63 saved Google texts as its published total.
* An immutable panel configuration records prompt text/order/source/category/weights, providers,
  requested models, mode, instructions, location, repeat count and provider-adapter source hashes.
  A wave uses the existing run ID; matching target/configuration waves reuse a series under a
  transaction lock. Changed settings/mode/model/prompt/adapters create a separate configuration.
  Core/focused kind is part of the fingerprint, so they cannot share a panel/series accidentally.
* Providers' reported model identifiers are preserved in existing response `report_metadata`
  where supplied. They are not automatically described as verified immutable model versions.
  Compatibility checks reject missing panel metadata, different configurations/series and
  unknown or differing served model versions.
* A read-only **Evidence Foundations** Streamlit page lets an operator inspect dated published
  metrics versus samples, context versus confirmed question links, unresolved labels and panel/
  wave/series provenance. It cannot collect reviews, start paid calls or save production data.

## Applied schema

The CLI-generated migration file is
[`sql/20261001124625_evidence_foundations.sql`](../sql/20261001124625_evidence_foundations.sql).
It follows the existing `sql/` deployment convention; it is not a new Supabase local stack.

| Local artifact | Recorded live migration version / name |
|---|---|
| `20261001124625_evidence_foundations.sql` | `20261001160213` / `evidence_foundations` |
| `20261001160431_evidence_foundation_service_permissions.sql` | `20261001163350` / `evidence_foundation_service_permissions` |

MCP assigns its own live history timestamps. Both files are applied; do not replay them because
their local filenames differ from the live timestamps. The original SQL is retained verbatim,
including its pre-approval draft comment. Applied SHA-256:
`c39fa5545ae340155ed875834f5d3ed7070e0827f8d68867c4691d9e40ed8f92`.

| New table | Purpose |
|---|---|
| `proposition_catalog` | Stable proposition keys, labels and catalogue version |
| `proposition_aliases` | Exact normalized reviewed labels linked to catalogue keys |
| `review_profile_metrics` | Dated published profile observations, separate from sampled texts |
| `ai_measurement_waves` | Existing run linked to immutable panel configuration and compatible series |

The migration seeds 18 vocabulary entries and their aliases. It creates no owner-positioning
facts, tested-question claims or metrics for any business. Existing runs, queries, results,
raw listings, reviews, report revisions and issued snapshots are not updated. There is no
historical backfill. Profile observations reference canonical `business_features.google_place_id`;
waves reference existing run IDs. Indexes cover foreign keys and business/configuration history.

The four tables enable RLS and revoke access from `PUBLIC`, `anon` and `authenticated`.
`service_role` has SELECT/INSERT privileges; the existing privileged SQL connection remains the
operator path. Profile/wave triggers reject UPDATE/DELETE, including from table owners.
Confirm the hosted application's database role is the table owner or an appropriate existing
privileged backend role before deployment; do not grant broad client-role access to compensate.
No security-definer functions or public read policies are introduced. Supabase's inherited
default ALL grants initially left extra `service_role` permissions despite the SELECT/INSERT
grant. Verification caught this; the second migration explicitly revoked ALL on only these four
tables before granting SELECT/INSERT. Live checks now confirm UPDATE, DELETE, TRUNCATE,
REFERENCES and TRIGGER permissions are denied for that role. Project-wide default grants were
not changed. The SQL regression now reproduces hosted default grants and tests this correction.

Read-only pre-migration connection checks confirmed the configured application role is
`postgres`. Post-migration checks confirmed this configured application role can read all four
stores and loads the stored catalogue (18 propositions / 27 aliases).

## Behaviour when the optional migration is absent

This backward-compatible fallback remains tested, but is no longer the live state.
The operator page reads existing raw captures, reviews and run context and labels its local
starter vocabulary. Stored catalogue/history and new wave persistence are clearly pending.
New benchmark runs continue using the existing schema; wave metadata is saved in the same run
transaction only when its additive table exists. Missing wave metadata remains unknown and
cannot qualify as a verified longitudinal comparison. Legacy runs are never assigned synthetic
panels/series on read. The explicit profile-history writer exists for future adapters, but no
automatic historical import or collector change is enabled in this increment.

## Validation

Both migrations have been executed in an isolated in-memory PostgreSQL WASM engine
(`@electric-sql/pglite@0.3.15`), using synthetic identities and roles only. Checks passed for:
catalogue seed, FK/check constraints, future dates, append-only observations/waves, client grants,
RLS after an accidental SELECT grant, backend-role reads and hosted-default-grant correction.
Synthetic insert/update/delete/truncate tests occur only in this isolated database; live
post-migration checks inspect permissions, constraints and triggers without writing test rows.

Reproduce with an isolated PGlite installation and:

```bash
EVIDENCE_SQL_TEST_ENGINE=/path/to/node_modules/@electric-sql/pglite/dist/index.js \
  node tests/evidence_foundations_migration.mjs
```

Python tests cover catalogue ambiguity, missing historical context, per-question confirmations,
repeat aggregation, Cisco/Wild Flor context labels, sample/total separation, source provenance,
unknown profile metrics, configuration fingerprints, compatible/incompatible waves, pre-migration
behaviour, atomic creator writes and the read-only operator page. Full-suite results are recorded
after completion below. Compilation and `pip check` are also required before handoff.

Original A full-suite result: **721 passed, 73 subtests passed, 13 skipped**, zero failures. The skipped
live/opt-in checks were not enabled. The previous merged baseline was 687 passed; the added
tests cover this increment. Python compilation and `pip check` passed. No live benchmark,
profile collection, production mutation or golden-snapshot refresh was used for validation.

Read-only AppTest walkthroughs against the configured database also passed for Cisco's Karma
and Wild Flor. They showed 63/100 saved Google texts separately from older dated listing totals
70/478. These totals are historical captures, not fresh profile measurements. No controls were
clicked. That initial read-only check confirmed the wave table was absent before application.

Post-application read-only AppTest walkthroughs also passed for Cisco and Wild Flor, including the
matrix tab. The page uses the stored vocabulary and no longer displays the pending-migration
notice. Profile-history and wave tables remain empty: no historical backfill or paid benchmark was
performed. Catalog inspection confirms RLS, client access denial, enabled append-only triggers,
foreign keys/checks and the trigger function's fixed empty search path/security-invoker mode.
Before/after checks preserve 44 runs, 3,481 reviews, 2,390 raw listings and 98 report revisions;
the fingerprint of existing run IDs/target_propositions is unchanged.

Supabase advisors report intentional [RLS without client policies](https://supabase.com/docs/guides/database/database-linter?lint=0008_rls_enabled_no_policy)
and [unused new indexes](https://supabase.com/docs/guides/database/database-linter?lint=0005_unused_index).
The new tables are private backend stores and mostly empty; do not add client policies or remove
their planned indexes to suppress those notices. Four warnings concern older snapshot/revision
functions' [mutable search paths](https://supabase.com/docs/guides/database/database-linter?lint=0011_function_search_path_mutable);
those functions are outside this migration and were not altered. No new missing-FK-index or
mutable-search-path warning targets this increment.

## Limitations and next decisions

This is the first foundation increment, not the evidence matrix, proposition support classifier,
research engine or focused-monitoring scheduler. Source-profile metric ingestion initially supports
Google's five-star scale; other native scales require explicit adapters/schema extension.
Platform collection-attempt persistence beyond the existing manual zero-check fix remains B work.
The starter aliases require operator acceptance as part of migration review; unresolved client
labels remain visible and can be added later rather than guessed. Adapter hashes conservatively
change the panel fingerprint even for harmless source edits. Report layouts/golden payloads stay
unchanged. Live Cisco/Wild Flor golden checks remain opt-in.

Next: retain this reviewed database state, deliver the approved code through a feature PR,
and continue B's durable source-capture/collection-attempt/review-decision design.
Further migrations or business-data backfills need their own explicit approval.

Subsequent local progress: a [read-only B matrix preview](public-evidence-matrix-increment-b.md)
now extends this page with the A schema applied. Combined validation is 746 passed,
73 subtests passed and 13 skipped. This preview does not persist or freeze evidence observations.
The full suite was rerun after application: **746 passed, 73 subtests passed, 13 skipped**
in 122.25 seconds. The isolated SQL regression also passed with synthetic service-role INSERT
and denied DELETE/TRUNCATE operations under reproduced hosted default grants. No production
test rows were inserted.
