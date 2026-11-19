from __future__ import annotations

import re
import unicodedata
from typing import Any

import pandas as pd

from src.ai_recommendation_intelligence import extract_business_name, normalise_name


def normalise_text(value: Any) -> str:
    text = unicodedata.normalize(
        "NFKD",
        str(value or ""),
    )
    text = "".join(
        character
        for character in text
        if not unicodedata.combining(character)
    )
    text = text.lower()
    text = text.replace("'", "")
    text = text.replace("’", "")
    text = text.replace("&", " and ")
    text = re.sub(
        r"[^a-z0-9]+",
        " ",
        text,
    )
    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def name_aliases(
    business_name: str,
) -> list[str]:
    normalised = normalise_text(
        business_name
    )

    if not normalised:
        return []

    aliases = [normalised]

    without_the = (
        normalised[4:].strip()
        if normalised.startswith("the ")
        else normalised
    )

    # "The Space" must not become "space", which matches the ordinary word in any answer.
    if (
        without_the != normalised
        and len(without_the.split()) >= 2
    ):
        aliases.append(without_the)

    suffixes = [
        " pub and kitchen",
        " pub and rooms",
        " coffee shop",
        " hair salon",
        " restaurant",
        " salon",
        " pub",
        " bar",
        " cafe",
    ]

    for candidate in list(aliases):
        for suffix in suffixes:
            if not candidate.endswith(suffix):
                continue

            shortened = candidate[
                :-len(suffix)
            ].strip()

            word_count = len(
                shortened.split()
            )

            if (
                len(shortened) >= 7
                and (
                    word_count >= 2
                    or normalised.startswith("the ")
                )
            ):
                aliases.append(shortened)

    return list(dict.fromkeys(aliases))


def _contains_alias(
    text: str,
    aliases: list[str],
) -> bool:
    padded = (
        " "
        + normalise_text(text)
        + " "
    )

    return any(
        (
            " "
            + alias
            + " "
        )
        in padded
        for alias in aliases
    )


# Words that may stay lower case inside a business name as an answer writes it.
_NAME_CONNECTORS = frozenset(
    {"a", "an", "and", "at", "by", "de", "des", "du", "for", "in", "la", "le", "of", "on", "the", "to", "y"}
)


