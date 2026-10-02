# Increment D: focused monitoring

## Behavior

The Focused Monitoring page prepares an exact question/family/provider/model/location/repeat
panel and an independently selected comparator cohort. All selected businesses must be canonical
identities in the same business group. The operator records geographic/service eligibility for
every family before seeing results. The plan can be downloaded without running or writing.
Unknown models, missing owner agreement and unassigned actions are not silently filled in.

An explicit paid-run control creates a `focused` wave through the existing run/query/runner
repositories. A's existing `ai_measurement_waves.configuration.settings` stores question families,
comparator IDs/basis, configuring operator and optional action links. Exact settings determine
panel/series identity; changing the cohort, family map, operator, action links or eligibility basis
starts a different configuration. No new table or migration is required. The main AI Visibility
latest-run selector and report-generator completed-benchmark selector exclude focused waves.
Historical core runs remain available in the monitoring inspector but cannot qualify as focused
before/after baselines. Existing attached reports and issued payloads are unchanged.

Missing/incomplete provider results may be explicitly retried against the same saved focused run.
Retry does not create a new wave or call already-completed answers. A changed adapter/configuration
blocks retry rather than silently reusing an incompatible series. If query creation itself was
interrupted, a new wave must be prepared; no queries/results are fabricated. Synchronous runs retain
the existing app's interruption limitations. Neither scheduling nor snapshot freezing is included.

## Counting and comparison

One appearance is one linked recommendation in one valid completed nonempty answer. Duplicate
slots do not add appearances. Raw target mentions/parser booleans do not determine counts.
The current canonical directory and saved aliases are read through the existing recommendation
resolver, with only exact/exact-group matches credited. Fuzzy matches remain unapproved; possible
names for a monitored business make its rate unknown, including a would-be zero. Resolution
records remain in the projection/export. This does not invent historical name approvals.

Expected denominators come from the frozen question/repeat/provider grid, including missing query
rows. Completed denominators exclude failures, truncations, blank answers and error-bearing records.
Missing queries, edited question text, duplicate answers, unexpected providers, fingerprint errors
and incomplete grids block strict comparison. Core/focused panels, different targets, different
series/configurations and reversed/same-run pairs cannot be compared. All returned model identifiers
are visible; missing, mixed or undated aliases cannot establish a fixed served model version.
A conservative date/version-suffix check is disclosed and does not verify internal model weights.

For a compatible pair, the target's appearance-rate change is shown in percentage points. The
contextual value subtracts the median eligible comparator change for the same family/provider/panel.
Comparators use those exact same contemporaneous answers, including independently selected zero
appearance businesses; businesses are never selected just because the model recommended them.
The minimum eligible cohort is operator-configurable, default three. Insufficient comparators retain
the target delta but suppress contextual change. Unknown target identity suppresses its delta.
This is descriptive context, not causal estimation; repeats are not independent experiments.

Structured citations remain preserved, including unknown citation coverage. Observed provider search
markers now persist separately from configured mode and citations. An absent marker is unavailable,
not a measured zero or proof of no search. Exports retain returned models, search markers and source
provenance. Old metadata is not backfilled. Selected archived source timestamps are compared with
the baseline/follow-up; archive time is never substituted for source retrieval time. Unknown or
post-baseline sources cannot stand in for baseline exposure. Action implementation dates, bundles,
overlap and unknown dates are flagged. Day-only implementation dates cannot resolve within-day order.

## Pilot and validation

The Cisco/Wild Flor continuation produced a local full-context review packet with 12 proposed
excerpt judgments and four validated investigation/action drafts. The mixed Cisco balayage review
was corrected to retain initial dissatisfaction and subsequent successful repair. Cisco's existing
completed question mappings were preserved; Wild Flor's proposed mappings/owner facts await
confirmation. These are proposals, not human approvals or agreed production interventions.
See [pilot record](evidence-pilot-2026-10-02.md).

Six live AppTest walkthroughs (Evidence Review, Positioning and Focused Monitoring for each pilot
business) passed using database-enforced read-only connections. Selecting historical before/after
runs exposed the missing panel metadata and blocked strict comparison. Pre/post counts matched:
44 runs, 3,481 reviews, 2,390 raw listing rows, 98 report revisions, two captures, 112 observations,
zero decisions, zero attempts, zero interventions and zero measurement waves.

Targeted synthetic tests exercise comparison eligibility, denominator loss/missing queries, served
model changes, raw mentions/duplicate slots, fuzzy identity, fixed zero comparator inclusion,
insufficient cohorts, action bundles/overlap, source timing, paid-control gating, exact-plan retry and
main-benchmark separation. All page writes/paid execution are mocked. No paid calls, new public
collection, decisions, interventions, migration application or historical backfill occurred in QA.

After merge, restart the Streamlit process so the new page and repository signatures are loaded.
No SQL deployment step is needed. A real paid focused wave and human pilot sign-off remain operator
tasks; they have not been represented as completed validation.
