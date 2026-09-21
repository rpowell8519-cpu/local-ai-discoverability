"""Reconcile the businesses a report talks about with the names the AI used for them.

The owner names competitors in their own words ("PLATF9RM"), the database holds Google's listing
name ("PLATF9RM Brighton - Coworking, Offices & Events"), and the AI answers use whichever short
form they like ("PLATF9RM", 25 times). Left alone, those are three different things, so a
competitor's visibility is under-counted and one of them is shown as an unverified stranger.

Nothing here decides anything. It finds the likely database businesses and the AI names that look
like the same business, and a reviewer confirms each. A name is only ever credited to a business
on that confirmation, and the same name can never be claimed by two businesses.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from src.ai_recommendation_intelligence import normalise_name
from src.business_lookup import near_misses, search_businesses
from src.report_identity import find_possible_target_names

TARGET_KEY = "target"
OWNER_KEY_PREFIX = "owner:"
NOT_IN_SYSTEM = ""  # the reviewer's answer when the owner's competitor has no database record
CONFIRMED_METHOD = "reviewer_confirmed_business_name"


class UndecidedNamesError(ValueError):
    """Raised when a name that may be a business, or an owner competitor, still has no decision."""

    def __init__(self, items: list[dict[str, Any]]):
        self.items = items
        parts = []
        for item in items:
            if item.get("name"):
                parts.append(f"“{item['name']}” ({int(item.get('recommendations') or 0)} answer(s)) for {item['subject']}")
            else:
                parts.append(f"which business in the database “{item['subject']}” is")
        super().__init__(
            "Some names still need a decision in the report review step: " + "; ".join(parts)
            + ". Otherwise a business could be reported under a name the AI did not use, or as absent from "
            "answers where it appeared."
        )


class ConflictingNameLinksError(ValueError):
    """Raised when one AI answer name is confirmed for two different businesses."""


@dataclass
class Subject:
    """A business whose look-alike AI names need deciding."""

    key: str                 # "target", a Google place ID, or "owner:<name>" for one not in the database
    label: str               # what to call it on the page
    place_id: str | None
    names: list[dict[str, Any]] = field(default_factory=list)  # flagged unresolved names to decide
    owner_name: str | None = None  # set when the owner named this business
    outside_set: bool = False      # a database business the AI's names resemble, not otherwise in this report


def owner_key(owner_name: str) -> str:
    return OWNER_KEY_PREFIX + " ".join(str(owner_name).split()).casefold()


def owner_competitor_candidates(
    owner_name: str, records: Iterable[Mapping[str, Any]], *, limit: int = 6
) -> list[Mapping[str, Any]]:
    """Database businesses the owner's competitor might be, best first."""

    records = list(records)
    found = list(search_businesses(records, owner_name, limit=limit))
    for extra in near_misses(records, owner_name, limit=limit):
        if extra not in found:
            found.append(extra)
    return found[:limit]


def default_owner_match(owner_name: str, candidates: Iterable[Mapping[str, Any]]) -> str | None:
    """A place ID only when exactly one candidate is named as the owner wrote it or starts with it."""

    wanted = normalise_name(owner_name)
    strong = [
        str(c["google_place_id"]) for c in candidates
        if wanted and (normalise_name(c.get("business_name")) == wanted or normalise_name(c.get("business_name")).startswith(wanted + " "))
    ]
    return strong[0] if len(strong) == 1 else None