def _strip_accents(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(character for character in text if not unicodedata.combining(character))


def _meaningful_words(alias: str) -> list[str]:
    return [word for word in alias.split() if word != "the"]


def _alias_pattern(alias: str) -> re.Pattern[str]:
    """Find an alias in the answer as written, so its capitals can be checked."""

    def word(value: str) -> str:
        # normalise_text drops apostrophes ("Cisco's" becomes "ciscos"), so allow one between letters.
        return "['’]?".join(re.escape(character) for character in value)

    words = alias.split()
    pattern = word(words[0])
    after_and = False
    for value in words[1:]:
        if value == "and":
            # normalise_text writes "&" as "and", so accept either.
            pattern += r"(?:[^A-Za-z0-9]*&[^A-Za-z0-9]*|[^A-Za-z0-9]+and[^A-Za-z0-9]+)"
            after_and = True
            continue
        pattern += ("" if after_and else r"[^A-Za-z0-9]+") + word(value)
        after_and = False
    return re.compile(r"(?<![A-Za-z0-9])" + pattern + r"(?![A-Za-z0-9])", re.IGNORECASE)


def _written_as_name(span: str) -> bool:
    """Each word of the matched text starts with a capital or a digit, as a name would."""

    for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9'’]*", span):
        if token.lower() in _NAME_CONNECTORS:
            continue
        if not (token[0].isupper() or token[0].isdigit()):
            return False
    return True


def _structured_names(response_text: str) -> set[str]:
    """Names the answer presents as names: list items, bold text and headings."""

    names: set[str] = set()
    text = str(response_text or "")

    def add(value: str) -> None:
        value = value.strip(" .,:;–—-")
        for candidate in (value, re.sub(r"\s*\([^)]*\)\s*$", "", value)):
            normalised = normalise_text(candidate)
            if normalised:
                names.add(normalised)

    for line in text.splitlines():
        item = re.match(r"^\s*(?:#{1,6}\s*)?(?:[-*+•]\s+|\d{1,2}[\.\)]\s*)(.+)$", line)
        if item:
            add(extract_business_name(item.group(1)))
        heading = re.match(r"^\s*#{1,6}\s*(.+)$", line)
        if heading:
            add(extract_business_name(heading.group(1)))
    for match in re.finditer(r"\*\*([^*\n]{1,80})\*\*|__([^_\n]{1,80})__", text):
        add(match.group(1) or match.group(2))
    return names


def _distinctive_spelling(business_name: str) -> str | None:
    """A one-word name spelt unlike an ordinary word ("WRAP", "PLATF9RM"), as the listing writes it."""

    words = [
        token
        for token in re.findall(r"[A-Za-z0-9]+", _strip_accents(business_name))
        if token.lower() != "the"
    ]
    if len(words) != 1:
        return None
    token = words[0]
    capitals = sum(1 for character in token if character.isupper())
    has_digit = any(character.isdigit() for character in token)
    has_letter = any(character.isalpha() for character in token)
    if capitals >= 2 or (has_digit and has_letter):
        return token
    return None


def _without_trailing_place_words(names: set[str], place_words: frozenset[str]) -> set[str]:
    """Also hold each presented name without the test's place words at its end ("honeycroft hove" -> "honeycroft")."""

    expanded = set(names)
    for name in names:
        words = name.split()
        while len(words) > 1 and words[-1] in place_words:
            words = words[:-1]
            expanded.add(" ".join(words))
    return expanded


def location_words(location_context: str | None) -> frozenset[str]:
    """The run's own place words ("Brighton and Hove" gives brighton, hove)."""

    return frozenset(
        word for word in normalise_text(location_context).split() if word not in _NAME_CONNECTORS
    )


def find_valid_name_position(
    response_text: str,
    business_name: str,
    *,
    structured_names: set[str] | None = None,
    place_words: frozenset[str] = frozenset(),
    is_target: bool = False,
    normalised_response: str | None = None,
    raw_response: str | None = None,
) -> int | None:
    """Where a business is named in an answer, counting only uses that read as its name.

    Plain text matching credited listings called "Brighton", "Village", "Here" or "The Space" with nearly every
    answer, and "STRONG Brighton" with the phrase "a strong Brighton feel" (WRAP's November test). Now:
    - a name of two or more words must be written with capitals, as a name;
    - a one-word name (besides "the") counts only where the answer presents it as a name - a list item, bold text
      or a heading - or, if the listing spells it unlike an ordinary word ("WRAP", "PLATF9RM"), written exactly so;
      a one-word name that is one of the run's own place words never counts from text alone;
    - the target keeps plain matching for its one-word name (written with a capital): it is the business the test
      is about, and its short forms are decided by the reviewer in step 5, not here.
    """

    # The caller passes the answer prepared once; checking thousands of known names re-prepared it every time.
    if normalised_response is None:
        normalised_response = " " + normalise_text(response_text) + " "
    raw = raw_response if raw_response is not None else _strip_accents(response_text)
    found = [
        (alias, index)
        for alias in name_aliases(business_name)
        for index in [normalised_response.find(" " + alias + " ")]
        if index >= 0
    ]
    if not found:
        return None
    if structured_names is None:
        structured_names = _structured_names(response_text)
    spelling = _distinctive_spelling(business_name)
    positions = []

    for alias, index in found:
        single_word = len(_meaningful_words(alias)) < 2
        if single_word and not is_target:
            if alias in place_words or " ".join(_meaningful_words(alias)) in place_words:
                continue
            # A name with a digit is distinctive in any case ("Time2Shine"); one made distinctive only by its
            # capitals ("WRAP", "POD") must be written exactly so, or "wrap" and "pod" would count.
            spelling_flags = re.IGNORECASE if spelling and any(c.isdigit() for c in spelling) else 0
            valid = alias in structured_names or (
                spelling is not None
                and re.search(
                    r"(?<![A-Za-z0-9])" + re.escape(spelling) + r"(?![A-Za-z0-9])", raw, spelling_flags
                ) is not None
            )
        else:
            valid = any(_written_as_name(match.group(0)) for match in _alias_pattern(alias).finditer(raw))
        if valid:
            positions.append(index)

    return min(positions) if positions else None


def find_name_position(
    response_text: str,
    business_name: str,
) -> int | None:
    normalised_response = (
        " "
        + normalise_text(response_text)
        + " "
    )

    positions = []

    for alias in name_aliases(
        business_name
    ):
        pattern = (
            " "
            + alias
            + " "
        )

        index = (
            normalised_response.find(
                pattern
            )
        )

        if index >= 0:
            positions.append(index)

    return min(positions) if positions else None


def find_recommendation_position(
    response_text: str,
    business_name: str,
) -> int | None:
    aliases = name_aliases(
        business_name
    )

    if not aliases:
        return None

    numbered_line = re.compile(
        r"^\s*(?:#{1,6}\s*)?"
        r"(\d+)[\.\)]\s*(.+)$"
    )

    for line in str(
        response_text or ""
    ).splitlines():
        match = numbered_line.match(
            line
        )

        if not match:
            continue

        item_number = int(
            match.group(1)
        )
        ranked_name = extract_business_name(match.group(2))
        ranked_normalised = normalise_name(ranked_name)

        legal_suffix_variants = tuple(
            alias + suffix
            for alias in aliases
            for suffix in (
                " limited",
                " ltd",
                " plc",
                " llp",
            )
        )

        if (
            ranked_normalised in aliases
            or ranked_normalised.startswith(legal_suffix_variants)
        ):
            return item_number

    return None


def analyse_visibility_response(
    *,
    response_text: str,
    target_google_place_id: str,
    target_business_name: str,
    known_businesses: list[
        dict[str, str]
    ],
    location_context: str | None = None,
) -> dict[str, Any]:
    mentions = []
    place_words = location_words(location_context)
    structured_names = _without_trailing_place_words(_structured_names(response_text), place_words)
    normalised_response = " " + normalise_text(response_text) + " "
    raw_response = _strip_accents(response_text)

    for business in known_businesses:
        place_id = str(
            business.get(
                "google_place_id"
            )
            or ""
        )
        name = str(
            business.get(
                "business_name"
            )
            or ""
        )

        if not place_id or not name:
            continue

        character_position = find_valid_name_position(
            response_text,
            name,
            structured_names=structured_names,
            place_words=place_words,
            is_target=place_id == str(target_google_place_id),
            normalised_response=normalised_response,
            raw_response=raw_response,
        )

        if character_position is None:
            continue

        recommendation_position = (
            find_recommendation_position(
                response_text,
                name,
            )
        )

        mentions.append(
            {
                "google_place_id":
                    place_id,
                "business_name":
                    name,
                "character_position":
                    int(
                        character_position
                    ),
                "recommendation_position":
                    recommendation_position,
                "recommended":
                    (
                        recommendation_position
                        is not None
                    ),
            }
        )

    mentions = sorted(
        mentions,
        key=lambda item: (
            (
                item[
                    "recommendation_position"
                ]
                if item[
                    "recommendation_position"
                ]
                is not None
                else 999
            ),
            item[
                "character_position"
            ],
            item[
                "business_name"
            ],
        ),
    )

    target_mention = next(
        (
            mention
            for mention in mentions
            if mention[
                "google_place_id"
            ]
            == str(
                target_google_place_id
            )
        ),
        None,
    )

    competitors = [
        mention
        for mention in mentions
        if mention[
            "google_place_id"
        ]
        != str(
            target_google_place_id
        )
    ]

    return {
        "target_mentioned": (
            target_mention is not None
        ),
        "target_recommended": (
            bool(
                target_mention
                and target_mention[
                    "recommended"
                ]
            )
        ),
        "target_position": (
            target_mention[
                "recommendation_position"
            ]
            if target_mention
            else None
        ),
        "mentioned_competitors":
            competitors,
        "mentioned_known_businesses":
            mentions,
    }


def reanalyse_results(
    results: pd.DataFrame,
    *,
    target_google_place_id: str,
    target_business_name: str,
    known_businesses: list[
        dict[str, str]
    ],
    location_context: str | None = None,
) -> pd.DataFrame:
    if results.empty:
        return results

    frame = results.copy()

    for index, row in frame.iterrows():
        if (
            row.get("status")
            != "completed"
            or not str(
                row.get(
                    "raw_response"
                )
                or ""
            ).strip()
        ):
            continue

        analysis = (
            analyse_visibility_response(
                response_text=str(
                    row[
                        "raw_response"
                    ]
                ),
                target_google_place_id=(
                    target_google_place_id
                ),
                target_business_name=(
                    target_business_name
                ),
                known_businesses=(
                    known_businesses
                ),
                location_context=location_context,
            )
        )

        frame.at[
            index,
            "target_mentioned",
        ] = analysis[
            "target_mentioned"
        ]

        frame.at[
            index,
            "target_recommended",
        ] = analysis[
            "target_recommended"
        ]

        frame.at[
            index,
            "target_position",
        ] = analysis[
            "target_position"
        ]

        frame.at[
            index,
            "mentioned_competitors",
        ] = analysis[
            "mentioned_competitors"
        ]

        frame.at[
            index,
            "mentioned_known_businesses",
        ] = analysis[
            "mentioned_known_businesses"
        ]

    return frame


def visibility_summary(
    results: pd.DataFrame,
) -> pd.DataFrame:
    if results.empty:
        return pd.DataFrame()

    rows = []

    providers = sorted(
        results[
            "provider"
        ]
        .dropna()
        .astype(str)
        .unique()
        .tolist()
    )

    for provider in providers:
        provider_frame = results[
            results[
                "provider"
            ]
            == provider
        ].copy()

        valid = provider_frame[
            (
                provider_frame[
                    "status"
                ]
                == "completed"
            )
            & (
                provider_frame[
                    "response_complete"
                ]
                .fillna(False)
                .astype(bool)
            )
        ].copy()

        incomplete = provider_frame[
            (
                provider_frame[
                    "status"
                ]
                == "completed"
            )
            & (
                ~provider_frame[
                    "response_complete"
                ]
                .fillna(False)
                .astype(bool)
            )
        ]

        failed = provider_frame[
            provider_frame[
                "status"
            ]
            == "failed"
        ]

        recommended = (
            valid[
                "target_recommended"
            ]
            .fillna(False)
            .astype(bool)
        )

        positions = pd.to_numeric(
            valid[
                "target_position"
            ],
            errors="coerce",
        ).dropna()

        visibility_rate = (
            float(
                recommended.mean()
            )
            if not valid.empty
            else None
        )

        rows.append(
            {
                "provider":
                    provider,
                "valid_responses":
                    len(valid),
                "incomplete_responses":
                    len(incomplete),
                "failed_responses":
                    len(failed),
                "target_recommendations":
                    int(
                        recommended.sum()
                    ),
                "visibility_rate":
                    visibility_rate,
                "average_position":
                    (
                        float(
                            positions.mean()
                        )
                        if not positions.empty
                        else None
                    ),
                "input_tokens":
                    int(
                        pd.to_numeric(
                            provider_frame[
                                "input_tokens"
                            ],
                            errors="coerce",
                        )
                        .fillna(0)
                        .sum()
                    ),
                "output_tokens":
                    int(
                        pd.to_numeric(
                            provider_frame[
                                "output_tokens"
                            ],
                            errors="coerce",
                        )
                        .fillna(0)
                        .sum()
                    ),
                "reasoning_tokens":
                    int(
                        pd.to_numeric(
                            provider_frame[
                                "reasoning_tokens"
                            ],
                            errors="coerce",
                        )
                        .fillna(0)
                        .sum()
                    ),
            }
        )

    return pd.DataFrame(rows)


def competitor_mention_summary(
    results: pd.DataFrame,
) -> pd.DataFrame:
    if results.empty:
        return pd.DataFrame()

    valid = results[
        (
            results["status"]
            == "completed"
        )
        & (
            results[
                "response_complete"
            ]
            .fillna(False)
            .astype(bool)
        )
    ]

    counts = {}

    for record in valid.to_dict(
        "records"
    ):
        mentions = record.get(
            "mentioned_known_businesses"
        ) or []

        for mention in mentions:
            if not mention.get(
                "recommended"
            ):
                continue

            place_id = str(
                mention.get(
                    "google_place_id"
                )
            )
            name = str(
                mention.get(
                    "business_name"
                )
            )

            key = (
                place_id,
                name,
            )

            counts[key] = (
                counts.get(
                    key,
                    0,
                )
                + 1
            )

    rows = [
        {
            "google_place_id":
                place_id,
            "business_name":
                name,
            "recommendations":
                count,
        }
        for (
            place_id,
            name,
        ), count in counts.items()
    ]

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(
        rows
    ).sort_values(
        [
            "recommendations",
            "business_name",
        ],
        ascending=[
            False,
            True,
        ],
    )
