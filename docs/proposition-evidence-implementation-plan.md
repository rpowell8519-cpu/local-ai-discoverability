# Proposition and evidence layer: revised implementation specification

Updated 1 October 2026 following the repository/document review and Rob's corrections.
This records the selected plan. The prerequisite coverage fix is merged. Increment A's schema
is applied following Rob's explicit approval; its code and the B preview are approved for a feature PR.
A–F below describe the staged plan.
Rob authorized starting local Increment A and subsequently continuing local evidence work;
see [its implementation and migration review](evidence-foundations-increment-a.md).
Rob previously authorized committing the prerequisite
fix and opening its own PR on `fix/platform-review-coverage`. The approved A migration and its
SELECT/INSERT permission correction are applied; no further schema changes, business-data writes,
paid collection or snapshot freezes are authorized by this document. Increment B now has
a local read-only saved-source matrix preview; durable observations/review decisions and C–F
remain future work. See [the preview and remaining B scope](public-evidence-matrix-increment-b.md).

## Product boundary

MEASURE → COMPARE → DIAGNOSE → ACT → REMEASURE. Preserve measured AI outcomes, observed
evidence, interpretation, hypotheses, proposed actions and subsequent outcomes separately.
No universal consistency score, proprietary ranking-factor claim or causal attribution from
an observed association. Cisco's Karma and Wild Flor remain regression cases; do not modify
their historical golden payloads to accommodate this work.

## Existing architecture to extend

The operator application is Streamlit, with domain/repository code in `src/`, PostgreSQL on
Supabase and durable reviewer briefs/decisions in append-only `report_audit_revisions`.
Canonical identity is `business_features.google_place_id`; similarly named empty tables are
not a replacement entity model. Existing run/query/result records retain repeated AI answers;
provider adapters already distinguish model memory from search-grounded measurement.
Website audits, review text and manually confirmed `business_platform_links` provide initial
evidence. Generic report assembly and owner findings already consume approved evidence
recommendations. Reuse those routes rather than introduce a second audit or report system.

Reuse owner `known_for`, `owner_context.priority_services`, `desired_searches` and reviewer
`question_priority_map`. Most urgently, **`ai_visibility_runs.target_propositions` is the
existing tested-intent link** (10 of 44 runs populated at this review). A proposition catalogue
must resolve/join its values, preserving original values and run IDs. Do not introduce a
parallel run-level tested-propositions column or silently overwrite the existing one.

Initial inspection found 2,330 canonical businesses, but evidence is much narrower: 47 with
website audits and 46 with stored review text. Research coverage is not yet a representative
cross-market cohort. Stored review samples include 63 Google texts for Cisco and 100 for Wild
Flor; these are not published review totals. Historical raw listings have some profile ratings
and totals, with their own collection dates, and must not be described as current metrics.

## Prerequisite: platform collection ambiguity

The former client-facing action inferred no platform presence from no stored review text.
Replace it with an explicit collection limitation, separate from observed fact or proposition
support. A confirmed profile URL establishes linked identity; it does not establish a completed
review-text check, published total or absence of reviews.

The local fix stores explicit completed empty checks (URL, date, explanation, method, count 0)
in existing reviewer revision JSON and captures computed source coverage with each reviewed
recommendation basis. Unchecked has `found_count = null`; collected samples have `checked, N`
and a separately labelled sampled count. This is usable text found/collected, never a claim
about the platform's published review total. Dates absent from old samples remain unknown.
The operator can clear a manual check by saving it unchecked. Changed profile URLs invalidate
old empty checks. Old sample-based presence actions require re-review for new generic reports.
Issued report snapshots remain unchanged. No migration is needed for this prerequisite.

Scoped local validation: 238 tests and 53 subtests passed across coverage, Streamlit reviewer flow,
generic assembly, evidence findings and report/PDF regressions. Two opt-in live Cisco/Wild Flor
production checks were skipped; their live golden payloads were not revalidated. Rob separately
reported a full-suite run: **687 passed, 73 subtests passed, 13 skipped, zero failures**.
Compilation and dependency checks also passed before preparing the prerequisite PR.
Existing approved platform-presence actions
need operator re-review; automatic collectors do not yet persist empty/failed attempt records.
That broader collection-attempt model remains Increment A/B work.

