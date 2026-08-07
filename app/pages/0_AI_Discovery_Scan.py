from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd
import streamlit as st
from sqlalchemy import text


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT))

from src.ai_discovery_prompt_generator import (
    VERTICALS,
    generate_discovery_prompts,
    vertical_key,
)
from src.ai_discovery_repository import (
    create_discovery_run,
    get_discovery_run,
    list_discovery_runs,
    load_diagnostic_readiness,
)
from src.ai_enrichment_repository import (
    load_entity_aliases,
    upsert_enrichment_candidates,
)
from src.ai_recommendation_intelligence import (
    build_business_share_table,
    build_directory_index,
    build_intent_stability_table,
    build_provider_share_table,
    build_recommendation_records,
    resolve_business_name,
)
from src.ai_visibility_analysis import (
    reanalyse_results,
    visibility_summary,
)
from src.ai_visibility_repository import (
    create_visibility_queries,
    get_run_results,
)
from src.ai_visibility_runner import (
    execute_calls,
    finalise_run_from_results,
)
from src.database import get_engine


BUILD_VERSION = "AI Discovery Scan v1.0"

DEFAULT_MODELS = {
    "OpenAI": "gpt-5.6-terra",
    "Claude": "claude-sonnet-5",
    "Gemini": "gemini-3.6-flash",
}


st.set_page_config(
    page_title="AI Discovery Scan",
    page_icon="🔎",
    layout="wide",
)

st.title("AI Discovery Scan")
st.caption(
    "Start with a few client facts, test real customer "
    "recommendation questions immediately, and discover "
    "the market as AI sees it."
)
st.caption(f"Build: {BUILD_VERSION}")

st.success(
    "This is an **additional entry point**. It does not "
    "replace the existing Competitor Matcher, Website "
    "Audits, Review Intelligence, Website Benchmark or "
    "AI Results Intelligence workflows."
)

st.info(
    "The client name, website and description are saved "
    "as scan context but are **not inserted into the AI "
    "prompts**. The models are asked neutral customer "
    "questions so the target must earn its recommendation."
)


def secret_value(
    key: str,
    default: str = "",
) -> str:
    try:
        value = st.secrets.get(
            key,
            default,
        )
    except Exception:
        value = default

    return str(
        value or default
    )


def jsonish(
    value,
    default,
):
    if isinstance(
        value,
        (
            list,
            dict,
        ),
    ):
        return value

    if value is None:
        return default

    try:
        if pd.isna(value):
            return default
    except (
        TypeError,
        ValueError,
    ):
        pass

    if isinstance(
        value,
        str,
    ):
        try:
            return json.loads(
                value
            )
        except json.JSONDecodeError:
            return default

    return default


def split_propositions(
    value: str,
) -> list[str]:
    parts = re.split(
        r"[\n,;]+",
        str(
            value
            or ""
        ),
    )

    return [
        re.sub(
            r"\s+",
            " ",
            part.strip(),
        )
        for part in parts
        if len(
            part.strip()
        )
        >= 3
    ]


@st.cache_data(ttl=300)
def load_business_directory() -> pd.DataFrame:
    engine = get_engine()

    query = text(
        """
        select
            google_place_id,
            business_name,
            primary_group,
            business_format
        from business_features
        order by business_name
        """
    )

    with engine.connect() as connection:
        rows = connection.execute(
            query
        ).mappings().all()

    return pd.DataFrame(rows)


try:
    businesses = (
        load_business_directory()
    )
except Exception as exc:
    st.error(
        "The business directory could not be loaded."
    )
    st.exception(exc)
    st.stop()


try:
    entity_aliases = (
        load_entity_aliases()
    )
except Exception:
    entity_aliases = pd.DataFrame()


# =========================================================
# 1. CLIENT SNAPSHOT
# =========================================================

st.subheader("1. Client snapshot")

profile_columns = st.columns(
    [1.1, 0.9]
)