def plan_subjects(
    *,
    target_id: str,
    target_name: str,
    unresolved: Iterable[Mapping[str, Any]],
    owner_names: Iterable[str],
    owner_places: Mapping[str, str],
    cohort_ids: Iterable[str],
    names_by_id: Mapping[str, str],
    records: Iterable[Mapping[str, Any]] = (),
) -> list[Subject]:
    """Every business whose AI names need deciding, each unresolved name claimed by at most one.

    Order matters: the target first, then the owner's competitors (matched against the owner's words
    and the database business chosen for them), then the other comparison businesses.
    """

    unresolved = [dict(item) for item in unresolved]
    claimed: set[str] = set()
    subjects: list[Subject] = []

    def flag(label: str, reference_names: list[str], *, owner_words: bool = False) -> list[dict[str, Any]]:
        found: dict[str, dict[str, Any]] = {}
        for reference in reference_names:
            for item in find_possible_target_names(reference, unresolved):
                if item["name"] not in claimed:
                    found.setdefault(item["name"], item)
            if owner_words:  # an AI name identical to what the owner typed is exactly the one to check
                for item in unresolved:
                    name = str(item.get("business_name") or "").strip()
                    if name and name not in claimed and normalise_name(name) == normalise_name(reference):
                        found.setdefault(name, {"name": name, "recommendations": int(item.get("recommendations") or 0),
                                                "reason": "Same as the name the owner gave"})
        claimed.update(found)
        return sorted(found.values(), key=lambda x: (-x["recommendations"], x["name"]))

    subjects.append(Subject(TARGET_KEY, target_name, target_id, flag(target_name, [target_name])))
    owner_pids: set[str] = set()
    for owner_name in owner_names:
        pid = str(owner_places.get(owner_name) or "") or None
        db_name = names_by_id.get(pid or "", "")
        subjects.append(Subject(pid or owner_key(owner_name), db_name or str(owner_name), pid,
                                flag(str(owner_name), [str(owner_name), db_name] if db_name else [str(owner_name)], owner_words=True),
                                owner_name=str(owner_name)))
        if pid:
            owner_pids.add(pid)
    for pid in dict.fromkeys(str(item) for item in cohort_ids):
        if pid == target_id or pid in owner_pids or pid not in names_by_id:
            continue
        subjects.append(Subject(pid, names_by_id[pid], pid, flag(names_by_id[pid], [names_by_id[pid]])))
    subjects += _outside_subjects(unresolved, claimed, {s.place_id for s in subjects if s.place_id}, records)
    return subjects


EXTRA_MIN_ANSWERS = 3       # a name the AI used at least this often is worth a look
EXTRA_NAMES_CONSIDERED = 15  # the most-used unmatched names
EXTRA_SUBJECTS_SHOWN = 6


def _outside_subjects(
    unresolved: list[dict[str, Any]], claimed: set[str], used_ids: set[str], records: Iterable[Mapping[str, Any]]
) -> list[Subject]:
    """Database businesses outside this report that a frequently used, still unmatched AI name may be.

    Without this, "Sauna Co" named in 15 answers stays an anonymous stranger when it is really a listed
    business that simply is not in the comparison set. A name is offered against each plausible business
    (the reviewer can confirm at most one), and only where the two names share what the existing
    look-alike test looks for.
    """

    seen: dict[str, Mapping[str, Any]] = {}
    for record in records:
        pid = str(record.get("google_place_id") or "")
        if pid and pid not in seen:
            seen[pid] = record
    if not seen:
        return []
    pool = list(seen.values())
    found: dict[str, Subject] = {}
    considered = sorted(
        (item for item in unresolved if str(item.get("business_name") or "").strip() not in claimed),
        key=lambda item: (-int(item.get("recommendations") or 0), str(item.get("business_name"))),
    )[:EXTRA_NAMES_CONSIDERED]
    for item in considered:
        if int(item.get("recommendations") or 0) < EXTRA_MIN_ANSWERS:
            continue
        for record in owner_competitor_candidates(str(item["business_name"]), pool, limit=3):
            pid = str(record["google_place_id"])
            if pid in used_ids:
                continue
            hit = find_possible_target_names(str(record.get("business_name") or ""), [item])
            if hit:
                subject = found.setdefault(pid, Subject(pid, str(record["business_name"]), pid, outside_set=True))
                subject.names.append(hit[0])
    ranked = sorted(found.values(), key=lambda s: (-sum(n["recommendations"] for n in s.names), s.label))[:EXTRA_SUBJECTS_SHOWN]
    for subject in ranked:
        claimed.update(n["name"] for n in subject.names)
    return ranked


def decisions_for(decisions: Mapping[str, Any], subject: Subject) -> tuple[list[str], list[str]]:
    """(confirmed, rejected) raw names saved for a subject."""

    if subject.key == TARGET_KEY:
        return list(decisions.get("confirmed_target_names") or []), list(decisions.get("rejected_target_names") or [])
    saved = dict((decisions.get("name_links") or {}).get(subject.key) or {})
    return list(saved.get("confirmed") or []), list(saved.get("rejected") or [])


def undecided_items(
    subjects: Iterable[Subject],
    decisions: Mapping[str, Any],
    owner_names: Iterable[str],
) -> list[dict[str, Any]]:
    """What still needs a person: unchosen owner competitors and flagged names with no decision."""

    places = dict(decisions.get("owner_competitor_places") or {})
    items: list[dict[str, Any]] = [
        {"subject": str(owner), "name": None} for owner in owner_names if str(owner) not in places
    ]
    for subject in subjects:
        confirmed, rejected = decisions_for(decisions, subject)
        decided = {*confirmed, *rejected}
        items += [
            {"subject": subject.label, "name": flagged["name"], "recommendations": flagged["recommendations"]}
            for flagged in subject.names if flagged["name"] not in decided
        ]
    return items


