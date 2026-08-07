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
    competitor_mention_summary,
    reanalyse_results,
    visibility_summary,
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


BUILD_VERSION = "AI Visibility v1.1"

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
    "V1.1 is a **model-memory benchmark**. It deliberately "
    "does not enable web-search tools. Visibility is scored "
    "only from valid, naturally completed responses; "
    "truncated, failed or missing calls are excluded."
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

st.caption(
    f"{len(selected_prompt_frame)} prompt(s) × "
    f"{len(selected_providers)} provider(s) = "
    f"{len(selected_prompt_frame) * len(selected_providers)} "
    "API call(s). Providers for each prompt run in "
    "parallel to reduce total run time."
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
    )

    query_records = (
        create_visibility_queries(
            run_id=run_id,
            prompts=prompt_records,
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

    prompt_count = int(
        latest_run.get(
            "prompt_count"
        )
        or len(
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
            prompt_count
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


st.write(
    "### Prompt-by-provider visibility"
)

result_lookup = {}

for row in results.to_dict(
    "records"
):
    result_lookup[
        (
            str(
                row[
                    "query_id"
                ]
            ),
            str(
                row[
                    "provider"
                ]
            ),
        )
    ] = row

matrix_rows = []

for query in latest_queries.to_dict(
    "records"
):
    matrix_row = {
        "#":
            int(
                query[
                    "prompt_order"
                ]
            ),
        "Customer question":
            str(
                query[
                    "prompt_text"
                ]
            ),
    }

    for provider in (
        latest_run_providers
    ):
        result = result_lookup.get(
            (
                str(
                    query[
                        "id"
                    ]
                ),
                provider,
            )
        )

        if result is None:
            value = "… missing"
        elif (
            result.get(
                "status"
            )
            == "failed"
        ):
            value = "✕ failed"
        elif not bool(
            result.get(
                "response_complete"
            )
        ):
            value = "⚠ incomplete"
        elif bool(
            result.get(
                "target_recommended"
            )
        ):
            position = result.get(
                "target_position"
            )

            value = (
                "✓ #"
                + str(
                    int(
                        position
                    )
                )
                if pd.notna(
                    position
                )
                else "✓"
            )
        else:
            value = "—"

        matrix_row[
            provider
        ] = value

    matrix_rows.append(
        matrix_row
    )

st.dataframe(
    pd.DataFrame(
        matrix_rows
    ),
    use_container_width=True,
    hide_index=True,
    height=700,
)


competitor_summary = (
    competitor_mention_summary(
        results
    )
)

if not competitor_summary.empty:
    competitor_summary[
        "Target?"
    ] = competitor_summary[
        "google_place_id"
    ].astype(str).apply(
        lambda value: (
            "Yes"
            if value
            == str(target_id)
            else "No"
        )
    )

    st.write(
        "### Known-business recommendation mentions"
    )

    st.dataframe(
        competitor_summary[
            [
                "business_name",
                "Target?",
                "recommendations",
            ]
        ].rename(
            columns={
                "business_name":
                    "Business",
                "recommendations":
                    "Recommendations",
            }
        ),
        use_container_width=True,
        hide_index=True,
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
            f"Prompt {results.loc[index, 'prompt_order']}: "
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
        "Visibility is now based on an actual numbered "
        "recommendation position, not merely the order "
        "in which known cohort businesses happen to "
        "appear in the response."
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
