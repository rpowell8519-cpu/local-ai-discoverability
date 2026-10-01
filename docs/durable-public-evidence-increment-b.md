# Increment B: durable captures and operator review

Implemented on `feature/durable-public-evidence`, based on foundation commit `b1d8356`.
Rob approved committing/pushing the foundation branch and continuing this work. A fresh remote
fetch confirmed the foundation was subsequently merged into main in PR #15 (`79a5e85`).
This session does not merge B or push directly to main.

**The B migration is applied following Rob's explicit approval on 1 October 2026.** Live migration
history records version `20261001204207`, name `public_evidence_archive`. No B archive, decision,
observation or attempt has been written to production. The B code is packaged separately for review.

## Result and boundaries

The read-only matrix currently points at mutable website/review records. Its hash alone cannot
recover evidence if those records later change. This increment adds durable copies of existing
primary records, normalized observations tied to their exact copy, and append-only human review.

It does not refresh sources, buy reviews, start model calls, change report recommendations,
freeze issued report payloads, invent historical collection outcomes, add triangulation rules,
or expose research associations. Capture time is archive time, not a new source retrieval date.

The archive includes the saved Google listing/raw JSON, selected audit/full saved pages,
saved review rows/raw provider JSON, confirmed platform links and relevant manual-check revision
provenance. This preserves everything the current database has; it cannot recover uncaptured
live HTML, review text discarded by earlier imports or historical data that was never stored.
Only the selected business's checks are copied. The catalogue/aliases and diagnostic projection
are also retained, so later vocabulary or extraction changes do not rewrite old observations.
The projection adapter is versioned as `saved-evidence-matrix-v2`: review permalinks/original
collected profile URLs take precedence over a replacement platform link. A current linked-profile
fallback is labelled as a reference, rather than misrepresented as the original collected URL.

## Applied schema

CLI-generated artifact: [`sql/20261001174111_public_evidence_archive.sql`](../sql/20261001174111_public_evidence_archive.sql).
The exact approved SQL was applied once through the Supabase migration tool. Its SHA-256 is
`b3224ce618039b96b99ef8f6b99fdd3202b9cf3c896d462fd399e8b23592f18c`.
The tool assigned the live version above; the original file (including its historical DRAFT header)
is retained verbatim. **Do not replay it because its local timestamp differs from live history.**
It requires applied Increment A and adds four private backend tables:

| Table | Purpose |
|---|---|
| `public_evidence_captures` | Canonical business, complete saved-source copy, canonical JSON bytes/hash, archive time and operator |
| `public_evidence_observations` | Fact/proposition observations referencing a capture; insert trigger requires exact equality with the captured observation |
| `public_evidence_decisions` | Append-only human decision revisions referencing a proposition excerpt in that exact capture |
| `public_evidence_collection_attempts` | Actual dated outcomes, URL, checked scope, notes, adapter and usable sample size; optional same-business capture link |

