# Sonnet 5.5 search compatibility

The authorised Wild Flor baseline on 3 October 2026 stopped after its first request.
Anthropic returned HTTP 400: forced `tool_choice` (`tool` or `any`) is unsupported on
Sonnet 5.5. The read-only model-availability check had passed; it did not validate the
Messages request parameters. No completed answers were produced and the remaining
14 planned requests were not attempted. Token usage was unavailable; no billing claim
is inferred from that absence.

For exactly `claude-sonnet-5-5`, the adapter now sends `tool_choice: auto`. The existing
system instruction still requires live search and the response guard still rejects an
answer with no observed web-search tool invocation. Other models retain their existing
forced-search behavior. Output/search limits and retry behavior are unchanged. The three
provider hot-reload checks use the updated version marker so an open Streamlit session
loads the correction.

Source: [Anthropic's Sonnet 5.5 breaking changes](https://platform.claude.com/docs/en/models/sonnet-5-5/whats-new-sonnet-5-5),
checked 3 October 2026. This compatibility exception does not guarantee that every request
will search or complete; those remain response-level checks.

The failed wave is preserved. An adapter change changes the frozen panel fingerprint,
so prepare a new panel rather than rewriting or retrying the old wave with different
request behavior. No migration is required. No additional paid verification is bundled
with this fix. Regression tests mock provider responses, checking both searched and
unsearched answers and preservation of other model behavior.