## Three separate status dimensions

| Dimension | Initial values | Meaning |
|---|---|---|
| Collection | NOT_CHECKED, COLLECTED, CHECKED_EMPTY, FAILED, UNAVAILABLE | What was attempted and obtained; retain attempts/errors and dates |
| Fact comparison | MATCH, SEMANTIC_MATCH, CONFLICT, MISSING, UNKNOWN, NOT_APPLICABLE | Comparison of a named contextual fact with an approved reference |
| Proposition evidence | EXPLICIT_SUPPORT, IMPLICIT_SUPPORT, CONTRADICTS, NO_SUPPORT_FOUND, UNKNOWN | What available evidence supports; not a ranking score |

Do not use MISSING/NO_SUPPORT_FOUND until adequate collection happened. A failed retrieval is
UNKNOWN evidence. Owner-unconfirmed positioning is unknown, not a rejection of a proposition.
Google is one observed source, not the automatic truth for every fact. Prices preserve fixed
versus “from”, currency and service context; hours preserve day, timezone and exceptions.

## Measurement vocabulary

* **Panel:** versioned exact prompts, provider/model configuration, modes, tool settings,
  location assumptions and weights. Core and focused panels have distinct identities.
* **Wave:** one dated execution of a panel, with repeat eligibility and completion recorded.
* **Series:** compatible waves of a frozen panel/configuration for longitudinal comparison.

A new focused variant does not enter historical core denominators. A material prompt, model,
mode or methodology change starts a new compatible series; an unresolved model version is
flagged. Cadence is configurable. Weekly web-enabled focused waves can accompany monthly
core waves without mixing model-memory and web-enabled outcomes.

## Increment A: foundations and tested-intent linkage

Extend the existing business/run/query/reviewer structures. Proposed additions are a
vertical-neutral proposition catalogue with reviewed aliases, review profile metric history,
and panel/wave/series metadata attached to existing runs and queries. Reuse source profiles
where existing links suffice; additions must retain identity confidence and provenance.
Derive sample sizes from review text separately from published rating/count observations.

**Resolve existing `target_propositions` values to catalogue IDs**, retaining unresolved labels
and original JSON. Historical nulls stay unknown. Existing `question_priority_map` and exact
query text identify which question tests which proposition; a run's context list alone does
not prove every proposition was actually tested. Test current discovery-run writes and the
visibility-run creation path so future populated values use the same field consistently.
Do not repopulate historical runs without inspectable evidence.

Proposed schema changes are additive and optional: catalogue/alias tables, dated profile
metric observations and panel/series metadata plus run-wave/query-family links. Final SQL and
constraints must be presented after inspecting the then-current schema, before application.
No historical totals or review velocity invented from capped samples.

## Increment B: normalized evidence and consistency matrix

Add immutable raw/source observations, typed fact observations and proposition-to-evidence
links, referencing canonical Place IDs and existing audits/review records where possible.
Retain source URL/platform ID, capture time, raw/normalized value, extractor version, evidence
ID/hash, identity confidence and freshness. Adapters collect and normalize; diagnostics compare.

**Join propositions against `ai_visibility_runs.target_propositions` from A** for tested-intent
context, then show confirmed family/question mappings. The evidence UI must display collection
status separately from fact comparison and proposition support, including underlying sources.
Do not build a new independent tested-intent flag on business propositions.

Evidence breadth counts distinct source classes with substantive support, with owner claims,
customer corroboration and third-party corroboration distinguishable. Repeated or syndicated
owner copy does not become independent corroboration. LLM summaries reference primary evidence
IDs and never replace it. Add sentence-level review support/contradiction with negation handling;
whole-review stars do not determine sentiment toward each proposition. Begin with existing
website, Google profile/reviews, Yelp and TripAdvisor data; booking sources follow as adapters
when collection is defensible. Do not build every directory adapter before proving usefulness.

## Increment C: triangulation and interventions, before research UI