Captures have a canonical Place ID FK. Identical business/content reuses its existing archive;
new content produces a new capture. Capture and normalized observations save in one transaction.
Canonical JSON is stored alongside JSONB; PostgreSQL validates their equivalence and checks the
[SHA-256 of the original UTF-8 bytes](https://www.postgresql.org/docs/17/functions-binarystring.html).
The writer explicitly binds canonical text as text before JSONB conversion, preventing parameter
type inference from changing the bytes. Readers verify the preserved bytes and semantic JSON
content; numbers may change rendering in JSONB, but booleans cannot masquerade as numbers.

Observation IDs must exist in the preserved payload, with the exact values and business identity.
Proposition keys reference the existing catalogue. Decision FKs exclude fact observations and
other captures. The backend writer serializes revisions with a per-capture/excerpt transaction
lock; revising appends a record, rather than updating an old approval. Latest revision is the
current interpretation. Support/contradiction requires confirmed business identity, an evidence
origin, a reviewer and an explanation. Earlier source evidence and decisions remain available.

All four tables enable RLS. Explicit REVOKE ALL includes `service_role` to override hosted default
grants, followed by SELECT/INSERT only. Client roles have no access. UPDATE/DELETE triggers reuse
the existing fixed-search-path security-invoker rejection function; service-role TRUNCATE is
also denied. The new observation validation function uses security invoker and a fixed empty
search path. FK indexes are included. No old table, source record, run or snapshot is altered;
no backfill is included. Trusted PostgreSQL owners retain administrative capabilities.

## Review semantics

Phrase extraction still creates `REVIEW_REQUIRED` candidates. The human decision distinguishes
explicit support, implicit support, contradiction, no support in that excerpt and uncertainty.
An unreviewed or wholly uncertain proposition has unknown breadth. Once definitive excerpts are
reviewed, breadth is the count of source classes with reviewed affirmative support in that scope;
incomplete/uncertain review remains visible. Owner claims, customer reports, independent third-party
evidence and syndicated claims are explicitly separate. Syndicated claims do not increase breadth.
Source breadth is not a count of independent witnesses; customer/third-party source breadth is
shown separately. Supporting and contradicting evidence IDs are inspectable. No universal score.

Choosing UNCERTAIN after an earlier support approval withdraws it from the current support count
without deleting history. Decisions apply only to their captured excerpt, not every mention of
the proposition or a future capture. Negated text is never auto-approved; overall review stars
remain excluded. Implicit paraphrases not found by the starter matcher remain a known limit.

## Collection outcomes and UX

`app/pages/12_Evidence_Review.py` provides separate explicit forms to archive saved evidence,
review a captured excerpt and record an actual completed collection outcome. It verifies the
archive before showing/reviewing it and exposes preserved context plus decision history.
It performs no writes on load. While its four tables are absent, it stops before showing write
controls; the original Evidence Foundations page remains read-only.

Recorded outcomes are COLLECTED (positive usable text sample), CHECKED_EMPTY (explicit zero),
FAILED or UNAVAILABLE (unknown sample size). NOT_CHECKED is absence of an attempt, not a fake
attempt record. URL, actual timezone-aware timestamp, checked scope and explanation are required.
No historical attempt is inferred from the date on an archived copy. These rows form a separate
operator ledger; they do not silently change existing reviewer-approved platform checks or
reports. Wiring actual asynchronous collector outcomes into this ledger remains follow-up work.

## Validation and deployment

Deterministic tests cover immutable copies/dates, raw provider context, changed-source recovery,
tamper detection, JSONB numeric rendering, cross-business/audit rejection, identity/origin/reviewer
requirements, unknown breadth, owner/customer/syndicated distinctions, revision withdrawal,
collection failures versus zero/positive samples, atomic capture writes, duplicate reuse and
serialized decision appends. AppTest uses mocked writers for all archive/review/attempt clicks.

The SQL was tested before application in isolated PGlite with synthetic identities/roles and reproduced
hosted default grants. Checks cover payload hashes, forged observations, decision FKs, attempt
constraints, append-only history, RLS and role privileges. Reproduce with:

```bash
EVIDENCE_SQL_TEST_ENGINE=/path/to/node_modules/@electric-sql/pglite/dist/index.js \
  node tests/public_evidence_archive_migration.mjs
```

Read-only live walkthroughs passed for Cisco's Karma and Wild Flor. Proposed captures were built
and hash-verified **in memory only** from 69/100 saved reviews and 10 pages each. The new review
page exposed no write controls before application. After application, read-only catalog checks
confirmed four RLS-enabled tables, service SELECT/INSERT only (no UPDATE/DELETE/TRUNCATE), no
anon/authenticated SELECT, all five guards enabled and the new function's empty search path/security
invoker. The new stores remained empty; legacy counts remained 44 runs, 3,481 reviews, 2,390 raw
listing rows and 98 report revisions. The `target_propositions` fingerprint was unchanged between
immediate pre/post checks. No production archive writer was called, no paid APIs were used and no
historical golden payload was refreshed.

Post-application AppTest walkthroughs passed for both Cisco and Wild Flor on Evidence Foundations
and Evidence Review using the configured application role (`postgres`). The review page's archive
and collection forms loaded, with an explicit empty-capture message. No controls were clicked;
all four archive stores were checked again and remained empty. Service-role permissions were
verified separately from the application's privileged database connection.

Advisor checks found no new security warnings or uncovered B foreign keys. The four new tables
produce expected [RLS-without-client-policy notices](https://supabase.com/docs/guides/database/database-linter?lint=0008_rls_enabled_no_policy);
unused indexes are expected on empty stores. Four pre-existing
[mutable-search-path warnings](https://supabase.com/docs/guides/database/database-linter?lint=0011_function_search_path_mutable)
and nine pre-existing uncovered foreign keys remain outside this migration's scope.

Final full-suite result: **781 passed, 73 subtests passed, 13 skipped**, zero failures, in
131.51 seconds. Compilation, `pip check`, `git diff --check` and isolated migration tests passed.
The skipped live/opt-in checks were not enabled. No live golden payload was re-frozen.
An operator's subsequent explicit archive/review action is distinct from deploying the schema.
Further steps: integrate real collector outcomes, add reviewed implicit evidence where justified,
then proceed to positioning triangulation and intervention tracking before research inference.