def name_adjudications(
    subjects: Iterable[Subject],
    decisions: Mapping[str, Any],
    owner_display: Mapping[str, str],
    *,
    target_method: str = "reviewer_confirmed_target_name",
) -> dict[str, dict[str, Any]]:
    """Slot adjudications crediting each confirmed name to its business.

    A business with a database record is credited by place ID. An owner competitor with no database
    record is credited to a single named group, so its several AI names count together without
    pretending its identity is verified.
    """

    result: dict[str, dict[str, Any]] = {}
    for subject in subjects:
        confirmed, _ = decisions_for(decisions, subject)
        display = subject.label if subject.place_id else owner_display.get(subject.key, subject.label)
        for raw in confirmed:
            if str(raw) in result and result[str(raw)]["google_place_id"] != subject.place_id:
                raise ConflictingNameLinksError(f"“{raw}” is confirmed for two different businesses.")
            result[str(raw)] = {
                "google_place_id": subject.place_id,
                "business_name": display,
                "resolution_method": target_method if subject.key == TARGET_KEY else CONFIRMED_METHOD,
            }
    return result


def confirmed_names_by_place(subjects: Iterable[Subject], decisions: Mapping[str, Any]) -> dict[str, list[str]]:
    """Confirmed names per database business, for crediting counts before a report is built."""

    grouped: dict[str, list[str]] = {}
    for subject in subjects:
        confirmed, _ = decisions_for(decisions, subject)
        if subject.place_id and confirmed:
            grouped.setdefault(subject.place_id, []).extend(confirmed)
    return grouped


def owner_competitor_entries(
    owner_names: Iterable[str],
    decisions: Mapping[str, Any],
    names_by_id: Mapping[str, str],
    counts_by_id: Mapping[str, int] | None = None,
) -> list[dict[str, Any]]:
    """The owner-nominated competitors as the report lists them, reflecting the reviewer's matches."""

    places = dict(decisions.get("owner_competitor_places") or {})
    counts = counts_by_id or {}
    entries = []
    for owner in owner_names:
        pid = str(places.get(str(owner)) or "")
        if pid and pid in names_by_id:
            recommendations = int(counts.get(pid, 0))
            entries.append({
                "owner_name": str(owner), "google_place_id": pid, "business_name": names_by_id[pid],
                "match_status": "matched", "match_score": 1.0, "recommendations": recommendations,
                "visibility_status": (f"Recommended {recommendations} time{'s' if recommendations != 1 else ''}"
                                      if recommendations else "Not recommended in this benchmark"),
            })
        else:
            entries.append({
                "owner_name": str(owner), "google_place_id": None, "business_name": str(owner),
                "match_status": "not_in_system", "match_score": 0.0, "recommendations": 0,
                "visibility_status": "Not in the business database; names the AI used for it are counted together",
            })
    return entries


def confirmed_by_place_from_decisions(decisions: Mapping[str, Any], target_id: str) -> dict[str, list[str]]:
    """Confirmed names per database business, read straight from the saved decisions.

    Used before any names have been looked up, so a report's counts already include them.
    """

    grouped: dict[str, list[str]] = {}
    target_names = [str(name) for name in decisions.get("confirmed_target_names") or []]
    if target_names:
        grouped[target_id] = target_names
    for key, saved in dict(decisions.get("name_links") or {}).items():
        confirmed = [str(name) for name in dict(saved).get("confirmed") or []]
        if confirmed and not str(key).startswith(OWNER_KEY_PREFIX):
            grouped.setdefault(str(key), []).extend(confirmed)
    return grouped


def disclosure_lines(subjects: Iterable[Subject], decisions: Mapping[str, Any]) -> list[str]:
    """One plain sentence per business that had AI answer names matched to it by the reviewer."""

    lines = []
    for subject in subjects:
        confirmed, _ = decisions_for(decisions, subject)
        if confirmed:
            who = "this business" if subject.key == TARGET_KEY else subject.label
            lines.append(f"Reviewer confirmed these AI answer names as {who}: " + ", ".join(f"“{name}”" for name in confirmed))
    return lines
