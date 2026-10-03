"""Customer-safe summary of one free visibility check.

Pure functions over saved answers. The unit throughout is the answer: one provider's completed,
valid response to one question. A business is counted once per answer whose numbered
recommendations include it, so rates are recommendations per valid answer and do not sum to 100%.
Missing or failed answers reduce the denominator; they are never treated as zero recommendations.
Nothing here carries raw answer text, internal identifiers or reviewer data.
"""
from __future__ import annotations

from typing import Any

PROJECTION_VERSION = "free-check-projection-v1"
TOP_BUSINESSES = 5
# A combined ranking is only shown when most answers arrived and no provider is absent.
MINIMUM_COVERAGE = 2 / 3


# Listing matches trusted enough to merge spellings under one business. A fuzzy match is not.
CONFIDENT_RESOLUTIONS = {"exact", "exact_group"}


def _flag(value: Any) -> bool:
    """True only for a real true. Saved rows pass through pandas, where a missing flag is NaN."""
    return value is not None and value == True  # noqa: E712 - NaN and None must both be false


def _valid(result: dict[str, Any]) -> bool:
    return result.get("status") == "completed" and _flag(result.get("response_complete"))


def _name_key(name: str) -> str:
    return " ".join("".join(c.lower() if c.isalnum() else " " for c in str(name or "")).split())


def build_projection(*, business_name: str, questions: list[str], providers: list[str],
                     queries: list[dict[str, Any]], results: list[dict[str, Any]],
                     recommendations: list[dict[str, Any]], target_id: str,
                     measured_at: str, benchmark_mode: str) -> dict[str, Any]:
    order_by_query = {str(q["id"]): int(q.get("base_prompt_order") or q.get("prompt_order") or 0) for q in queries}
    valid = [r for r in results if _valid(r) and str(r["query_id"]) in order_by_query]
    valid_keys = {(str(r["query_id"]), str(r["provider"])) for r in valid}
    expected = len(questions) * len(providers)

    def count(rows, **match):
        return sum(1 for r in rows if all(r.get(k) == v for k, v in match.items()))

    target_rows = [{"order": order_by_query[str(r["query_id"])], "provider": str(r["provider"]),
                    "recommended": _flag(r.get("target_recommended")),
                    "mentioned": _flag(r.get("target_mentioned")) or _flag(r.get("target_recommended"))}
                   for r in valid]
    target_recommended = count(target_rows, recommended=True)

    # Other businesses: one count per valid answer, grouped by resolved listing when there is one.
    groups: dict[str, dict[str, Any]] = {}
    for rec in recommendations:
        key = (str(rec.get("query_id")), str(rec.get("provider")))
        place_id = str(rec.get("google_place_id") or "")
        if key not in valid_keys or place_id == target_id:
            continue
        raw_name = str(rec.get("raw_business_name") or "").strip()
        resolved = bool(place_id) and rec.get("resolution_status") in CONFIDENT_RESOLUTIONS
        group_key = "id:" + place_id if resolved else "name:" + _name_key(raw_name)
        if group_key == "name:" or _name_key(raw_name) == _name_key(business_name):
            continue
        group = groups.setdefault(group_key, {
            "name": str(rec.get("business_name") or raw_name) if resolved else raw_name,
            "identity": "matched" if resolved else "unverified", "answers": set()})
        group["answers"].add(key)

    ranked = sorted(groups.values(), key=lambda g: (-len(g["answers"]), g["name"].lower()))
    businesses = [{"name": g["name"], "answers": len(g["answers"]), "identity": g["identity"], "is_target": False}
                  for g in ranked[:TOP_BUSINESSES]]

    per_provider = [{"provider": p,
                     "expected": len(questions),
                     "valid": count(target_rows, provider=p),
                     "target_recommended": count(target_rows, provider=p, recommended=True)}
                    for p in providers]
    per_question = [{"order": i, "text": text,
                     "valid": count(target_rows, order=i),
                     "target_recommended": count(target_rows, order=i, recommended=True)}
                    for i, text in enumerate(questions, start=1)]

    adequate = (expected > 0 and len(valid) >= expected * MINIMUM_COVERAGE
                and all(p["valid"] > 0 for p in per_provider))
    rank = None
    if adequate:
        ahead = sum(1 for g in ranked if len(g["answers"]) > target_recommended)
        tied = sum(1 for g in ranked if len(g["answers"]) == target_recommended)
        rank = {"position": ahead + 1, "of": len(ranked) + 1, "tied_with": tied}

    caveats = ["Results come from API checks on one date; consumer AI apps and later dates can differ.",
               "Business names are matched automatically. A name the check could not match is shown as "
               "unverified, and is never counted as your business."]
    if len(valid) < expected:
        caveats.append(f"{expected - len(valid)} of {expected} answers were not completed and are excluded.")
    if not adequate:
        caveats.append("Too few answers completed to show a combined ranking.")

    return {
        "schema_version": PROJECTION_VERSION,
        "measured_at": measured_at,
        "benchmark_mode": benchmark_mode,
        "expected_answers": expected,
        "valid_answers": len(valid),
        "target": {"name": business_name,
                   "recommended_answers": target_recommended,
                   "mentioned_answers": count(target_rows, mentioned=True),
                   "recommendation_rate": round(target_recommended / len(valid), 4) if valid else None},
        "rank": rank,
        "businesses": businesses,
        "providers": per_provider,
        "questions": per_question,
        "caveats": caveats,
    }
