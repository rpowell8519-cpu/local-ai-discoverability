# Increment F: compact report additions

Built on `feature/report-additions-increment-f` (branched from `main` at `a582727`, after PR #26).
Read-only against already-reviewed evidence: this adds no new judgment, no schema, and no
collection. It projects decisions a human operator already made in Evidence Review / Positioning
(Increments B/C) into an optional, reviewer-gated section of the client summary (LS). Not merged
or pushed; not yet committed locally either (see "Working-tree note" below).

## What this delivers

- `src/positioning_report_summary.py` (`build_positioning_candidates`) reuses
  `positioning_triangulation.triangulate` exactly as `app/pages/13_Positioning.py` already does,
  reading the business's latest archived capture, its reviewed decisions, its owner brief and the
  report's own attached benchmark run (never an arbitrary one, so "tested intent" stays consistent
  with the report's own AI-visibility numbers). It returns only rows with a reportable triangulation
  suggestion (`STRATEGIC_CORE`, `HIDDEN_STRENGTH`, `CUSTOMER_STRENGTH`, `UNPROVEN_AMBITION`,
  `CONFLICTED_EVIDENCE`) or at least one recorded intervention — a bare `NEEDS_REVIEW` row with no
  linked action is operator triage noise, not client content, and is dropped. Raw excerpt text,
  evidence IDs and review identities never leave this module; only the proposition label, the
  triangulation reason, support counts and an intervention's status/hypothesis/dates do.
- A new, explicitly reviewer-gated step in `app/pages/10_AI_Report_Generator.py` (step 5, mirroring
  the existing recommendation-candidate pattern exactly): each candidate is shown with an
  include/undecided/leave-out radio, defaulting to undecided. "Complete report review" is blocked
  while any positioning candidate is undecided, the same way it already blocks on undecided
  recommendations, open names or unresolved waivers. Decisions persist in
  `reviewer_decisions["positioning_summary_decisions"]`; only `include`d candidates are copied into
  `reviewer_decisions["approved_positioning_summary"]`. Nothing reaches a report without an
  explicit reviewer choice.
- `src/poc_audit_generic.py` copies `approved_positioning_summary` into
  `owner_report["positioning_summary"]`, the same mechanism already used for
  `evidence_recommendations`/`recommendation_basis`/`type_wording`.
- `src/client_summary/adapter.py` (`_positioning_summary`) turns each approved candidate into
  fixed, plain-English wording keyed by its suggestion label (e.g. "You named this as a priority,
  but the reviewed customer evidence does not yet support it" for `UNPROVEN_AMBITION`) — never the
  raw suggestion enum or raw reason string. An unrecognised suggestion value is dropped
  defensively rather than rendered as-is. Capped at six rows.
- `src/client_summary/pdf.py` (`render_positioning`) adds one new, fully optional page, rendered
  only when `positioning_summary` is non-empty. Page number is 10 normally, 13 when the business
  also has the three existing review pages; `TOTAL_PAGES + extra` already accounted for an
  optional 3-page review block, now also a conditional 1-page positioning block. A report with no
  approved positioning evidence (the overwhelming majority of reports today, since no business has
  gone through Evidence Review yet) renders byte-for-byte as before — confirmed by test, not
  assumed.

## What was deliberately not built

- The RP (full evidence) report's equivalent addition. `poc_audit_pdf.py` uses a different,
  absolute-canvas rendering style; AGENTS.md already flagged RP's own mentioned-vs-recommended gap
  as deserving separate care rather than folding into an LS-focused pass, and the same reasoning
  applies here.
- Any new reviewer judgment. The triangulation suggestion and any intervention record already
  existed, already reviewer-made, before this increment; this only decides whether an *already
  made* decision is copied into a client deliverable.
- Statistical/correlation content from Increment E. Only Increment C's evidence-backed
  triangulation reaches this page; Evidence Research stays internal, as the product principles
  require.

## Tests

- `tests/test_positioning_report_summary.py`: no capture → `[]`; capture with no decisions at all
  → still correctly filtered (not a special case); a reportable suggestion becomes a candidate with
  no raw excerpt/evidence-id leakage; a bare `NEEDS_REVIEW` row with no linked intervention is
  dropped; a recorded intervention makes its proposition reportable even with zero reviewed
  decisions (deliberate); intervention storage not yet applied is treated as no interventions, not
  an error.
- `tests/test_client_summary_positioning.py` (mirrors the existing
  `test_client_summary_mentions.py` end-to-end pattern against `synthetic_owner_services_payload`):
  the default fixture (no positioning data) stays inert and keeps its existing page count; an
  unrecognised suggestion label is dropped; an approved finding renders its own extra page with the
  right page numbering; a recorded action's status and hypothesis appear beside its finding; more
  than six candidates are capped at six.

## Validation

Full suite from a clean working tree on this branch: **918 passed, 73 subtests passed, 13 skipped,
zero failures** (independently run, not just reported). `python -m compileall -q app src`: clean.
`python -m pip check`: no broken requirements. `git diff --check`: clean. The 11 new tests above are
included in that total; every pre-existing test, including the Cisco's Karma and Wild Flor LS/RP
regression fixtures, is unaffected.

## Working-tree note (2026-10-06)

This branch was built in the same local checkout as an unrelated, concurrently active session
working on a separate `feature/free-check-identity-and-email` branch. A branch checkout made while
that session had uncommitted changes in progress caused both sessions' uncommitted work to become
briefly visible on whichever branch was checked out at a given moment. No commits were lost or
cross-contaminated — `git add -A` was caught and reverted before anything was staged, and this
branch's own files were never added to the other session's commit. As of writing, this increment's
files exist only as uncommitted changes in the working tree; they have deliberately not been
`git add`ed or committed yet, to avoid racing with the other session's own pending commit. Commit
this branch's exact file list (not `-A`) once the working tree is confirmed to hold only one
session's changes at a time:

```
app/pages/10_AI_Report_Generator.py src/client_summary/adapter.py src/client_summary/pdf.py
src/poc_audit_generic.py src/positioning_report_summary.py tests/test_client_summary_positioning.py
tests/test_positioning_report_summary.py docs/report-additions-increment-f.md
```
