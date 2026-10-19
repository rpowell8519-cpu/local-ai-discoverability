"""The client account area (beta): the frozen, client-safe copy of one test that the website shows.

A published test holds counts only, never answer text. For each prompt: how many answers there were,
how many recommended the client (in each AI tool), the other businesses recommended and the websites
cited. Counts follow Final Beta: one appearance is the client in one completed answer's numbered list
of recommendations, matched by the names a person has confirmed for the client.

Nothing is decided here. The operator confirms or rejects every name in the answers that looks like the
client, groups the spellings of each competitor, and lists the client's own websites; those decisions
are saved with the published test and offered again for the next one (`carry_forward`). A name that
looks like the client and has not been decided stops publishing (`undecided_client_names`).
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any, Iterable, Mapping, Sequence

from src.ai_recommendation_intelligence import extract_numbered_recommendations
from src.final_beta_report import PROVIDER_ORDER, domain_of, name_patterns

VERSION = "client-account-test-v1"
MAX_COMPETITORS = 8
MAX_SOURCES = 8
EMPTY_DECISIONS: dict[str, Any] = {
    "client_names": [], "rejected_names": [], "short_name": "", "competitor_groups": {}, "own_domains": [], "prompt_sets": {}, "prompt_notes": {},
}


def clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _squash(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


def _provider(value: Any) -> str:
    text = str(value or "").strip().casefold()
    return next((name for name in PROVIDER_ORDER if name.casefold() == text), str(value or "").strip())


def _complete(row: Mapping[str, Any]) -> bool:
    return str(row.get("status") or "") == "completed" and row.get("response_complete") is not False


def recommended_names(row: Mapping[str, Any]) -> list[str]:
    """The businesses one answer recommended, each once, as the AI wrote them."""
    names = (clean(re.sub(r"\*+", "", str(item.get("raw_business_name") or "")))
             for item in extract_numbered_recommendations(str(row.get("raw_response") or "")))
    return list(dict.fromkeys(name for name in names if name))


def cited_domains(row: Mapping[str, Any]) -> set[str]:
    """The websites one answer cited. Google's tool gives the website only as the link title."""
    hosts = set()
    for cite in (row.get("report_metadata") or {}).get("citations") or []:
        host = domain_of(cite.get("url"))
        if not host or "vertexaisearch" in host:
            host = domain_of(clean(cite.get("title")))
        if "." in host and host not in {"uk.com", "co.uk", "org.uk"}:
            hosts.add(host)
    return hosts


def carry_forward(previous: Mapping[str, Any] | None, *, client_names: Iterable[str] = (), short_name: str = "",
                  own_domains: Iterable[str] = ()) -> dict[str, Any]:
    """The decisions to start from: the last published test's, else the client's reviewed report's names."""
    decisions = {key: (value.copy() if isinstance(value, (list, dict)) else value) for key, value in EMPTY_DECISIONS.items()}
    if previous:
        decisions.update({key: previous[key] for key in EMPTY_DECISIONS if key in previous})
    decisions["client_names"] = list(dict.fromkeys([*map(clean, decisions["client_names"]), *map(clean, client_names)]))
    decisions["client_names"] = [name for name in decisions["client_names"] if name]
    decisions["short_name"] = clean(decisions["short_name"] or short_name)
    decisions["own_domains"] = sorted({domain_of(d) for d in [*decisions["own_domains"], *own_domains] if domain_of(d)})
    return decisions


def _is_client(name: str, patterns: Sequence[re.Pattern[str]]) -> bool:
    return any(p.search(name) for p in patterns)


def undecided_client_names(rows: Iterable[Mapping[str, Any]], decisions: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Recommended names that look like the client but are on neither the confirmed nor the rejected list.

    A name looks like the client when it contains the client's short name or the first word of a
    confirmed name (four letters or more), ignoring case and punctuation. Names already matched by the
    confirmed list are not asked about again.
    """
    patterns = name_patterns(decisions.get("client_names") or [], decisions.get("short_name") or "")
    decided = {_squash(n) for n in [*(decisions.get("client_names") or []), *(decisions.get("rejected_names") or [])]}
    stems = {_squash(decisions.get("short_name"))} | {_squash(str(n).split()[0]) for n in decisions.get("client_names") or [] if str(n).split()}
    stems = {s for s in stems if len(s) >= 4}
    found: Counter[str] = Counter()
    for row in rows:
        if not _complete(row):
            continue
        for name in recommended_names(row):
            if _squash(name) in decided or _is_client(name, patterns):
                continue
            if any(stem in _squash(name) for stem in stems):
                found[name] += 1
    return [{"name": name, "answers": count} for name, count in sorted(found.items(), key=lambda item: (-item[1], item[0].casefold()))]


def competitor_names(rows: Iterable[Mapping[str, Any]], decisions: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Every other business the answers recommended, after grouping, with the answers that named it."""
    patterns = name_patterns(decisions.get("client_names") or [], decisions.get("short_name") or "")
    group_of = _group_lookup(decisions.get("competitor_groups") or {})
    counts: Counter[str] = Counter()
    spellings: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        if not _complete(row):
            continue
        seen = set()
        for name in recommended_names(row):
            # A rejected look-alike is some other business, so it stays among the competitors.
            if _is_client(name, patterns):
                continue
            label = group_of.get(_squash(name), name)
            spellings[label].add(name)
            seen.add(label)
        counts.update(seen)
    return [{"name": name, "answers": count, "spellings": sorted(spellings[name])}
            for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0].casefold()))]


