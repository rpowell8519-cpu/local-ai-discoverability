from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st
from sqlalchemy import text


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT))

from src.ai_prompt_generator import (
    generate_prompts,
)
from src.ai_visibility_analysis import (
    reanalyse_results,
    visibility_summary,
)
from src.ai_recommendation_intelligence import (
    build_business_share_table,
    build_intent_stability_table,
    build_provider_share_table,
    build_recommendation_records,
)
from src.ai_visibility_repository import (
    create_visibility_queries,
    create_visibility_run,
    get_latest_run,
    get_run_queries,
    get_run_results,
)
from src.ai_visibility_runner import (
    build_retry_plan,
    execute_calls,
    finalise_run_from_results,
)
from src.database import get_engine
from src.review_repository import (
    get_reviews,
)
from src.taxonomy import GROUP_LABELS


BUILD_VERSION = "AI Results Intelligence v1.2"

DEFAULT_MODELS = {
    "OpenAI": "gpt-5.6-terra",
    "Claude": "claude-sonnet-5",
    "Gemini": "gemini-3.6-flash",
}


st.set_page_config(
    page_title="AI Visibility",
    page_icon="🤖",
    layout="wide",
)

st.title("AI Visibility")
st.caption(
    "Test whether major AI models recommend the target "
    "business for realistic local customer questions."
)
st.caption(f"Build: {BUILD_VERSION}")

