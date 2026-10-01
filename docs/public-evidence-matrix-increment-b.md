# Increment B: saved-source matrix preview

Rob authorized continuing the evidence work on 1 October 2026. This first B slice is
implemented on `feature/evidence-foundations`, alongside the A work.
It does not apply a migration, persist new observations, collect evidence, call a model,
freeze a snapshot, change a report, commit or push.
Rob subsequently approved committing/pushing A and this preview for a feature PR; no merge or
additional schema application is implied.
Separately, Rob subsequently approved the A schema, now applied with its service-role permission
correction. See [A's applied state and live migration versions](evidence-foundations-increment-a.md).

## What this slice delivers

The Evidence Foundations page has a **Public evidence matrix** tab. It projects the latest
saved Google listing, latest attempted website audit, saved review samples and confirmed
platform links into separately labelled collection, fact and proposition tables.

* The repository uses a repeatable-read, read-only transaction. Google source selection is
  `created_at DESC, id DESC`; website selection is `started_at DESC, id DESC`, so an older
  successful audit does not silently conceal a newer failed attempt.
* Contact comparisons reuse the existing UK phone/postcode extraction. Exact and semantic
  equivalence, conflicts, missing values and unknowns remain distinct. A Google listing is
  a comparison observation, not approved canonical truth. Multiple different numbers remain
  unknown for operator adjudication. Capped text cannot establish a conflict or a missing value.
* Missing means missing **within the checked saved text**, not absent from the entire site.
  All source dates are visible; differences between dated captures are not claims about
  current business information.
* The reusable comparator also supports reviewed service-name aliases, fixed/from prices
  with service/currency context, and opening-hour observations with day/timezone/exception
  context. These are tested domain capabilities, not automatic price/hour extractors.
  Overnight schedules and ambiguous prose remain unknown in this version.
* Proposition extraction uses exact catalogue labels/reviewed aliases and sentence excerpts.
  Clause-level polarity hints distinguish negative and mixed/negated wording. Every phrase
  match remains `REVIEW_REQUIRED`: no automatic support or contradiction approval, no inference
  from whole-review stars, no model-generated primary evidence. Implicit meanings need later
  reviewed extraction; exact matching intentionally misses paraphrases.
* The same model supports salons, restaurants and other catalogue propositions. A matrix only
  shows propositions with phrase candidates. An omitted row is not evidence of an absent offer.
* Each observation preserves the canonical Place ID, source class, original record reference,
  public URL when available, capture and publication dates separately, exact value/excerpt,
  normalized fact where supported, adapter version and content hash. Review IDs are deduplicated
  within source/business, not across platforms. Identity confidence is explicitly not reassessed.
* `candidate_source_classes` counts sources with candidate phrases. Substantive evidence breadth
  stays unknown until evidence is reviewed; a repeated sentence is not additional corroboration.
* Existing manual empty platform checks are reused from reviewer revision JSON. Checked-empty
  has sample size zero; unchecked has unknown size. Linked profiles are not completed checks.
* Tested intent remains in the existing run-context/confirmed-question mapping tab. The matrix
  introduces no independent tested-intent flag or run field.

## What remains before Increment B is complete

This is a read-only projection, **not an immutable evidence archive**. Existing website/review
records can be updated by their existing collectors. The hash identifies the projected value
and provenance, but cannot restore a deleted/changed underlying source record. It must not be
used as a frozen report or research snapshot until the next persistence slice is implemented.

Next B work is an explicitly reviewed additive persistence design for source captures,
collection attempts and evidence decisions. It needs immutable primary capture payloads, dated
attempt/error histories, human support/contradiction decisions, identity handling, and links back
to existing source records. Reviewed customer support, owner claims and independent third-party
corroboration must remain distinguishable. No new tables are applied by this preview.

Only then should we calculate substantive proposition breadth, feed triangulation/interventions,
or expose compact report additions. Existing recommendations, issued reports and golden fixtures
are unchanged.

## Collection plan for subsequent research

Before purchasing broader data, define an eligible business cohort independently of AI answers,
including businesses with zero appearances. Document sector/catchment/selection rules, exact
benchmark panels and measurement dates. Collect comparable evidence for that cohort rather than
only extending the current client-plus-leaders diagnostic sample.

For each business/platform capture published profile metrics, the review sampling method/cap,
text sample size and dates, identity link, collection outcome, provenance and missingness. Keep
unsupported native rating scales explicit. Choose platforms by sector relevance; absence of a
platform is not a defect. Preserve evidence available as of each wave, and distinguish genuinely
independent corroboration from syndicated owner copy. Review extraction precision on operator-
labelled excerpts before using it to generate research features.

Pilot collection and inspect completeness/cost/identity errors before expanding. More reviews
improve per-business estimates; more independent businesses/markets strengthen comparison.
Repeated waves supply longitudinal evidence but are not independent businesses. Research
inference, sample-size decisions and any paid collection remain separate later work.

## Validation

Deterministic tests cover exact/semantic/conflicting contact facts, partial/unavailable sources,
service aliases, price ambiguity, day/timezone/hour exceptions, sentence/clause negation,
website-only/review-only/cross-source candidates, source-aware deduplication, stars ignored,
unknown breadth, explicit checked-empty, restaurant propositions, content hashes and read-only
query ordering. AppTest checks the real tab with mocked primary evidence and no write controls.

Validation completed on 1 October 2026: **746 passed, 73 subtests passed, 13 skipped**, zero
failures. The skipped live/opt-in checks were not enabled. Compilation, dependency checks and
`git diff --check` passed. Read-only AppTest walkthroughs against the configured database passed
for Cisco's Karma and Wild Flor, including the new matrix tab, with no errors or controls clicked.
The published historical metrics remained distinct from saved review-text sample counts.
The A wave table remained absent; no production migration or writes occurred.
That was the pre-approval walkthrough. Post-approval read-only walkthroughs also passed with
all four A tables present and the stored catalogue active; no B observations were persisted.