def _group_lookup(groups: Mapping[str, Iterable[str]]) -> dict[str, str]:
    lookup = {}
    for label, names in groups.items():
        lookup[_squash(label)] = clean(label)
        for name in names:
            lookup[_squash(name)] = clean(label)
    return lookup


def project_test(rows: Iterable[Mapping[str, Any]], decisions: Mapping[str, Any], *, tested_on: str,
                 models: Mapping[str, str] | None = None) -> dict[str, Any]:
    """The published copy of one test day. Raises if a name that looks like the client is undecided."""
    rows = [dict(row) for row in rows]
    undecided = undecided_client_names(rows, decisions)
    if undecided:
        raise ValueError("Decide these names before publishing: " + ", ".join(item["name"] for item in undecided))
    patterns = name_patterns(decisions.get("client_names") or [], decisions.get("short_name") or "")
    group_of = _group_lookup(decisions.get("competitor_groups") or {})
    own = {domain_of(d) for d in decisions.get("own_domains") or [] if domain_of(d)}
    prompt_sets = {clean(text): clean(name) for text, name in dict(decisions.get("prompt_sets") or {}).items()}
    # A caution the operator wants read with a prompt's figures, e.g. answers about plant nurseries.
    prompt_notes = {clean(text): " ".join(str(note).split()) for text, note in dict(decisions.get("prompt_notes") or {}).items() if str(note or "").strip()}
    by_prompt: dict[str, list[dict[str, Any]]] = defaultdict(list)
    order: dict[str, tuple[int, int]] = {}
    for row in rows:
        text = clean(row.get("prompt_text"))
        by_prompt[text].append(row)
        order.setdefault(text, (int(row.get("run_order") or 0), int(row.get("base_prompt_order") or 0)))
    prompts = []
    for text in sorted(by_prompt, key=lambda t: order[t]):
        providers: dict[str, dict[str, int]] = {}
        competitors: Counter[str] = Counter()
        sources: Counter[str] = Counter()
        answers = recommended = own_cited = citing = 0
        for row in by_prompt[text]:
            if not _complete(row):
                continue
            names = recommended_names(row)
            listed = any(_is_client(name, patterns) for name in names)
            tool = providers.setdefault(_provider(row.get("provider")), {"answers": 0, "recommended": 0})
            tool["answers"] += 1
            tool["recommended"] += listed
            answers += 1
            recommended += listed
            competitors.update({group_of.get(_squash(n), n) for n in names if not _is_client(n, patterns)})
            hosts = cited_domains(row)
            citing += bool(hosts)
            own_cited += bool(hosts & own)
            sources.update(hosts - own)
        if not answers:
            continue
        prompts.append({
            "text": text, "set": prompt_sets.get(text) or "Other prompts", "answers": answers, "recommended": recommended,
            "providers": {name: providers[name] for name in [*PROVIDER_ORDER, *sorted(set(providers) - set(PROVIDER_ORDER))] if name in providers},
            "competitors": [{"name": n, "answers": c} for n, c in sorted(competitors.items(), key=lambda i: (-i[1], i[0].casefold()))[:MAX_COMPETITORS]],
            "sources": [{"domain": d, "answers": c} for d, c in sorted(sources.items(), key=lambda i: (-i[1], i[0]))[:MAX_SOURCES]],
            "own_site_answers": own_cited, "answers_with_sources": citing,
            **({"note": prompt_notes[text]} if text in prompt_notes else {}),
        })
    if not prompts:
        raise ValueError("This test has no completed answers to publish.")
    return {"version": VERSION, "tested_on": tested_on, "models": dict(models or {}), "prompts": prompts}


PLAN_STATUSES = {"proposed": "Proposed", "agreed": "Agreed", "in_progress": "In progress", "done": "Done", "not_doing": "Not doing"}
PLAN_FIELDS = ("number", "title", "timing", "owner", "status", "why", "what", "complete_when", "progress")


def clean_plan_actions(actions: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """An action plan's actions as the client sees them: numbered in order, each with a title and a known status."""
    cleaned = []
    for item in actions:
        action = {field: " ".join(str(item.get(field) or "").split()) for field in PLAN_FIELDS}
        if not action["title"]:
            continue
        action["status"] = action["status"] if action["status"] in PLAN_STATUSES else "proposed"
        cleaned.append(action)
    if not cleaned:
        raise ValueError("A plan needs at least one action with a title.")
    if len(cleaned) > 40:
        raise ValueError("A plan holds at most 40 actions.")
    for index, action in enumerate(cleaned, 1):
        action["number"] = action["number"] or f"{index:02d}"
    return cleaned