with profile_columns[0]:
    target_name = st.text_input(
        "Business name",
        placeholder=(
            "For example: The George Payne Pub"
        ),
    )

    category_label = st.selectbox(
        "Business category",
        options=list(
            VERTICALS.keys()
        ),
        index=0,
    )

    location_context = st.text_input(
        "Market / location",
        placeholder=(
            "For example: Hove"
        ),
    )

    target_website = st.text_input(
        "Website",
        placeholder=(
            "https://example.com"
        ),
    )

with profile_columns[1]:
    target_description = st.text_area(
        "Short description",
        placeholder=(
            "A short internal description of the client. "
            "This is stored as context but is not sent "
            "to the recommendation models."
        ),
        height=120,
    )

    propositions_text = st.text_area(
        "Key propositions / customer needs",
        placeholder=(
            "One per line, for example:\n"
            "a Sunday roast\n"
            "a good pub garden\n"
            "live music\n"
            "groups and celebrations"
        ),
        height=150,
    )


primary_group = vertical_key(
    category_label
)


def resolve_target():
    if not target_name.strip():
        return {
            "resolution_status":
                "unresolved",
            "resolution_score":
                None,
            "google_place_id":
                None,
            "business_name":
                target_name.strip(),
        }

    directory_index = (
        build_directory_index(
            businesses,
            aliases=entity_aliases,
        )
    )

    result = resolve_business_name(
        target_name.strip(),
        directory_index=(
            directory_index
        ),
        primary_group=(
            primary_group
        ),
        fuzzy_threshold=0.94,
        margin_threshold=0.06,
    )

    # For a quick-scan target, err on the side of NOT attaching a
    # prospect to an existing entity unless confidence is very high.
    if (
        result.get(
            "resolution_status"
        )
        in {
            "exact",
            "exact_group",
        }
    ):
        return result

    score = result.get(
        "resolution_score"
    )

    if (
        result.get(
            "resolution_status"
        )
        == "fuzzy"
        and score is not None
        and float(score) >= 0.97
    ):
        return result

    return {
        "resolution_status":
            "unresolved",
        "resolution_score":
            score,
        "google_place_id":
            None,
        "business_name":
            target_name.strip(),
    }


target_resolution = (
    resolve_target()
)

if target_name.strip():
    if target_resolution.get(
        "google_place_id"
    ):
        st.caption(
            "Existing dataset match: "
            f"**{target_resolution.get('business_name')}** "
            f"({target_resolution.get('resolution_status')})"
        )
    else:
        st.caption(
            "No high-confidence existing dataset match. "
            "That's fine: the scan will use a temporary "
            "target entity and can enrich the business later."
        )


profile_signature = json.dumps(
    {
        "name":
            target_name.strip(),
        "category":
            category_label,
        "location":
            location_context.strip(),
        "propositions":
            split_propositions(
                propositions_text
            ),
    },
    sort_keys=True,
)


generate_disabled = (
    not target_name.strip()
    or not location_context.strip()
)

if st.button(
    "Generate customer questions",
    type="primary",
    disabled=generate_disabled,
):
    st.session_state[
        "discovery_prompt_frame"
    ] = generate_discovery_prompts(
        category_label=(
            category_label
        ),
        location=(
            location_context
        ),
        propositions=(
            propositions_text
        ),
        max_prompts=20,
    )

    st.session_state[
        "discovery_profile_signature"
    ] = profile_signature


# =========================================================
# 2. PROMPTS + RUN
# =========================================================

