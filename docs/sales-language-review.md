# Documentation / sales-language review

Status: **corrected 30 October 2026** at Rob's request. Flagged 1 October 2026.

Three documents made claims the platform's evidence standards do not allow: rating cutoffs, guaranteed
inclusion, lost-revenue figures and proven mechanisms. They must not be "fixed" by encoding rating cutoffs,
guaranteed inclusion or estimated lost revenue in product logic.

## What was corrected

| Document | Claims removed or rewritten |
| --- | --- |
| `reports/1. Comprehensive_Local_AI_Visibility_Operating_Model.md` | 4.5+ star threshold; £2,000/month lost retainers; "systematically included"; "contracts routed to your competitors"; "first-mover advantage"; "whose revenue the client is losing"; "Prove ROI"; Cloudflare "September 2026" default; unscoped 79.8%, 78/80 and Yelp-deal figures |
| `reports/2. AI_Visibility_Implementation_Playbook_and_SOP.md` | 4.5+ threshold and "below 4.2 systematically excluded" (no source); primary category "single largest factor"; "direct data pipe" into ChatGPT; reviews as "verified semantic proof"; "89% of consumers and LLM evaluators" (no source); "exclusive" Yelp deal; Cloudflare "Content Independence Day" date; "LLMs penalize entity ambiguity"; unscoped Steady Demand, Seer, Murray Digital and Lily Ray figures |
| `src/generate_executive_pack_pdf.py` (the Executive Master Pack PDF) | The same claims, plus a page arguing that "Counts do not measure customers, sales, revenue" was a flaw to remove; "capture over 70% of high-margin contracts"; "the owner immediately books a call to stop losing revenue" |

Also corrected in all three: Cloudflare advice no longer suggests a user-agent bypass rule, which anyone can
fake; it points to verified-bot controls instead. Apple Business Connect is now Apple Business, and Siri's use of
it is described as undocumented.

## Basis for the figures that remain

Every remaining third-party figure is taken from the 20 September research notes ("LLM visibility levers
beyond website", kept locally by Rob), which link each source and grade its strength. The figures now state
their scope in the text: vendor or agency, sample size, country. The source pages were not re-read for this
correction. Two items rest on secondary reports only, and the documents now say so: the July 2026 Yelp
licensing deal, and Seer's 87% Bing alignment.

Two findings ran against the original claims:

- **Ratings.** In Steady Demand's index, AI-recommended businesses averaged 4.75 stars, below the 4.84 of ordinary
  search results. 90% were rated 4.5 or above. That describes who was recommended, not a cutoff.
- **Primary category.** Whitespark's expert panel ranked GBP primary category #34 for AI search, not first.

## Replacement language now used

"In our dated benchmark, these businesses were recommended for these prompts and providers."

"We observed gaps in the available public evidence. The proposed changes improve clarity and consistency;
compatible follow-up measurements will show whether AI visibility changes."

"This observation does not establish a rating cutoff, guarantee inclusion or measure lost sales."

## Still open

- Copies of the Executive Master Pack PDF made before this change still carry the old claims, including
  `reports/Local AI Discoverability - Executive Master Pack.pdf` (26 September, not in the repository).
  Regenerate it with `python src/generate_executive_pack_pdf.py`, and do not reuse earlier copies.
- The strategy in reports 1 and 2 predates the free check, client accounts and Final Beta report. This review
  corrected claims only, not strategy.
- This is not a full factual or legal verification. Pricing, process and DMCC statements were left as written.
