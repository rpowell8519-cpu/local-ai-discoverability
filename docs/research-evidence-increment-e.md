# Increment E: internal evidence research

The Evidence Research page builds downloadable business × family × provider/model × panel ×
wave rows from saved focused measurements. It reuses the monitoring recommendation counts and
frozen independent cohort, retaining eligible zero appearances. Historical runs without that
plan show explicit exclusions. Nothing is collected, written, paid for or added to client reports.
No migration is needed.

## Evidence timing and populations

Profile observations are selected at or before wave start. Source IDs, dates, hashes and adapter
versions remain visible. Legacy raw listing records are mutable: their timestamps and hashes do
not constitute an immutable historical profile archive. Published Google totals/ratings remain
separate from distinct collected review texts and reviewed proposition candidates.

Only captures archived by wave start qualify. Later copies of older-looking text cannot establish
historical exposure. Source retrieval dates determine freshness (default 90 days, adjustable).
Future publication/import dates are excluded. Missing dates, stale values and missing evidence
remain inspectable or unknown; they are not imputed as zero. Latest known sample review date is
not the platform's latest review, and platform review velocity remains unknown.

Proposition support uses only decisions recorded by wave start, with latest revisions as of that
time and distinct customer source records, not repeated excerpts or independent people. Partial
review, uncertain identity, unresolved families, stale source dates and contradictions prevent
support associations. Contradictions and review coverage remain visible. Current directory/alias
resolution is disclosed, and its linking records are exported; historical approvals are not invented.

## Exploratory analysis

The page separates exact panel/family/provider/served-model/mode/market/business-group strata.
Unknown served versions and incomplete answer grids cannot become eligible measurements. It
shows sample distributions, scatterplots and Spearman ranks, with row, business, wave and market
counts. Log1p review counts change only the display, not the Spearman test.

Bootstrap intervals resample canonical businesses with all their selected waves. At least ten
businesses are required by default; too many degenerate resamples withhold the interval. Small
samples, constant values, unequal wave coverage, excluded observations and multiple exploratory
comparisons are disclosed. These are selected-sample descriptions, not representative market
estimates, AI ranking factors, significance claims or causal effects.

## Reads and validation

The repository bounds selection to ten runs and batches evidence reads in a repeatable-read,
read-only transaction. Optional missing stores leave historical runs explicitly excluded. Only
captures needed for the chosen dates/cohort are loaded. The initial run selector shows the latest
100 runs. No new indexes or database changes are introduced.

Synthetic tests exercise as-of decisions/archives, stale/missing evidence, distinct populations,
zero appearances, model/identity exclusions, constant/tied ranks, clustered repeated waves,
small samples, incompatible strata, read-only repository behavior and the page's empty/historical/
analysis states. Production walkthroughs use database-enforced read-only connections.

Restart Streamlit after merging to load the new page. A real focused wave and human excerpt
reviews remain operational work; the existing pilot runs do not qualify as research observations.

Final clean-checkout validation of code commit `5ec70f6`: **884 passed, 73 subtests passed,
13 skipped, zero failures**. Compilation and dependency checks passed. Eight live read-only
walkthroughs covered Evidence Review, Positioning, Focused Monitoring and Evidence Research for
both Cisco and Wild Flor. Historical runs were explicitly excluded as expected. Counts remained
44 runs, 3,481 reviews, 2,390 raw listings, 99 report revisions, two captures, 112 observations,
and zero decisions, attempts, interventions or measurement waves. The additional report revision
relative to the earlier D walkthrough is the previously authorised Wild Flor owner brief, not QA.