Show intended positioning, customer-perceived support and tested intent separately. Transparent,
configurable rules can suggest strategic core, hidden strength, unproven ambition, customer
strength or market opportunity; display the observations and thresholds behind each suggestion.
Weak support for a tested intent is not a recommendation to pretend the business offers it.

Introduce the smallest reusable intervention/action record now: proposition, finding, hypothesis,
affected evidence/source IDs, owner, priority/effort, status, planned/implemented dates, completion
evidence, baseline series and focused families. Keep simultaneous actions as explicit bundles.
Use existing approved action IDs as links; do not duplicate approved recommendations or invent
historical implementation dates. Intervention persistence is an additive schema proposal.

## Increment D: focused monitoring and before/after

Execute optional focused panels separately from canonical benchmarks. Preserve citations and
actual tool use where providers supply them. Add compatibility checks before comparisons and
show denominator/completion differences, provider/model changes and evidence freshness.
Compare target movement with an eligible contemporaneous cohort for the same family/provider/
panel. Target delta minus median comparator delta supplies context, not a causal estimate.
Flag bundles, insufficient comparators and overlapping changes. No autonomous paid scheduler
or snapshot freeze is part of the first increment.

## Increment E: internal research dataset, then exploratory UI

Build inspectable rows at **business × prompt family × provider/model × panel version × wave**;
series links waves. Repeats contribute appearances/eligible repeats, not independent customers.
Include verified zero-appearance businesses from independently defined eligible markets, alongside
verified recommended businesses. Selecting only recommended businesses biases associations.
Exclude unresolved entities and show evidence completeness and selection rules.

Use evidence available as of the wave: published review count/rating, recency, genuine recent
activity where coverage permits, sample size/support rates and source breadth/conflicts. A latest
sample date is “latest known in sample”, not necessarily the platform's latest review. Missing
citations or missing facts are not zero. Keep modes, markets/verticals and compatible provider/
model groups separate. Do not reuse today's evidence for yesterday's exposure without a flag.

Begin with distributions, N/unique businesses/markets, scatterplots and Spearman associations.
Raw and log1p review counts give identical Spearman ranks; log scale helps visualization, not an
independent correlation test. Use cluster-aware bootstrap intervals when coverage permits, rather
than resampling repeated rows as independent businesses. Flag small N, constant features,
multiple exploratory comparisons and unequal coverage. Descriptive output can ship before the
sample supports inferential analysis; no client-facing “ranking factors” screen.

## Increment F: compact report additions

After operator evidence is stable, add traceable consistency/proposition gaps and corroboration
summaries to the optional report layer. Every action connects measurement → evidence →
interpretation → action → follow-up measure. Keep research associations internal. Existing
reports and immutable payloads must continue rendering; no complete PDF redesign.

## Migration risks and verification

Do not point new foreign keys at empty duplicate entity tables, conflate review platform IDs,
silently normalize ambiguous proposition labels or backfill unavailable historical observations.
Review uniqueness currently needs platform context when IDs overlap; plan an additive correction
without modifying legacy frozen reviews. Prefer versioned optional evidence payloads and null
historical values. Preview every migration and bounded backfill before seeking explicit approval.

Each increment needs deterministic offline tests and a Cisco/Wild Flor walkthrough. Cover source
unknown versus checked empty versus failed, exact/semantic/conflicting facts, price/hour context,
source-specific proposition support/contradiction, triangulation unknowns, total/sample separation,
existing `target_propositions` resolution, core/focused denominators, incompatible before/after,
unresolved/zero-appearance cohort inclusion, known Spearman results and small-N handling. Reuse
existing Streamlit AppTest and report regressions; no paid provider/collector calls in tests.
Report files/schema changes, actual checks, limitations and operator decisions after each increment.

First success criterion: Cisco and Wild Flor produce better evidenced decisions with manageable
operator time. Research scale follows reliable identity, collection and temporal coverage.

## Separate documentation work

Reports 1 and 2 contain sales/methodology claims that conflict with these principles. Their
review notices point to [the sales-language issue](sales-language-review.md). This is a
documentation/account-management correction, not a change to ranking weights or product code.
