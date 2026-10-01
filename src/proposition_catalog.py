"""Resolve reviewed labels without rewriting run context or guessing tested questions."""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping
from typing import Any

CATALOGUE_VERSION = "propositions-v1"

# A starter vocabulary, not evidence that any business offers these propositions.
STARTER_PROPOSITIONS = (
    ("balayage", "Balayage", ()),
    ("curly_hair", "Curly hair", ("Curly-hair expertise",)),
    ("bridal_hair", "Bridal hair", ("Wedding hair", "Bridal / wedding hair")),
    ("colour_correction", "Colour correction", ("Color correction",)),
    ("hair_extensions", "Hair extensions", ()),
    ("childrens_haircuts", "Children's haircuts", ("Children’s haircuts",)),
    ("quiet_appointments", "Quiet appointments", ()),
    ("private_dining", "Private dining", ()),
    ("wine_selection", "Wine selection", ("Wine list", "A great wine list")),
    ("family_friendly", "Family friendly", ("Family-friendly",)),
    ("coworking", "Co-working", ("Coworking", "Co working")),
    ("private_offices", "Private offices", ()),
    ("meeting_rooms", "Meeting rooms", ()),
    ("commercial_cleaning", "Commercial cleaning", ()),
    ("office_cleaning", "Office cleaning", ()),
    ("end_of_tenancy_cleaning", "End of tenancy cleaning", ()),
    ("carpet_cleaning", "Carpet cleaning", ()),
    ("upholstery_cleaning", "Upholstery cleaning", ()),
)


def label_key(value: str) -> str:
    """Case/spacing/typographic equivalence only; no stemming or fuzzy correction."""
    text = unicodedata.normalize("NFKC", str(value)).casefold().replace("’", "'")
    return re.sub(r"\s+", " ", text).strip()


def starter_catalogue() -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    catalogue, aliases = [], []
    seen = set()
    for key, label, alternative_labels in STARTER_PROPOSITIONS:
        catalogue.append({"proposition_key": key, "label": label, "catalogue_version": CATALOGUE_VERSION})
        for value in (label, *alternative_labels):
            normalized = label_key(value)
            if normalized in seen:
                continue
            seen.add(normalized)
            aliases.append({"alias_key": normalized, "alias_text": value, "proposition_key": key,
                            "catalogue_version": CATALOGUE_VERSION})
    return catalogue, aliases


def resolve_labels(values: Iterable[str] | None, catalogue: Iterable[Mapping[str, Any]],
                   aliases: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    known = {str(row["proposition_key"]): row for row in catalogue}
    matches: dict[str, set[str]] = {}
    for row in aliases:
        matches.setdefault(label_key(row["alias_text"]), set()).add(str(row["proposition_key"]))
    for key, row in known.items():
        matches.setdefault(label_key(row["label"]), set()).add(key)
    result = []
    for raw in values or []:
        candidates = matches.get(label_key(raw), set()) & known.keys()
        key = next(iter(candidates)) if len(candidates) == 1 else None
        result.append({"raw_label": raw, "proposition_key": key,
                       "label": known[key]["label"] if key else None,
                       "resolution": "resolved" if key else ("ambiguous" if candidates else "unresolved")})
    return result


def build_tested_intent_links(run: Mapping[str, Any], questions: Iterable[Mapping[str, Any]],
                        confirmed_question_map: Mapping[str, str], catalogue, aliases) -> dict[str, Any]:
    """Join the existing run context and confirmed reviewer mappings, without inferred volume."""
    context = resolve_labels(run.get("target_propositions"), catalogue, aliases)
    links = []
    seen = set()
    for question in questions:
        order = str(question.get("base_prompt_order") or question.get("prompt_order"))
        if order in seen:
            continue  # repeat rows are one sampled intent
        seen.add(order)
        raw = confirmed_question_map.get(order)
        resolution = resolve_labels([raw], catalogue, aliases)[0] if raw else {
            "raw_label": None, "proposition_key": None, "label": None, "resolution": "not_mapped"}
        links.append({**resolution, "question_order": order, "prompt_text": question.get("prompt_text"),
                      "mapping_basis": "reviewer_confirmed" if raw else "unknown"})
    return {"run_id": str(run["id"]), "context_status": "recorded" if context else "unknown",
            "context_source": "ai_visibility_runs.target_propositions", "run_context": context,
            "tested_questions": links}
