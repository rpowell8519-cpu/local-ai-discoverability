"""Link each tested question to the owner priority it covers.

The owner's priority services and the customer questions are written separately, so
nothing records which question tests which service. Without that link the report can
only say "coverage not mapped" for every service. A reviewer confirms the link in the
report review step. Suggestions come from shared wording and are never applied without
that confirmation.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any

from src.ai_recommendation_intelligence import normalise_name

NOT_LINKED = "Not linked to one priority"
GENERAL_GROUP_NAME = "General questions (not tied to one priority)"

_FILLER_WORDS = frozenset({
    "a", "an", "and", "any", "are", "around", "at", "best", "book", "can", "cheap",
    "find", "for", "good", "great", "hire", "host", "i", "in", "is", "it", "me", "near",
    "of", "offers", "on", "or", "place", "recommend", "recommended", "rent", "the", "to",
    "top", "us", "want", "what", "where", "which", "who", "with", "brighton", "hove",
    "sussex",
})


def _stem(word: str) -> str:
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _token_list(value: str) -> list[str]:
    """Meaningful words in order, lightly stemmed."""

    return [
        _stem(word)
        for word in normalise_name(value).split()
        if word not in _FILLER_WORDS and len(word) > 1
    ]


def _covers(question: set[str], joined: set[str], priority_tokens: list[str], token: str) -> bool:
    """Whether the question contains this word of a priority, allowing "co working" for "coworking"."""

    if token in question or token in joined:
        return True
    # A priority written "Co-working" is satisfied by "coworking" in the question.
    return any(
        token in (first, second) and first + second in question
        for first, second in zip(priority_tokens, priority_tokens[1:])
    )


_MIN_COVERAGE = 0.5


def suggest_priority(question: str, priorities: Iterable[str]) -> str | None:
    """The one priority the question clearly tests, judged on words distinctive to that priority.

    A word shared by several priorities ("working", "space") says little about which one a question
    is for, so a priority is scored on the words no other priority uses. It needs at least half of
    them, and it must beat every other priority. When it is not clear the answer is None and a
    reviewer decides: a wrong suggestion that gets accepted misgroups a client's results.
    """

    listed = [str(p) for p in priorities if str(p).strip()]
    tokens = {priority: _token_list(priority) for priority in listed}
    frequency = Counter(word for words in tokens.values() for word in set(words))
    question_words = _token_list(question)
    known = set(question_words)
    joined = {a + b for a, b in zip(question_words, question_words[1:])}
    scored = []
    for priority, words in tokens.items():
        if not words:
            continue
        distinctive = [word for word in words if frequency[word] == 1] or words
        covered = sum(_covers(known, joined, words, word) for word in distinctive)
        scored.append((covered / len(distinctive), priority))
    scored.sort(key=lambda item: (-item[0], item[1]))
    if not scored or scored[0][0] < _MIN_COVERAGE:
        return None
    if len(scored) > 1 and scored[1][0] == scored[0][0]:
        return None
    return scored[0][1]


def suggest_priority_map(
    questions: Iterable[Mapping[str, Any]], priorities: Iterable[str]
) -> dict[str, str]:
    """Suggested link for each question that has an unambiguous match."""

    priorities = list(priorities)
    suggestions = {}
    for question in questions:
        match = suggest_priority(str(question.get("prompt_text") or ""), priorities)
        if match:
            suggestions[str(int(question["base_prompt_order"]))] = match
    return suggestions


def undecided_questions(
    questions: Iterable[Mapping[str, Any]],
    priorities: Iterable[str],
    question_map: Mapping[str, str],
) -> list[int]:
    """Question numbers with no valid decision."""

    valid = {*[str(p) for p in priorities], NOT_LINKED}
    return [
        int(question["base_prompt_order"])
        for question in questions
        if str(question_map.get(str(int(question["base_prompt_order"])), "")) not in valid
    ]


def build_service_groups(
    priorities: Iterable[str], question_map: Mapping[str, str]
) -> list[dict[str, Any]]:
    """Service groups in the shape the owner report expects.

    Every priority is listed. One with no linked question is reported as not tested,
    never as absent from the AI answers. Questions are never in two groups.
    """

    priorities = [str(p) for p in priorities if str(p).strip()]
    groups = [
        {
            "name": priority,
            "questions": sorted(
                int(order) for order, linked in question_map.items() if linked == priority
            ),
        }
        for priority in priorities
    ]
    general = sorted(
        int(order) for order, linked in question_map.items() if linked == NOT_LINKED
    )
    if general:
        groups.append({"name": GENERAL_GROUP_NAME, "questions": general})
    return groups