if (
    "discovery_prompt_frame"
    in st.session_state
):
    st.divider()
    st.subheader(
        "2. Review the customer questions"
    )

    if (
        st.session_state.get(
            "discovery_profile_signature"
        )
        != profile_signature
    ):
        st.warning(
            "The client snapshot has changed since these "
            "questions were generated. Click **Generate "
            "customer questions** again before running "
            "if you want the prompt set updated."
        )

    edited_prompts = st.data_editor(
        st.session_state[
            "discovery_prompt_frame"
        ],
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        column_config={
            "include":
                st.column_config.CheckboxColumn(
                    "Run"
                ),
            "category":
                st.column_config.TextColumn(
                    "Intent"
                ),
            "source":
                st.column_config.TextColumn(
                    "Source"
                ),
            "prompt":
                st.column_config.TextColumn(
                    "Customer question",
                    width="large",
                ),
        },
        key="discovery_prompt_editor",
    )

    st.session_state[
        "discovery_prompt_frame"
    ] = edited_prompts.copy()

    selected_prompts = (
        edited_prompts[
            edited_prompts[
                "include"
            ].fillna(False)
        ].copy()
    )

    selected_prompts[
        "prompt"
    ] = (
        selected_prompts[
            "prompt"
        ]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    selected_prompts = (
        selected_prompts[
            selected_prompts[
                "prompt"
            ].ne("")
        ]
    )

    target_name_lower = (
        target_name
        .strip()
        .lower()
    )

    prompt_mentions_target = (
        bool(
            target_name_lower
        )
        and selected_prompts[
            "prompt"
        ]
        .astype(str)
        .str.lower()
        .str.contains(
            re.escape(
                target_name_lower
            ),
            regex=True,
        )
        .any()
    )

    if prompt_mentions_target:
        st.error(
            "At least one selected customer question "
            "contains the target business name. Remove "
            "the target name before running the neutral "
            "visibility benchmark."
        )

    st.write("### Sampling")

    repetitions = st.radio(
        "Repetitions per customer question",
        options=[1, 2, 3],
        index=0,
        horizontal=True,
        help=(
            "1 = quick reconnaissance. "
            "3 = recommended for a more robust "
            "client benchmark."
        ),
    )

    st.write("### Providers")

    api_keys = {
        "OpenAI":
            secret_value(
                "OPENAI_API_KEY"
            ),
        "Claude":
            secret_value(
                "ANTHROPIC_API_KEY"
            ),
        "Gemini":
            secret_value(
                "GEMINI_API_KEY"
            ),
    }

    provider_columns = (
        st.columns(3)
    )

    selected_providers = []

    for column, provider in zip(
        provider_columns,
        [
            "OpenAI",
            "Claude",
            "Gemini",
        ],
    ):
        with column:
            available = bool(
                api_keys[
                    provider
                ]
            )

            selected = st.checkbox(
                provider,
                value=available,
                disabled=not available,
                key=(
                    "discovery_provider_"
                    + provider
                ),
            )

            if selected:
                selected_providers.append(
                    provider
                )

    with st.expander(
        "Model settings"
    ):
        model_values = {
            "OpenAI":
                st.text_input(
                    "OpenAI model",
                    value=secret_value(
                        "OPENAI_MODEL",
                        DEFAULT_MODELS[
                            "OpenAI"
                        ],
                    ),
                    key=(
                        "discovery_openai_model"
                    ),
                ),
            "Claude":
                st.text_input(
                    "Claude model",
                    value=secret_value(
                        "ANTHROPIC_MODEL",
                        DEFAULT_MODELS[
                            "Claude"
                        ],
                    ),
                    key=(
                        "discovery_claude_model"
                    ),
                ),
            "Gemini":
                st.text_input(
                    "Gemini model",
                    value=secret_value(
                        "GEMINI_MODEL",
                        DEFAULT_MODELS[
                            "Gemini"
                        ],
                    ),
                    key=(
                        "discovery_gemini_model"
                    ),
                ),
        }

    total_calls = (
        len(
            selected_prompts
        )
        * int(
            repetitions
        )
        * len(
            selected_providers
        )
    )

    st.caption(
        f"{len(selected_prompts)} customer question(s) × "
        f"{int(repetitions)} repetition(s) × "
        f"{len(selected_providers)} provider(s) = "
        f"**{total_calls} API call(s)**."
    )

    run_disabled = (
        not target_name.strip()
        or not location_context.strip()
        or selected_prompts.empty
        or not selected_providers
        or prompt_mentions_target
    )

    if st.button(
        "Run AI Discovery Scan",
        type="primary",
        disabled=run_disabled,
    ):
        prompt_records = (
            selected_prompts[
                [
                    "category",
                    "source",
                    "prompt",
                ]
            ]
            .to_dict(
                "records"
            )
        )

        propositions = (
            split_propositions(
                propositions_text
            )
        )

        run_models = {
            provider:
                model_values[
                    provider
                ]
            for provider in (
                selected_providers
            )
        }

        created = create_discovery_run(
            target_business_name=(
                target_name.strip()
            ),
            target_google_place_id=(
                target_resolution.get(
                    "google_place_id"
                )
            ),
            target_resolution_status=(
                target_resolution.get(
                    "resolution_status"
                )
                or "unresolved"
            ),
            target_dataset_match_name=(
                target_resolution.get(
                    "business_name"
                )
                if target_resolution.get(
                    "google_place_id"
                )
                else None
            ),
            primary_group=(
                primary_group
            ),
            category_label=(
                category_label
            ),
            location_context=(
                location_context.strip()
            ),
            website=(
                target_website.strip()
            ),
            description=(
                target_description.strip()
            ),
            propositions=(
                propositions
            ),
            providers=(
                selected_providers
            ),
            models=(
                run_models
            ),
            prompt_count=len(
                prompt_records
            ),
            repeat_count=int(
                repetitions
            ),
        )

        run_id = created[
            "run_id"
        ]
        target_id = created[
            "target_google_place_id"
        ]

        query_records = (
            create_visibility_queries(
                run_id=run_id,
                prompts=prompt_records,
                repetitions=int(
                    repetitions
                ),
            )
        )

        call_plan = [
            {
                **query_record,
                "provider":
                    provider,
            }
            for query_record
            in query_records
            for provider
            in selected_providers
        ]

        progress = st.progress(0)
        status_box = st.empty()

        def progress_callback(
            processed: int,
            total: int,
        ):
            progress.progress(
                processed
                / max(
                    total,
                    1,
                )
            )

        def status_callback(
            prompt_text: str,
        ):
            status_box.write(
                f"Testing: **{prompt_text}**"
            )

        execute_calls(
            run_id=run_id,
            call_plan=call_plan,
            models=run_models,
            api_keys=api_keys,
            target_google_place_id=(
                target_id
            ),
            target_business_name=(
                target_name.strip()
            ),
            known_businesses=[
                {
                    "google_place_id":
                        target_id,
                    "business_name":
                        target_name.strip(),
                }
            ],
            progress_callback=(
                progress_callback
            ),
            status_callback=(
                status_callback
            ),
        )

        finalise_run_from_results(
            run_id=run_id,
            expected_call_count=len(
                call_plan
            ),
        )

        status_box.empty()

        st.session_state[
            "selected_discovery_run_id"
        ] = run_id

        st.cache_data.clear()

        st.success(
            "AI Discovery Scan complete. "
            "The result has been saved."
        )

        st.rerun()


# =========================================================
# 3. SAVED / LATEST SCAN
# =========================================================

st.divider()
st.subheader("3. Discovery results")

try:
    recent_runs = list_discovery_runs(
        limit=25
    )
except Exception as exc:
    st.warning(
        "AI Discovery Scan storage is not available yet. "
        "Run `sql/12_ai_discovery_scan.sql` in Supabase."
    )
    st.exception(exc)
    st.stop()


if recent_runs.empty:
    st.info(
        "No AI-first discovery scans have been run yet."
    )
    st.stop()


recent_runs[
    "id"
] = recent_runs[
    "id"
].astype(str)

run_lookup = {
    str(
        row[
            "id"
        ]
    ): (
        f"{row['target_business_name']} — "
        f"{row['location_context']} — "
        f"{row['started_at']}"
    )
    for row in recent_runs.to_dict(
        "records"
    )
}

run_ids = recent_runs[
    "id"
].tolist()

default_run_id = (
    st.session_state.get(
        "selected_discovery_run_id"
    )
)

if (
    default_run_id
    not in run_ids
):
    default_run_id = (
        run_ids[0]
    )

selected_run_id = st.selectbox(
    "Saved discovery scan",
    options=run_ids,
    index=run_ids.index(
        default_run_id
    ),
    format_func=lambda value: (
        run_lookup.get(
            value,
            value,
        )
    ),
)

st.session_state[
    "selected_discovery_run_id"
] = selected_run_id

run = get_discovery_run(
    selected_run_id
)

if not run:
    st.error(
        "The selected discovery scan could not be loaded."
    )
    st.stop()


results = get_run_results(
    selected_run_id
)

if results.empty:
    st.info(
        "This scan has no stored model responses yet."
    )
    st.stop()


run_target_id = str(
    run[
        "target_google_place_id"
    ]
)
run_target_name = str(
    run[
        "target_business_name"
    ]
)
run_primary_group = str(
    run.get(
        "primary_group"
    )
    or ""
)

known_businesses = [
    {
        "google_place_id":
            run_target_id,
        "business_name":
            run_target_name,
    }
]

results = reanalyse_results(
    results,
    target_google_place_id=(
        run_target_id
    ),
    target_business_name=(
        run_target_name
    ),
    known_businesses=(
        known_businesses
    ),
)

summary = visibility_summary(
    results
)

st.write("### AI visibility")

if not summary.empty:
    metric_columns = st.columns(
        len(
            summary
        )
    )

    for column, row in zip(
        metric_columns,
        summary.to_dict(
            "records"
        ),
    ):
        with column:
            rate = row[
                "visibility_rate"
            ]

            value = (
                f"{float(rate):.0%} visible"
                if (
                    rate is not None
                    and pd.notna(
                        rate
                    )
                )
                else "No valid responses"
            )

            position = row[
                "average_position"
            ]

            delta = (
                f"Avg position "
                f"{float(position):.1f}"
                if (
                    position is not None
                    and pd.notna(
                        position
                    )
                )
                else None
            )

            st.metric(
                str(
                    row[
                        "provider"
                    ]
                ),
                value,
                delta=delta,
            )


# Build a directory that includes the prospect itself even when it has
# not yet been imported into the structured business dataset.
market_businesses = (
    businesses.copy()
)

if (
    run_target_id.startswith(
        "discovery:"
    )
):
    target_stub = pd.DataFrame(
        [
            {
                "google_place_id":
                    run_target_id,
                "business_name":
                    run_target_name,
                "primary_group":
                    run_primary_group,
                "business_format":
                    run.get(
                        "target_category_label"
                    ),
            }
        ]
    )

    market_businesses = pd.concat(
        [
            market_businesses,
            target_stub,
        ],
        ignore_index=True,
    )


recommendations = (
    build_recommendation_records(
        results=results,
        businesses=(
            market_businesses
        ),
        aliases=(
            entity_aliases
        ),
        target_google_place_id=(
            run_target_id
        ),
        commercial_competitor_ids=set(),
        primary_group=(
            run_primary_group
        ),
    )
)

provider_share = (
    build_provider_share_table(
        recommendations,
        target_google_place_id=(
            run_target_id
        ),
    )
)

business_share = (
    build_business_share_table(
        recommendations
    )
)


if not provider_share.empty:
    st.write(
        "### Share of Recommendation"
    )

    overall = (
        provider_share[
            provider_share[
                "provider"
            ]
            == "All providers"
        ]
    )

    if not overall.empty:
        row = overall.iloc[0]

        cols = st.columns(3)

        with cols[0]:
            st.metric(
                "Overall Share of Recommendation",
                f"{float(row['share_of_recommendation']):.1%}",
            )

        with cols[1]:
            st.metric(
                "Position-weighted share",
                f"{float(row['position_weighted_share']):.1%}",
            )

        with cols[2]:
            st.metric(
                "Target recommendation slots",
                (
                    f"{int(row['target_recommendations'])}"
                    f" / {int(row['recommendation_slots'])}"
                ),
            )

    provider_display = (
        provider_share.copy()
    )

    provider_display[
        "Share"
    ] = provider_display[
        "share_of_recommendation"
    ].apply(
        lambda value: (
            f"{float(value):.1%}"
        )
    )

    provider_display[
        "Weighted share"
    ] = provider_display[
        "position_weighted_share"
    ].apply(
        lambda value: (
            f"{float(value):.1%}"
        )
    )

    st.dataframe(
        provider_display[
            [
                "provider",
                "recommendation_slots",
                "target_recommendations",
                "Share",
                "Weighted share",
            ]
        ].rename(
            columns={
                "provider":
                    "Provider",
                "recommendation_slots":
                    "Recommendation slots",
                "target_recommendations":
                    "Target recommendations",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )


if not business_share.empty:
    st.write(
        "### AI recommendation market"
    )

    st.caption(
        "This market is discovered from the AI responses "
        "themselves. It is intentionally not limited to a "
        "pre-selected competitor cohort."
    )

    market_display = (
        business_share.copy()
    )

    market_display[
        "Share"
    ] = market_display[
        "share_of_recommendation"
    ].apply(
        lambda value: (
            f"{float(value):.1%}"
        )
    )

    market_display[
        "Weighted share"
    ] = market_display[
        "position_weighted_share"
    ].apply(
        lambda value: (
            f"{float(value):.1%}"
        )
    )

    market_display[
        "Avg position"
    ] = market_display[
        "average_position"
    ].apply(
        lambda value: (
            f"{float(value):.2f}"
        )
    )

    provider_columns = [
        column
        for column in [
            "OpenAI_recommendations",
            "Claude_recommendations",
            "Gemini_recommendations",
        ]
        if column
        in market_display.columns
    ]

    st.dataframe(
        market_display[
            [
                "business_name",
                "classification",
                "recommendations",
                "Share",
                "Weighted share",
                "Avg position",
                *provider_columns,
            ]
        ].head(30).rename(
            columns={
                "business_name":
                    "Business",
                "classification":
                    "Relationship",
                "recommendations":
                    "Recommendations",
                "OpenAI_recommendations":
                    "OpenAI",
                "Claude_recommendations":
                    "Claude",
                "Gemini_recommendations":
                    "Gemini",
            }
        ),
        use_container_width=True,
        hide_index=True,
        height=650,
    )


# =========================================================
# 4. WHO SHOULD WE INVESTIGATE?
# =========================================================

st.write(
    "### Who should we investigate next?"
)

if business_share.empty:
    st.info(
        "No recommendation market was extracted."
    )
else:
    leaders = business_share[
        business_share[
            "classification"
        ]
        .isin(
            [
                "AI-discovered",
                "Unresolved",
            ]
        )
    ].copy().head(12)

    resolved_leader_ids = (
        leaders[
            "google_place_id"
        ]
        .dropna()
        .astype(str)
        .tolist()
    )

    try:
        readiness = (
            load_diagnostic_readiness(
                resolved_leader_ids
            )
        )
    except Exception:
        readiness = pd.DataFrame()

    if not readiness.empty:
        readiness[
            "google_place_id"
        ] = readiness[
            "google_place_id"
        ].astype(str)

        leaders[
            "google_place_id"
        ] = leaders[
            "google_place_id"
        ].astype(str)

        leaders = leaders.merge(
            readiness,
            on="google_place_id",
            how="left",
        )
    else:
        leaders[
            "latest_website_audit"
        ] = None
        leaders[
            "website_score"
        ] = None
        leaders[
            "reviews_stored"
        ] = 0

    leaders[
        "Website audit"
    ] = leaders[
        "latest_website_audit"
    ].apply(
        lambda value: (
            "Yes"
            if pd.notna(
                value
            )
            else "No"
        )
    )

    leaders[
        "Reviews"
    ] = pd.to_numeric(
        leaders[
            "reviews_stored"
        ],
        errors="coerce",
    ).fillna(0).astype(int)

    leaders[
        "Next action"
    ] = leaders.apply(
        lambda row: (
            "Ready to compare"
            if (
                row[
                    "Website audit"
                ]
                == "Yes"
                and int(
                    row[
                        "Reviews"
                    ]
                )
                > 0
            )
            else (
                "Run website audit"
                if (
                    row[
                        "Website audit"
                    ]
                    == "No"
                    and int(
                        row[
                            "Reviews"
                        ]
                    )
                    > 0
                )
                else (
                    "Import reviews"
                    if (
                        row[
                            "Website audit"
                        ]
                        == "Yes"
                    )
                    else (
                        "Enrich business data"
                        if row[
                            "classification"
                        ]
                        == "Unresolved"
                        else "Website + reviews"
                    )
                )
            )
        ),
        axis=1,
    )

    leaders[
        "Share"
    ] = leaders[
        "share_of_recommendation"
    ].apply(
        lambda value: (
            f"{float(value):.1%}"
        )
    )

    st.dataframe(
        leaders[
            [
                "business_name",
                "classification",
                "recommendations",
                "Share",
                "average_position",
                "Website audit",
                "Reviews",
                "Next action",
            ]
        ].rename(
            columns={
                "business_name":
                    "Business",
                "classification":
                    "Relationship",
                "recommendations":
                    "AI recommendations",
                "average_position":
                    "Avg position",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

    unresolved = leaders[
        leaders[
            "classification"
        ]
        == "Unresolved"
    ].copy()

    if not unresolved.empty:
        action_columns = st.columns(
            2
        )

        with action_columns[0]:
            if st.button(
                "Add unresolved leaders to enrichment queue",
                key=(
                    "discovery_enrich_"
                    + selected_run_id
                ),
            ):
                saved = (
                    upsert_enrichment_candidates(
                        run_id=(
                            selected_run_id
                        ),
                        unresolved_market=(
                            unresolved
                        ),
                    )
                )

                st.success(
                    f"Saved/updated {saved} "
                    "candidate(s) in the enrichment queue."
                )

        with action_columns[1]:
            lookup_export = (
                unresolved.assign(
                    lookup_query=(
                        unresolved[
                            "business_name"
                        ].astype(str)
                        + " "
                        + str(
                            run.get(
                                "location_context"
                            )
                            or ""
                        )
                    )
                )[
                    [
                        "business_name",
                        "lookup_query",
                        "recommendations",
                        "providers",
                        "average_position",
                    ]
                ]
                .to_csv(
                    index=False
                )
                .encode(
                    "utf-8"
                )
            )

            st.download_button(
                "Download targeted lookup CSV",
                data=lookup_export,
                file_name=(
                    "ai_discovery_lookup.csv"
                ),
                mime="text/csv",
            )


# =========================================================
# 5. INTENT PERFORMANCE / STABILITY
# =========================================================

repeat_count = int(
    run.get(
        "repeat_count"
    )
    or 1
)

st.write(
    (
        "### Intent stability"
        if repeat_count > 1
        else "### Intent performance"
    )
)

if repeat_count == 1:
    st.caption(
        "This scan contains one sample per customer "
        "question, so this shows intent-level performance. "
        "Use 2–3 repetitions for a true stability measure."
    )

stability = (
    build_intent_stability_table(
        results
    )
)

if not stability.empty:
    prompt_groups = (
        stability[
            [
                "base_prompt_order",
                "prompt_text",
            ]
        ]
        .drop_duplicates()
        .sort_values(
            "base_prompt_order"
        )
    )

    provider_names = [
        str(
            provider
        )
        for provider in jsonish(
            run.get(
                "providers"
            ),
            [],
        )
    ]

    matrix_rows = []

    for prompt in (
        prompt_groups.to_dict(
            "records"
        )
    ):
        row = {
            "#":
                int(
                    prompt[
                        "base_prompt_order"
                    ]
                ),
            "Customer question":
                prompt[
                    "prompt_text"
                ],
        }

        prompt_rows = stability[
            stability[
                "base_prompt_order"
            ]
            == prompt[
                "base_prompt_order"
            ]
        ]

        for provider in (
            provider_names
        ):
            provider_row = (
                prompt_rows[
                    prompt_rows[
                        "provider"
                    ]
                    == provider
                ]
            )

            if provider_row.empty:
                row[
                    provider
                ] = "…"
                continue

            item = (
                provider_row.iloc[
                    0
                ]
            )

            valid = int(
                item[
                    "valid_repeats"
                ]
            )
            hits = int(
                item[
                    "target_hits"
                ]
            )
            position = item[
                "average_position"
            ]

            if valid <= 1:
                if hits:
                    row[
                        provider
                    ] = (
                        "✓ #"
                        + str(
                            int(
                                round(
                                    float(
                                        position
                                    )
                                )
                            )
                        )
                    )
                else:
                    row[
                        provider
                    ] = "—"
            else:
                value = (
                    f"{hits}/{valid}"
                )

                if (
                    hits
                    and pd.notna(
                        position
                    )
                ):
                    value += (
                        f" · avg #{float(position):.1f}"
                    )

                row[
                    provider
                ] = value

        matrix_rows.append(
            row
        )

    st.dataframe(
        pd.DataFrame(
            matrix_rows
        ),
        use_container_width=True,
        hide_index=True,
        height=650,
    )


# =========================================================
# 6. HANDOFF TO THE EXISTING PRODUCT
# =========================================================

st.write(
    "### Continue into the deep diagnostic"
)

if (
    not run_target_id.startswith(
        "discovery:"
    )
):
    st.success(
        "The target already matches a business in the "
        "structured dataset. You can now use the existing "
        "deep-diagnostic workflow without re-creating the "
        "target."
    )

    link_columns = st.columns(3)

    with link_columns[0]:
        st.page_link(
            "pages/3_Competitor_Matcher.py",
            label="Open Competitor Matcher",
        )

    with link_columns[1]:
        st.page_link(
            "pages/5_Website_Audits.py",
            label="Open Website Audits",
        )

    with link_columns[2]:
        st.page_link(
            "pages/8_AI_Visibility.py",
            label="Open full AI Visibility",
        )
else:
    st.info(
        "This target was not yet in the structured business "
        "dataset. The next deep-diagnostic step is to import "
        "the target and the highest-value AI competitors, "
        "then run the existing feature, website and review "
        "workflows."
    )


# =========================================================
# RAW EVIDENCE
# =========================================================

with st.expander(
    "Inspect raw model evidence"
):
    result_options = (
        results.index.tolist()
    )

    selected_index = st.selectbox(
        "Response",
        options=result_options,
        format_func=lambda index: (
            f"{results.loc[index, 'provider']} — "
            f"Prompt {int(results.loc[index, 'base_prompt_order'])}"
            f" / repeat {int(results.loc[index, 'repeat_index'])}: "
            f"{results.loc[index, 'prompt_text']}"
        ),
        key=(
            "discovery_raw_response_"
            + selected_run_id
        ),
    )

    selected_result = (
        results.loc[
            selected_index
        ]
    )

    st.write(
        f"**Provider:** {selected_result['provider']}  \n"
        f"**Model:** {selected_result['model']}  \n"
        f"**Finish reason:** "
        f"{selected_result.get('finish_reason') or '—'}  \n"
        f"**Target recommended:** "
        f"{'Yes' if bool(selected_result.get('target_recommended')) else 'No'}"
    )

    st.text_area(
        "Raw response",
        value=str(
            selected_result.get(
                "raw_response"
            )
            or ""
        ),
        height=350,
        disabled=True,
    )


with st.expander(
    "Methodology"
):
    st.write(
        "The AI Discovery Scan is deliberately an "
        "**AI-first reconnaissance route**. It does not "
        "require a pre-built commercial competitor cohort."
    )

    st.write(
        "Core prompts are generated from the category, "
        "location and client propositions. The business "
        "name itself is not inserted into the prompts."
    )

    st.write(
        "Visibility Rate measures how often the target is "
        "recommended. Share of Recommendation measures the "
        "target's share of all numbered recommendation "
        "slots. The AI recommendation market includes every "
        "venue extracted from valid answers."
    )

    st.write(
        "Resolved AI-discovered businesses can immediately "
        "enter the existing website/review diagnostic. "
        "Unresolved businesses can be queued for a targeted "
        "Maps lookup and then imported."
    )

    st.write(
        "This scan complements rather than replaces the "
        "existing evidence-first workflow. The deeper "
        "commercial competitor, website, review and "
        "benchmark layers remain the more rigorous route "
        "for explaining why a business is winning or losing."
    )
