# Cisco's Karma and Wild Flor evidence pilot

Rob authorised “merge and then pilot, then on to c” on 1 October and resumed the work on
2 October. Fresh origin fetch confirmed B merged in PR #16 (`c28c1af`). The interrupted
session had created the C branch and inspection script but no archives or review decisions.

## What actually happened

On 2 October the explicit B writer archived only the two authorised businesses. Source
records were read in repeatable-read transactions. Returned captures were reloaded and their
preserved bytes/hash verified. Identical Cisco evidence reused its existing capture after a
console-output serialization error; no duplicate capture was made.

| Business | Capture ID | Saved reviews | Saved pages | Proposition candidates |
|---|---|---:|---:|---:|
| Cisco's Karma | `0f8a41b5-f4b3-4afc-b460-6caafda6e7f6` | 69 | 10 | 30 |
| Wild Flor | `ba111425-7af9-4cb0-8c08-b83fd852e322` | 100 | 10 | 45 |

Hashes: Cisco `dbfdce62dd8b333a72acc6e05582fbf15958d3b04512542f24722234e7c4176f`;
Wild Flor `dce66dc4f44d70acfb088016e4e4e586bdb801be6b6a71c42f51b2c8956382fb`.
Archive time is not source retrieval time. There are 112 normalized observations, including
the 75 proposition candidates. No new collection occurred; collection-attempt count remains zero.

The review packet below is **Codex's provisional assessment**, for an operator to inspect in
Evidence Review. No assessment has been entered as a human approval. The production decision
table remains empty. The archive/page workflow is exercised; operator sign-off is still outstanding.

## Review packet

IDs below are suffixes of `saved-evidence-matrix-v2:`. Each refers to its named capture, and
the UI shows the exact excerpt, original record, dates and preserved full context.

| Business / proposition | Evidence ID suffix | Provisional assessment and operator check |
|---|---|---|
| Cisco / balayage | `e353552645ee85ae98baf2305ac758fb5cd768a4299936c6841d71c5bae009b8` | Owner website explicitly describes balayage; owner claim, not customer corroboration. |
| Cisco / balayage | `bdd79e44a3a4c967379cf3ab178e255f21c390439849256fd47936cbbba0e566` | Customer describes receiving balayage and returning to that stylist; likely explicit customer support. Confirm the complete preserved review and business identity. |
| Cisco / balayage | `3e85d44bd4c8f839569940af7bc034db04cb07c579d0990f32a14669fec2d607` | Customer describes receiving the service, with positive hospitality; support for service experience, not proof of exceptional technical expertise. |
| Cisco / bridal hair | `e07519fdf22dff616c869c8108e1ff40b0a44b260414cbec16ce8f7e346a0c13` | Yelp reviewer describes the owner's wedding service; customer-reported offering, but does not establish that this reviewer received it. Retain that scope. |
| Cisco / bridal hair | `7e6d62fad4c20f4221bb9fb90a83ed1bb0dd86b88372f6b1be01de2f0fede559` | Customer praises wedding styling. Inspect the full review to resolve whom “she” refers to. |
| Wild Flor / wine | `f414b86dc5d6696f838d665b4486c3f7050ed500f870c93a32a8d5dc7f9caf12` | Explicit positive customer statement about the wine list; likely support after identity/context confirmation. |
| Wild Flor / private dining | `12e9f63f6104c5890f00f97478a00ec9203990ba11e2582d52efb4292f995127` | Customer describes an actual private-dining event with 18 guests; likely explicit support for the experience. |
| Wild Flor / private dining | `635aa9803de882f4f64a28eebefa06797a79df3e007ea4bce12c511ee5fab841` | Website describes an offer and minimum spend. The negative hint comes from “don't need to break the bank”; it is not a contradiction. Retain original seasonal/price context. |
| Wild Flor / private dining | `5fc56fff63d8b9d8cc882871d25fa311a26c0ec3d679990de89033b216fd916b` | Navigation includes the phrase while the voucher page says no results. It provides no substantive private-dining proposition support; do not treat the negative hint as contradiction. |

## What the pilot changed about C

Cisco has three customer balayage candidates and two bridal candidates across Google/Yelp,
beside 25 website candidates. Multiple website pages repeat owner copy. Wild Flor has 15
customer wine candidates and three private-dining candidates, beside 27 website candidates.
These are excerpt counts, not approved support, independent witnesses or published review totals.

C therefore counts distinct reviewed source records per proposition, keeps origin distinctions,
ignores stars and polarity hints, and requires affirmative decisions before suggesting strengths.
Operator judgments on one sentence do not approve another sentence or another capture.

Cisco's current owner revision resolves Balayage and Bridal hair. Five other labels remain
unresolved, including singular “Hair extension”; no fuzzy alias was silently added. Its completed
question map links question 5 to Bridal hair and question 7 to Balayage. Those links remain usable
even though the latest run's `target_propositions` is empty. Unresolved question mappings prevent
claims that other catalogue propositions were not tested.

Wild Flor has no saved owner brief or completed question map. The run's context records private
dining and wine, and its prompt wording is visible, but C keeps owner intent and tested links
unknown until confirmed. A run context entry is not an independently confirmed question mapping.

Neither business currently receives an approved positioning category. Both correctly show
NEEDS_REVIEW. The next operator task is the short excerpt review above, followed by missing
owner vocabulary/question confirmations. No historical golden report payload was modified.

## Read-only verification

Evidence Review and Positioning passed live AppTest loading for both businesses. Selecting the
existing benchmark on Positioning also passed. All connections used a database setting refusing
writes; no form was submitted. Pre/post counts matched: 44 runs, 3,481 reviews, 2,390 raw listing
rows, 98 report revisions, 2 captures, 112 observations, zero decisions and zero attempts.
These checks test loaded database/page behavior; they do not assert an operator approved evidence.