st.info(
    "V1.2 is a **model-memory benchmark**. It measures both "
    "target visibility and **Share of Recommendation** across "
    "every numbered venue recommendation. It also identifies "
    "AI-discovered competitors outside the approved commercial "
    "cohort. Search/browsing remains disabled."
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
    except (TypeError, ValueError):
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


@st.cache_data(ttl=300)
def load_businesses() -> pd.DataFrame:
    engine = get_engine()

    query = text(
        """
        select
            bf.google_place_id,
            bf.business_name,
            bf.primary_group,
            bf.business_format,
            coalesce(
                nullif(
                    rol.raw_data->>'city',
                    ''
                ),
                nullif(
                    rol.raw_data->>'borough',
                    ''
                ),
                nullif(
                    rol.raw_data->>'district',
                    ''
                ),
                'Brighton and Hove'
            ) as location_hint
        from business_features bf
        join raw_outscraper_locations rol
          on rol.google_place_id =
             bf.google_place_id
        order by bf.business_name
        """
    )

    with engine.connect() as connection:
        rows = connection.execute(
            query
        ).mappings().all()

    return pd.DataFrame(rows)



@st.cache_data(ttl=120)
def load_evidence_status(
    google_place_ids: list[str],
) -> pd.DataFrame:
    columns = [
        "google_place_id",
        "latest_website_audit",
        "website_audit_status",
        "website_score",
        "reviews_stored",
    ]

    if not google_place_ids:
        return pd.DataFrame(
            columns=columns
        )

    engine = get_engine()

    query = text(
        """
        with latest_audits as (
            select distinct on (
                google_place_id
            )
                google_place_id,
                completed_at
                    as latest_website_audit,
                audit_status
                    as website_audit_status,
                website_completeness_score
                    as website_score
            from website_audit_runs
            where google_place_id = any(
                :google_place_ids
            )
            order by
                google_place_id,
                completed_at desc nulls last,
                started_at desc
        ),
        review_counts as (
            select
                google_place_id,
                count(*)::integer
                    as reviews_stored
            from business_reviews
            where google_place_id = any(
                :google_place_ids
            )
            group by google_place_id
        )
        select
            ids.google_place_id,
            la.latest_website_audit,
            la.website_audit_status,
            la.website_score,
            coalesce(
                rc.reviews_stored,
                0
            ) as reviews_stored
        from unnest(
            cast(
                :google_place_ids
                as text[]
            )
        ) as ids(
            google_place_id
        )
        left join latest_audits la
          on la.google_place_id =
             ids.google_place_id
        left join review_counts rc
          on rc.google_place_id =
             ids.google_place_id
        """
    )

    with engine.connect() as connection:
        rows = connection.execute(
            query,
            {
                "google_place_ids":
                    google_place_ids,
            },
        ).mappings().all()

    return pd.DataFrame(
        rows,
        columns=columns,
    )


@st.cache_data(ttl=60)
def load_saved_cohort(
    target_google_place_id: str,
) -> pd.DataFrame:
    engine = get_engine()

    query = text(
        """
        select
            crr.candidate_google_place_id
                as google_place_id,
            crr.relationship_status,
            bf.business_name,
            bf.primary_group,
            bf.business_format
        from competitor_relationship_reviews crr
        join business_features bf
          on bf.google_place_id =
             crr.candidate_google_place_id
        where
            crr.target_google_place_id =
                :target_google_place_id
        order by
            crr.relationship_status,
            bf.business_name
        """
    )

    columns = [
        "google_place_id",
        "relationship_status",
        "business_name",
        "primary_group",
        "business_format",
    ]

    with engine.connect() as connection:
        rows = connection.execute(
            query,
            {
                "target_google_place_id":
                    target_google_place_id,
            },
        ).mappings().all()

    return pd.DataFrame(
        rows,
        columns=columns,
    )


try:
    businesses = load_businesses()
except Exception as exc:
    st.error(
        "Business data could not be loaded."
    )
    st.exception(exc)
    st.stop()


if businesses.empty:
    st.warning(
        "No business features are available."
    )
    st.stop()


available_groups = sorted(
    businesses[
        "primary_group"
    ]
    .dropna()
    .astype(str)
    .unique()
    .tolist(),
    key=lambda key: (
        GROUP_LABELS.get(
            key,
            key,
        )
    ),
)

default_group_index = (
    available_groups.index(
        "bars_pubs"
    )
    if "bars_pubs"
    in available_groups
    else 0
)


st.sidebar.header("Visibility target")

selected_group = st.sidebar.selectbox(
    "Canonical group",
    options=available_groups,
    index=default_group_index,
    format_func=lambda value: (
        GROUP_LABELS.get(
            value,
            value,
        )
    ),
)

target_options = businesses[
    businesses[
        "primary_group"
    ]
    == selected_group
].copy()

target_options = target_options.sort_values(
    "business_name"
)

target_ids = (
    target_options[
        "google_place_id"
    ]
    .dropna()
    .astype(str)
    .drop_duplicates()
    .tolist()
)

target_name_lookup = (
    target_options
    .assign(
        google_place_id=lambda frame: (
            frame[
                "google_place_id"
            ].astype(str)
        )
    )
    .drop_duplicates(
        "google_place_id"
    )
    .set_index(
        "google_place_id"
    )["business_name"]
    .to_dict()
)

default_target_index = 0

for index, place_id in enumerate(
    target_ids
):
    if str(
        target_name_lookup.get(
            place_id,
            "",
        )
    ).lower() in {
        "the george payne pub",
        "george payne",
    }:
        default_target_index = index
        break


target_id = st.sidebar.selectbox(
    "Target business",
    options=target_ids,
    index=default_target_index,
    format_func=lambda value: (
        target_name_lookup.get(
            value,
            value,
        )
    ),
)

target_row = businesses[
    businesses[
        "google_place_id"
    ].astype(str)
    == str(target_id)
].iloc[0].to_dict()

target_name = str(
    target_row.get(
        "business_name"
    )
    or target_id
)

default_location = str(
    target_row.get(
        "location_hint"
    )
    or "Brighton and Hove"
)

location_context = st.sidebar.text_input(
    "Customer search location",
    value=default_location,
)


try:
    saved_cohort = load_saved_cohort(
        str(target_id)
    )
except Exception as exc:
    st.error(
        "Saved competitor decisions could not be loaded."
    )
    st.exception(exc)
    st.stop()


st.sidebar.divider()
st.sidebar.header("Known competitor set")

cohort_scope = st.sidebar.selectbox(
    "Use for mention detection",
    options=[
        "Direct competitors",
        "Direct + indirect competitors",
        "Direct + indirect + possible",
    ],
    index=1,
)

if cohort_scope == "Direct competitors":
    included_statuses = {
        "direct",
    }
elif (
    cohort_scope
    == "Direct + indirect competitors"
):
    included_statuses = {
        "direct",
        "indirect",
    }
else:
    included_statuses = {
        "direct",
        "indirect",
        "possible",
    }

if saved_cohort.empty:
    selected_cohort = (
        saved_cohort.copy()
    )
else:
    selected_cohort = saved_cohort[
        saved_cohort[
            "relationship_status"
        ].isin(
            included_statuses
        )
    ].copy()

st.sidebar.caption(
    f"{len(selected_cohort)} known competitor(s)"
)


known_businesses = [
    {
        "google_place_id":
            str(target_id),
        "business_name":
            target_name,
    }
]

if not selected_cohort.empty:
    known_businesses.extend(
        [
            {
                "google_place_id":
                    str(
                        row[
                            "google_place_id"
                        ]
                    ),
                "business_name":
                    str(
                        row[
                            "business_name"
                        ]
                    ),
            }
            for row in (
                selected_cohort
                .to_dict("records")
            )
        ]
    )


st.sidebar.divider()
st.sidebar.header("Providers")

api_keys = {
    "OpenAI": secret_value(
        "OPENAI_API_KEY"
    ),
    "Claude": secret_value(
        "ANTHROPIC_API_KEY"
    ),
    "Gemini": secret_value(
        "GEMINI_API_KEY"
    ),
}

selected_providers = []

for provider_name in [
    "OpenAI",
    "Claude",
    "Gemini",
]:
    available = bool(
        api_keys[
            provider_name
        ]
    )

    enabled = st.sidebar.checkbox(
        provider_name,
        value=available,
        disabled=not available,
    )

    if enabled:
        selected_providers.append(
            provider_name
        )


with st.sidebar.expander(
    "Model settings"
):
    model_values = {
        "OpenAI": st.text_input(
            "OpenAI model",
            value=secret_value(
                "OPENAI_MODEL",
                DEFAULT_MODELS[
                    "OpenAI"
                ],
            ),
        ),
        "Claude": st.text_input(
            "Claude model",
            value=secret_value(
                "ANTHROPIC_MODEL",
                DEFAULT_MODELS[
                    "Claude"
                ],
            ),
        ),
        "Gemini": st.text_input(
            "Gemini model",
            value=secret_value(
                "GEMINI_MODEL",
                DEFAULT_MODELS[
                    "Gemini"
                ],
            ),
        ),
    }


try:
    target_reviews = get_reviews(
        [
            str(target_id)
        ]
    )
except Exception:
    target_reviews = pd.DataFrame()


prompt_state_key = (
    "ai_prompt_editor_"
    + str(target_id)
    + "_"
    + location_context.strip().lower()
)

if (
    prompt_state_key
    not in st.session_state
):
    st.session_state[
        prompt_state_key
    ] = generate_prompts(
        primary_group=(
            selected_group
        ),
        location=(
            location_context
        ),
        reviews=(
            target_reviews
        ),
        max_prompts=20,
    )


st.subheader("1. Review the test questions")

st.write(
    "The target and competitor names are not inserted "
    "into these customer questions. You can edit, add "
    "or remove prompts before running the benchmark."
)

control_columns = st.columns(
    [1, 1, 3]
)

with control_columns[0]:
    if st.button(
        "Regenerate prompts"
    ):
        st.session_state[
            prompt_state_key
        ] = generate_prompts(
            primary_group=(
                selected_group
            ),
            location=(
                location_context
            ),
            reviews=(
                target_reviews
            ),
            max_prompts=20,
        )
        st.rerun()

with control_columns[1]:
    if st.button(
        "Use first 5 only"
    ):
        prompt_frame = (
            st.session_state[
                prompt_state_key
            ].copy()
        )

        prompt_frame[
            "include"
        ] = False

        if not prompt_frame.empty:
            prompt_frame.loc[
                prompt_frame.index[
                    :5
                ],
                "include",
            ] = True

        st.session_state[
            prompt_state_key
        ] = prompt_frame
        st.rerun()


edited_prompts = st.data_editor(
    st.session_state[
        prompt_state_key
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
    key=(
        "prompt_data_editor_"
        + str(target_id)
    ),
)

st.session_state[
    prompt_state_key
] = edited_prompts.copy()

selected_prompt_frame = edited_prompts[
    edited_prompts[
        "include"
    ].fillna(False)
].copy()

selected_prompt_frame[
    "prompt"
] = (
    selected_prompt_frame[
        "prompt"
    ]
    .fillna("")
    .astype(str)
    .str.strip()
)

selected_prompt_frame = (
    selected_prompt_frame[
        selected_prompt_frame[
            "prompt"
        ].ne("")
    ]
)

st.write("### Sampling")

repetitions = st.select_slider(
    "Repetitions per customer question",
    options=[1, 2, 3],
    value=1,
    help=(
        "Use 1 for quick QA. Use 3 for a more robust "
        "client benchmark: repeated sampling lets us "
        "measure how consistently each model recommends "
        "the business rather than treating one answer "
        "as deterministic."
    ),
)

total_api_calls = (
    len(selected_prompt_frame)
    * len(selected_providers)
    * int(repetitions)
)

st.caption(
    f"{len(selected_prompt_frame)} customer question(s) × "
    f"{int(repetitions)} repetition(s) × "
    f"{len(selected_providers)} provider(s) = "
    f"{total_api_calls} API call(s). Providers for each "
    "question/repetition run in parallel."
)

if repetitions == 3:
    st.success(
        "3 repetitions is the recommended client-grade "
        "sampling level for this stage of the pilot."
    )


st.divider()
st.subheader("2. Run or resume benchmark")


def run_progress_ui():
    progress = st.progress(0)
    status_box = st.empty()

    def progress_callback(
        processed: int,
        total: int,
    ):
        progress.progress(
            processed / max(
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

    return (
        progress,
        status_box,
        progress_callback,
        status_callback,
    )


run_button = st.button(
    "Run new AI visibility test",
    type="primary",
    disabled=(
        len(
            selected_prompt_frame
        )
        == 0
        or len(
            selected_providers
        )
        == 0
    ),
)

if run_button:
    prompt_records = (
        selected_prompt_frame[
            [
                "category",
                "source",
                "prompt",
            ]
        ]
        .to_dict("records")
    )

    models_for_run = {
        provider: (
            model_values[
                provider
            ]
        )
        for provider
        in selected_providers
    }

    run_id = create_visibility_run(
        target_google_place_id=(
            str(target_id)
        ),
        target_business_name=(
            target_name
        ),
        primary_group=(
            selected_group
        ),
        location_context=(
            location_context
        ),
        providers=(
            selected_providers
        ),
        models=(
            models_for_run
        ),
        prompt_count=len(
            prompt_records
        ),
        repeat_count=int(
            repetitions
        ),
    )

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

    (
        progress,
        status_box,
        progress_callback,
        status_callback,
    ) = run_progress_ui()

    execute_calls(
        run_id=run_id,
        call_plan=call_plan,
        models=models_for_run,
        api_keys=api_keys,
        target_google_place_id=(
            str(target_id)
        ),
        target_business_name=(
            target_name
        ),
        known_businesses=(
            known_businesses
        ),
        progress_callback=(
            progress_callback
        ),
        status_callback=(
            status_callback
        ),
    )

    status_box.empty()

    finalise_run_from_results(
        run_id=run_id,
        expected_call_count=len(
            call_plan
        ),
    )

    st.cache_data.clear()
    st.success(
        "Benchmark finished. Results have been "
        "saved after every individual API call."
    )
    st.rerun()


try:
    latest_run = get_latest_run(
        str(target_id)
    )
except Exception as exc:
    st.info(
        "The AI Visibility reliability columns are not "
        "available yet. Run the supplied SQL migration."
    )
    st.exception(exc)
    st.stop()


latest_queries = pd.DataFrame()
latest_results = pd.DataFrame()
retry_plan = []
latest_run_providers = []
latest_run_models = {}

if latest_run:
    latest_run_id = str(
        latest_run["id"]
    )

    latest_queries = (
        get_run_queries(
            latest_run_id
        )
    )

    latest_results = (
        get_run_results(
            latest_run_id
        )
    )

    latest_run_providers = [
        str(item)
        for item in jsonish(
            latest_run.get(
                "providers"
            ),
            [],
        )
    ]

    latest_run_models = {
        str(key): str(value)
        for key, value in jsonish(
            latest_run.get(
                "models"
            ),
            {},
        ).items()
    }

    retry_plan = build_retry_plan(
        queries=latest_queries,
        results=latest_results,
        providers=(
            latest_run_providers
        ),
    )


if latest_run and retry_plan:
    pending_counts = {}

    for item in retry_plan:
        provider = str(
            item["provider"]
        )
        pending_counts[
            provider
        ] = (
            pending_counts.get(
                provider,
                0,
            )
            + 1
        )

    st.warning(
        "The latest run has missing, failed or "
        "truncated responses. They are excluded from "
        "visibility scoring and can be resumed without "
        "repeating valid calls."
    )

    retry_provider_options = [
        provider
        for provider in (
            latest_run_providers
        )
        if pending_counts.get(
            provider,
            0,
        )
        > 0
    ]

    retry_providers = st.multiselect(
        "Providers to resume/retry",
        options=(
            retry_provider_options
        ),
        default=(
            retry_provider_options
        ),
        format_func=lambda provider: (
            f"{provider} "
            f"({pending_counts.get(provider, 0)} call(s))"
        ),
    )

    filtered_retry_plan = [
        item
        for item in retry_plan
        if item[
            "provider"
        ]
        in retry_providers
    ]

    if st.button(
        f"Resume/retry {len(filtered_retry_plan)} incomplete call(s)",
        disabled=(
            not filtered_retry_plan
        ),
    ):
        unavailable = [
            provider
            for provider
            in retry_providers
            if not api_keys.get(
                provider
            )
        ]

        if unavailable:
            st.error(
                "Missing API secret(s) for: "
                + ", ".join(
                    unavailable
                )
            )
        else:
            (
                progress,
                status_box,
                progress_callback,
                status_callback,
            ) = run_progress_ui()

            execute_calls(
                run_id=(
                    latest_run_id
                ),
                call_plan=(
                    filtered_retry_plan
                ),
                models=(
                    latest_run_models
                ),
                api_keys=api_keys,
                target_google_place_id=(
                    str(target_id)
                ),
                target_business_name=(
                    target_name
                ),
                known_businesses=(
                    known_businesses
                ),
                progress_callback=(
                    progress_callback
                ),
                status_callback=(
                    status_callback
                ),
            )

            status_box.empty()

            expected_call_count = (
                len(
                    latest_queries
                )
                * len(
                    latest_run_providers
                )
            )

            finalise_run_from_results(
                run_id=(
                    latest_run_id
                ),
                expected_call_count=(
                    expected_call_count
                ),
            )

            st.cache_data.clear()
            st.success(
                "Resume/retry finished. Valid previous "
                "responses were not repeated."
            )
            st.rerun()


st.divider()
st.subheader("3. Latest visibility results")

if not latest_run:
    st.info(
        "No AI visibility test has been run for this "
        "target yet."
    )
    st.stop()

if latest_results.empty:
    st.info(
        "The latest run does not yet contain results."
    )
    st.stop()


# Re-run the latest detection logic over stored raw responses. This fixes
# historical V1 ranking without requiring the paid model calls to be run
# again.
results = reanalyse_results(
    latest_results,
    target_google_place_id=(
        str(target_id)
    ),
    target_business_name=(
        target_name
    ),
    known_businesses=(
        known_businesses
    ),
)

summary = visibility_summary(
    results
)

if not summary.empty:
    metric_columns = st.columns(
        len(summary)
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

            if (
                rate is None
                or pd.isna(rate)
            ):
                metric_value = (
                    "No valid responses"
                )
            else:
                metric_value = (
                    f"{float(rate):.0%} visible"
                )

            average_position = row[
                "average_position"
            ]

            delta = None

            if (
                average_position
                is not None
                and pd.notna(
                    average_position
                )
            ):
                delta = (
                    "Avg position "
                    f"{float(average_position):.1f}"
                )

            st.metric(
                str(
                    row["provider"]
                ),
                metric_value,
                delta=delta,
            )

            if (
                row[
                    "incomplete_responses"
                ]
                or row[
                    "failed_responses"
                ]
            ):
                st.caption(
                    f"{row['incomplete_responses']} incomplete · "
                    f"{row['failed_responses']} failed"
                )

    expected_responses_per_provider = (
        len(
            latest_queries
        )
    )

    summary_display = (
        summary.copy()
    )

    summary_display[
        "Missing"
    ] = summary_display.apply(
        lambda row: max(
            expected_responses_per_provider
            - int(
                row[
                    "valid_responses"
                ]
            )
            - int(
                row[
                    "incomplete_responses"
                ]
            )
            - int(
                row[
                    "failed_responses"
                ]
            ),
            0,
        ),
        axis=1,
    )

    summary_display[
        "Visibility"
    ] = summary_display[
        "visibility_rate"
    ].apply(
        lambda value: (
            f"{float(value):.0%}"
            if (
                value is not None
                and pd.notna(value)
            )
            else "—"
        )
    )

    summary_display[
        "Avg position"
    ] = summary_display[
        "average_position"
    ].apply(
        lambda value: (
            f"{float(value):.1f}"
            if pd.notna(value)
            else "—"
        )
    )

    st.dataframe(
        summary_display[
            [
                "provider",
                "valid_responses",
                "incomplete_responses",
                "failed_responses",
                "Missing",
                "target_recommendations",
                "Visibility",
                "Avg position",
                "input_tokens",
                "output_tokens",
                "reasoning_tokens",
            ]
        ].rename(
            columns={
                "provider":
                    "Provider",
                "valid_responses":
                    "Valid",
                "incomplete_responses":
                    "Incomplete",
                "failed_responses":
                    "Failed",
                "target_recommendations":
                    "Target recommendations",
                "input_tokens":
                    "Input tokens",
                "output_tokens":
                    "Output tokens",
                "reasoning_tokens":
                    "Reasoning tokens",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )



# -----------------------------
# Recommendation market
# -----------------------------

commercial_competitor_ids = set(
    selected_cohort[
        "google_place_id"
    ]
    .dropna()
    .astype(str)
    .tolist()
)

recommendations = (
    build_recommendation_records(
        results=results,
        businesses=businesses,
        target_google_place_id=(
            str(target_id)
        ),
        commercial_competitor_ids=(
            commercial_competitor_ids
        ),
        primary_group=(
            selected_group
        ),
    )
)

provider_share = (
    build_provider_share_table(
        recommendations,
        target_google_place_id=(
            str(target_id)
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

    st.caption(
        "Share of Recommendation = the target's share of "
        "all numbered venue recommendation slots returned "
        "by that provider. Position-weighted share gives "
        "higher value to recommendations nearer #1."
    )

    overall_share_rows = (
        provider_share[
            provider_share[
                "provider"
            ]
            == "All providers"
        ]
    )

    if not overall_share_rows.empty:
        overall_share = (
            overall_share_rows.iloc[0]
        )

        overall_columns = (
            st.columns(3)
        )

        with overall_columns[0]:
            st.metric(
                "Overall Share of Recommendation",
                f"{float(overall_share['share_of_recommendation']):.1%}",
            )

        with overall_columns[1]:
            st.metric(
                "Position-weighted share",
                f"{float(overall_share['position_weighted_share']):.1%}",
            )

        with overall_columns[2]:
            st.metric(
                "Target recommendation slots",
                (
                    f"{int(overall_share['target_recommendations'])}"
                    f" / {int(overall_share['recommendation_slots'])}"
                ),
            )

    share_display = (
        provider_share.copy()
    )

    share_display[
        "Share of Recommendation"
    ] = share_display[
        "share_of_recommendation"
    ].apply(
        lambda value: (
            f"{float(value):.1%}"
        )
    )

    share_display[
        "Position-weighted share"
    ] = share_display[
        "position_weighted_share"
    ].apply(
        lambda value: (
            f"{float(value):.1%}"
        )
    )

    st.dataframe(
        share_display[
            [
                "provider",
                "recommendation_slots",
                "target_recommendations",
                "Share of Recommendation",
                "Position-weighted share",
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
        "This includes every venue extracted from valid "
        "model answers — not only the approved commercial "
        "competitor set."
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

    display_columns = [
        "business_name",
        "classification",
        "recommendations",
        "Share",
        "Weighted share",
        "Avg position",
        *provider_columns,
    ]

    rename_map = {
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

    st.dataframe(
        market_display[
            display_columns
        ].head(40).rename(
            columns=rename_map
        ),
        use_container_width=True,
        hide_index=True,
        height=700,
    )


# -----------------------------
# AI-discovered competitor queue
# -----------------------------

if not business_share.empty:
    ai_discovered = (
        business_share[
            business_share[
                "classification"
            ]
            == "AI-discovered"
        ].copy()
    )

    if not ai_discovered.empty:
        resolved_ids = (
            ai_discovered[
                "google_place_id"
            ]
            .dropna()
            .astype(str)
            .tolist()
        )

        try:
            evidence_status = (
                load_evidence_status(
                    resolved_ids
                )
            )
        except Exception:
            evidence_status = pd.DataFrame()

        if not evidence_status.empty:
            evidence_status[
                "google_place_id"
            ] = evidence_status[
                "google_place_id"
            ].astype(str)

            ai_discovered[
                "google_place_id"
            ] = ai_discovered[
                "google_place_id"
            ].astype(str)

            ai_discovered = (
                ai_discovered.merge(
                    evidence_status,
                    on="google_place_id",
                    how="left",
                )
            )
        else:
            ai_discovered[
                "latest_website_audit"
            ] = None
            ai_discovered[
                "website_audit_status"
            ] = None
            ai_discovered[
                "website_score"
            ] = None
            ai_discovered[
                "reviews_stored"
            ] = 0

        ai_discovered[
            "Website audit"
        ] = ai_discovered[
            "latest_website_audit"
        ].apply(
            lambda value: (
                "Yes"
                if pd.notna(value)
                else "No"
            )
        )

        ai_discovered[
            "Reviews"
        ] = pd.to_numeric(
            ai_discovered[
                "reviews_stored"
            ],
            errors="coerce",
        ).fillna(0).astype(int)

        def readiness_label(
            row,
        ):
            has_site = (
                row[
                    "Website audit"
                ]
                == "Yes"
            )
            has_reviews = (
                int(
                    row[
                        "Reviews"
                    ]
                )
                > 0
            )

            if (
                has_site
                and has_reviews
            ):
                return (
                    "Ready to compare"
                )

            if (
                not has_site
                and not has_reviews
            ):
                return (
                    "Need website + reviews"
                )

            if not has_site:
                return (
                    "Need website audit"
                )

            return (
                "Need reviews"
            )

        ai_discovered[
            "Diagnostic readiness"
        ] = ai_discovered.apply(
            readiness_label,
            axis=1,
        )

        ai_discovered[
            "Share"
        ] = ai_discovered[
            "share_of_recommendation"
        ].apply(
            lambda value: (
                f"{float(value):.1%}"
            )
        )

        st.write(
            "### AI-discovered competitor diagnostic queue"
        )

        st.caption(
            "These businesses were not in the approved "
            "commercial cohort but the AI models repeatedly "
            "placed them into the same recommendation market. "
            "They are candidates for website/review diagnostic "
            "comparison."
        )

        st.dataframe(
            ai_discovered[
                [
                    "business_name",
                    "recommendations",
                    "providers",
                    "Share",
                    "average_position",
                    "Website audit",
                    "Reviews",
                    "Diagnostic readiness",
                ]
            ].rename(
                columns={
                    "business_name":
                        "Business",
                    "recommendations":
                        "AI recommendations",
                    "providers":
                        "Providers",
                    "average_position":
                        "Avg position",
                }
            ),
            use_container_width=True,
            hide_index=True,
            height=500,
        )

    unresolved = (
        business_share[
            business_share[
                "classification"
            ]
            == "Unresolved"
        ].copy()
    )

    if not unresolved.empty:
        with st.expander(
            "Unresolved AI-recommended venue names"
        ):
            st.write(
                "These names could not be confidently "
                "matched to the current business database. "
                "They may be outside the original ~800 "
                "business pull, naming variants, or "
                "occasionally model errors."
            )

            st.dataframe(
                unresolved[
                    [
                        "business_name",
                        "recommendations",
                        "providers",
                        "average_position",
                    ]
                ].rename(
                    columns={
                        "business_name":
                            "Raw venue name",
                        "recommendations":
                            "Recommendations",
                        "providers":
                            "Providers",
                        "average_position":
                            "Avg position",
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )


# -----------------------------
# Repeated-sampling stability
# -----------------------------

st.write(
    "### Intent stability"
)

stability = (
    build_intent_stability_table(
        results
    )
)

if stability.empty:
    st.info(
        "No valid repeated-sampling results are available."
    )
else:
    matrix_rows = []

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
            latest_run_providers
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
                ] = "… missing"
                continue

            item = (
                provider_row.iloc[0]
            )

            valid_repeats = int(
                item[
                    "valid_repeats"
                ]
            )
            target_hits = int(
                item[
                    "target_hits"
                ]
            )
            invalid = int(
                item[
                    "incomplete_or_failed"
                ]
            )

            if valid_repeats == 0:
                value = (
                    "⚠ no valid response"
                )
            elif valid_repeats == 1:
                if target_hits:
                    position = (
                        item[
                            "average_position"
                        ]
                    )

                    value = (
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
                    value = "—"
            else:
                position = (
                    item[
                        "average_position"
                    ]
                )

                value = (
                    f"{target_hits}/{valid_repeats}"
                )

                if (
                    target_hits
                    and pd.notna(
                        position
                    )
                ):
                    value += (
                        f" · avg #{float(position):.1f}"
                    )

            if invalid:
                value += (
                    f" · {invalid} invalid"
                )

            row[
                provider
            ] = value

        matrix_rows.append(row)

    st.dataframe(
        pd.DataFrame(
            matrix_rows
        ),
        use_container_width=True,
        hide_index=True,
        height=700,
    )

st.write(
    "### Inspect raw model response"
)

response_options = (
    results.index.tolist()
)

selected_response_index = (
    st.selectbox(
        "Result",
        options=response_options,
        format_func=lambda index: (
            f"{results.loc[index, 'provider']} — "
            f"Prompt {int(results.loc[index, 'base_prompt_order'])}"
            f" / repeat {int(results.loc[index, 'repeat_index'])}: "
            f"{results.loc[index, 'prompt_text']}"
        ),
    )
)

selected_result = results.loc[
    selected_response_index
]

completion_label = (
    "Valid complete response"
    if (
        selected_result[
            "status"
        ]
        == "completed"
        and bool(
            selected_result[
                "response_complete"
            ]
        )
    )
    else (
        "Incomplete / truncated"
        if selected_result[
            "status"
        ]
        == "completed"
        else "Failed"
    )
)

st.write(
    f"**Provider:** {selected_result['provider']}  \n"
    f"**Model:** {selected_result['model']}  \n"
    f"**Completion:** {completion_label}  \n"
    f"**Finish reason:** "
    f"{selected_result.get('finish_reason') or '—'}  \n"
    f"**Target recommended:** "
    f"{'Yes' if bool(selected_result.get('target_recommended')) else 'No'}  \n"
    f"**Recommendation position:** "
    f"{int(selected_result['target_position']) if pd.notna(selected_result.get('target_position')) else '—'}"
)

if (
    selected_result[
        "status"
    ]
    == "completed"
):
    token_columns = st.columns(4)

    token_values = [
        (
            "Input tokens",
            selected_result.get(
                "input_tokens"
            ),
        ),
        (
            "Visible output",
            selected_result.get(
                "output_tokens"
            ),
        ),
        (
            "Reasoning tokens",
            selected_result.get(
                "reasoning_tokens"
            ),
        ),
        (
            "Total tokens",
            selected_result.get(
                "total_tokens"
            ),
        ),
    ]

    for column, (
        label,
        value,
    ) in zip(
        token_columns,
        token_values,
    ):
        with column:
            st.metric(
                label,
                (
                    int(value)
                    if pd.notna(
                        value
                    )
                    else "—"
                ),
            )

    st.text_area(
        "Raw response",
        value=str(
            selected_result[
                "raw_response"
            ]
            or ""
        ),
        height=350,
        disabled=True,
    )
else:
    st.error(
        str(
            selected_result[
                "error_message"
            ]
            or "Provider call failed."
        )
    )


with st.expander(
    "Methodology and limitations"
):
    st.write(
        "Visibility Rate answers: **how often is the target "
        "recommended for the tested customer questions?**"
    )

    st.write(
        "Share of Recommendation answers: **what share of "
        "all numbered recommendation slots does the target "
        "occupy?** This includes businesses outside the "
        "pre-approved competitor cohort."
    )

    st.write(
        "Position-weighted Share of Recommendation uses "
        "1 / recommendation rank, so #1 recommendations "
        "contribute more than #5 recommendations."
    )

    st.write(
        "Repeated sampling allows the same customer intent "
        "to be tested up to three times per provider. The "
        "Intent stability table reports how often the target "
        "appeared across those repetitions."
    )

    st.write(
        "Business-name resolution first uses exact/alias "
        "matching against business_features, then a high-"
        "confidence fuzzy match. Ambiguous names remain "
        "unresolved rather than being forced to a business."
    )

    st.write(
        "Incomplete, truncated, failed and missing calls "
        "are excluded from the visibility denominator. "
        "They can be retried without repeating valid calls."
    )

    st.write(
        "Gemini runs with minimal thinking for this "
        "simple recommendation task so hidden reasoning "
        "does not consume most of the response budget."
    )

    st.write(
        "V1.1 still detects only the target and known "
        "competitor set. Raw responses are retained so "
        "unknown recommended businesses can be extracted "
        "in a future iteration."
    )

    st.write(
        "API model results are not presented as identical "
        "to the consumer ChatGPT, Claude or Gemini apps, "
        "which may use different search, location and "
        "product orchestration."
    )
