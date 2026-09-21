"""Three practical actions for the client summary, chosen from the measured results.

Every action is a suggested check, never a verified gap: a low appearance count does not
show that a page is missing information, and nothing here has inspected a website. The
wording follows what the research supports (accurate details, consistent listings,
crawlers not blocked) and promises no change in AI answers. Business types differ only in
which details and platforms are named.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

# Limits enforced by the summary contract.
TITLE_LIMIT, TASK_LIMIT, OWNER_LIMIT, DONE_LIMIT = 75, 380, 100, 200
_TOPIC_LIMIT_IN_TITLE = 40


@dataclass(frozen=True)
class BusinessProfile:
    details: str
    platforms: str


_DEFAULT = BusinessProfile(
    details="what you offer, where, prices or price guidance, and how to enquire or book",
    platforms="Google Business Profile, Apple Business, Bing Places and the main directories for your trade",
)
_PROFILES: dict[str, BusinessProfile] = {
    "hospitality": BusinessProfile(
        details="opening times, menus and prices, how to book or enquire (including groups), and what is on",
        platforms="Google Business Profile, Apple Business, Bing Places, TripAdvisor and any booking platform you use",
    ),
    "beauty": BusinessProfile(
        details="services and prices, how to book, who offers what, and opening times",
        platforms="Google Business Profile, Apple Business, Bing Places and your booking platform (Fresha, Booksy or Treatwell)",
    ),
    "trades": BusinessProfile(
        details="the services you offer, areas covered, price guidance, how to ask for a quote, and accreditations",
        platforms="Google Business Profile, Bing Places, and trade directories you belong to such as Checkatrade or MyBuilder",
    ),
    "workspace": BusinessProfile(
        details="spaces and capacity, prices, availability, how to book a visit or a room, and facilities",
        platforms="Google Business Profile, Apple Business, Bing Places and any workspace listing site you use",
    ),
}
_GROUPS = {
    **dict.fromkeys(
        ("bar", "bars", "cafe", "cafes", "food_drink", "hospitality_food_drink",
         "pub", "pubs", "restaurant", "restaurants"), "hospitality"),
    **dict.fromkeys(("hair_beauty", "salon", "salons", "beauty"), "beauty"),
    **dict.fromkeys(("cleaning_services", "trades", "trade", "home_services", "plumber", "electrician"), "trades"),
    **dict.fromkeys(("coworking", "workspace", "office_space"), "workspace"),
}

_OWNER_TOPIC = "Business owner supplies the facts; website provider publishes them"
_DONE_TOPIC = "A customer can find the details and complete an enquiry or booking; the team has tested that route"
_OWNER_DETAILS = "Business owner, with the website provider"
_DONE_DETAILS = "Details agree everywhere they appear, and the website provider has confirmed AI search crawlers can visit the site"


def profile_for(business_group: str | None) -> BusinessProfile:
    key = str(business_group or "").strip().casefold().replace(" ", "_")
    return _PROFILES.get(_GROUPS.get(key, ""), _DEFAULT)


def _rate(question: Mapping[str, Any]) -> float:
    return question["appearances"] / question["answers"] if question["answers"] else 0.0


def _topic_for_title(label: str) -> str:
    label = label.strip().rstrip(".")
    if len(label) > _TOPIC_LIMIT_IN_TITLE:
        return "this topic"
    return label[:1].lower() + label[1:]


def build_actions(
    questions: Sequence[Mapping[str, Any]],
    *,
    business_group: str | None = None,
    reviewer_titles: Iterable[str] = (),
) -> list[dict[str, Any]]:
    """Return exactly three actions.

    questions: dicts with id, label, appearances, answers. The two weakest topics each get
    an information check; the third keeps details consistent, linked to the strongest topic.
    """

    if len(questions) < 2:
        raise ValueError("The client summary needs at least two tested questions to choose actions.")
    profile = profile_for(business_group)
    weakest_first = sorted(questions, key=lambda q: (_rate(q), str(q["id"])))
    strongest = max(questions, key=lambda q: (_rate(q), -questions.index(q)))
    actions = []
    for position, question in enumerate(weakest_first[:2], 1):
        label = str(question["label"]).strip()
        actions.append(
            {
                "id": f"action-{position}",
                "title": f"Make {_topic_for_title(label)} easy to find and act on",
                "question_id": question["id"],
                "status": "suggested_check",
                "evidence_ids": [],
                "task": (
                    f"Review the pages and profiles that cover “{label}”. Where they are missing or unclear, "
                    f"add {profile.details}. Include only details the team can verify."
                ),
                "owner": _OWNER_TOPIC,
                "done_when": _DONE_TOPIC,
            }
        )
    actions.append(
        {
            "id": "action-3",
            "title": "Keep your business details accurate and consistent",
            "question_id": strongest["id"],
            "status": "suggested_check",
            "evidence_ids": [],
            "task": (
                "Check that your name, address, phone number, opening times, services and links match on your "
                f"website and on {profile.platforms}. Correct differences and remove duplicate or out-of-date "
                "listings. Ask your website provider to confirm AI search crawlers are not blocked."
            ),
            "owner": _OWNER_DETAILS,
            "done_when": _DONE_DETAILS,
        }
    )
    for action, title in zip(actions, [str(t).strip() for t in reviewer_titles if str(t).strip()]):
        action["title"] = title
    return actions
