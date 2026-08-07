from __future__ import annotations

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
    analyse_visibility_response,
    competitor_mention_summary,
    visibility_summary,
)
from src.ai_visibility_repository import (
    create_visibility_queries,
    create_visibility_run,
    finish_visibility_run,
    get_latest_run,
    get_run_results,
    save_visibility_result,
)
from src.database import get_engine
from src.llm_providers.anthropic_provider import (
    call_anthropic,
)
from src.llm_providers.gemini_provider import (
    call_gemini,
)
from src.llm_providers.openai_provider import (
    call_openai,
)
from src.review_repository import (
    get_reviews,
)
from src.taxonomy import GROUP_LABELS


BUILD_VERSION = "AI Visibility v1.0"

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
    "V1 is a **model-memory benchmark**. It deliberately "
    "does not enable web-search tools. This measures what "
    "the selected API models recommend from their existing "
    "model knowledge, not an exact reproduction of the "
    "consumer ChatGPT, Claude or Gemini apps."
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

target_options = (
    target_options.sort_values(
        "business_name"
    )
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
    help=(
        "This is inserted into the recommendation "
        "questions. Edit it if a broader or more "
        "specific location is more realistic."
    ),
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


st.sidebar.divider()
st.sidebar.header("Providers")

openai_key = secret_value(
    "OPENAI_API_KEY"
)
anthropic_key = secret_value(
    "ANTHROPIC_API_KEY"
)
gemini_key = secret_value(
    "GEMINI_API_KEY"
)

provider_availability = {
    "OpenAI": bool(
        openai_key
    ),
    "Claude": bool(
        anthropic_key
    ),
    "Gemini": bool(
        gemini_key
    ),
}

selected_providers = []

for provider_name in [
    "OpenAI",
    "Claude",
    "Gemini",
]:
    enabled = st.sidebar.checkbox(
        provider_name,
        value=provider_availability[
            provider_name
        ],
        disabled=not (
            provider_availability[
                provider_name
            ]
        ),
        help=(
            None
            if provider_availability[
                provider_name
            ]
            else (
                f"{provider_name} API key "
                "was not found in Streamlit Secrets."
            )
        ),
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
    "These prompts are generated from the business vertical "
    "and, where review data is available, recurring customer "
    "associations. The target business name is never inserted "
    "into the question."
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
                "Run",
                help=(
                    "Only checked prompts "
                    "will be sent."
                ),
            ),
        "category":
            st.column_config.TextColumn(
                "Intent",
            ),
        "source":
            st.column_config.TextColumn(
                "Source",
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

selected_prompt_frame = (
    edited_prompts[
        edited_prompts[
            "include"
        ].fillna(False)
    ].copy()
)

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
    f"{len(selected_prompt_frame)} prompt(s) selected × "
    f"{len(selected_providers)} provider(s) = "
    f"{len(selected_prompt_frame) * len(selected_providers)} "
    "API call(s)."
)


st.divider()
st.subheader("2. Run the model-memory benchmark")

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
            for row in selected_cohort.to_dict(
                "records"
            )
        ]
    )

with st.expander(
    "Known businesses used for result detection"
):
    st.dataframe(
        pd.DataFrame(
            known_businesses
        ).rename(
            columns={
                "business_name":
                    "Business",
                "google_place_id":
                    "Google Place ID",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )


run_button = st.button(
    "Run AI visibility test",
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

    total_calls = (
        len(query_records)
        * len(
            selected_providers
        )
    )

    progress = st.progress(0)
    status_box = st.empty()

    completed_calls = 0
    failed_calls = 0

    for query_record in (
        query_records
    ):
        prompt_text = str(
            query_record[
                "prompt_text"
            ]
        )

        for provider in (
            selected_providers
        ):
            status_box.write(
                f"Testing **{provider}**: "
                f"{prompt_text}"
            )

            model = (
                models_for_run[
                    provider
                ]
            )

            try:
                if provider == "OpenAI":
                    provider_response = (
                        call_openai(
                            api_key=(
                                openai_key
                            ),
                            model=model,
                            prompt=(
                                prompt_text
                            ),
                        )
                    )
                elif provider == "Claude":
                    provider_response = (
                        call_anthropic(
                            api_key=(
                                anthropic_key
                            ),
                            model=model,
                            prompt=(
                                prompt_text
                            ),
                        )
                    )
                else:
                    provider_response = (
                        call_gemini(
                            api_key=(
                                gemini_key
                            ),
                            model=model,
                            prompt=(
                                prompt_text
                            ),
                        )
                    )

                analysis = (
                    analyse_visibility_response(
                        response_text=(
                            provider_response.text
                        ),
                        target_google_place_id=(
                            str(
                                target_id
                            )
                        ),
                        target_business_name=(
                            target_name
                        ),
                        known_businesses=(
                            known_businesses
                        ),
                    )
                )

                save_visibility_result(
                    run_id=run_id,
                    query_id=str(
                        query_record[
                            "id"
                        ]
                    ),
                    provider=provider,
                    model=model,
                    raw_response=(
                        provider_response.text
                    ),
                    analysis=analysis,
                    input_tokens=(
                        provider_response.input_tokens
                    ),
                    output_tokens=(
                        provider_response.output_tokens
                    ),
                    total_tokens=(
                        provider_response.total_tokens
                    ),
                    latency_ms=(
                        provider_response.latency_ms
                    ),
                    status="completed",
                )

                completed_calls += 1

            except Exception as exc:
                save_visibility_result(
                    run_id=run_id,
                    query_id=str(
                        query_record[
                            "id"
                        ]
                    ),
                    provider=provider,
                    model=model,
                    raw_response=None,
                    analysis={
                        "target_mentioned":
                            False,
                        "target_position":
                            None,
                        "mentioned_competitors":
                            [],
                        "mentioned_known_businesses":
                            [],
                    },
                    input_tokens=None,
                    output_tokens=None,
                    total_tokens=None,
                    latency_ms=None,
                    status="failed",
                    error_message=str(
                        exc
                    )[:2000],
                )

                failed_calls += 1

            progress.progress(
                (
                    completed_calls
                    + failed_calls
                )
                / total_calls
            )

    status_box.empty()

    if failed_calls == 0:
        run_status = "completed"
    elif completed_calls > 0:
        run_status = "partial"
    else:
        run_status = "failed"

    finish_visibility_run(
        run_id=run_id,
        status=run_status,
        error_message=(
            (
                f"{failed_calls} API "
                "call(s) failed."
            )
            if failed_calls
            else None
        ),
    )

    st.success(
        f"Run complete: {completed_calls} successful "
        f"API call(s), {failed_calls} failed."
    )

    st.cache_data.clear()
    st.rerun()


st.divider()
st.subheader("3. Latest visibility results")

try:
    latest_run = get_latest_run(
        str(target_id)
    )
except Exception as exc:
    st.info(
        "The AI Visibility database tables are not "
        "available yet. Run the supplied SQL migration."
    )
    st.exception(exc)
    st.stop()


if not latest_run:
    st.info(
        "No AI visibility test has been run for this "
        "target yet."
    )
    st.stop()


latest_run_id = str(
    latest_run["id"]
)

results = get_run_results(
    latest_run_id
)

if results.empty:
    st.info(
        "The latest run does not yet contain results."
    )
    st.stop()


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
            average_position = (
                row[
                    "average_position"
                ]
            )

            st.metric(
                str(
                    row[
                        "provider"
                    ]
                ),
                (
                    f"{row['visibility_rate']:.0%} visible"
                ),
                delta=(
                    (
                        f"Avg position "
                        f"{average_position:.1f}"
                    )
                    if average_position
                    is not None
                    else (
                        "No target mentions"
                    )
                ),
            )

    summary_display = (
        summary.copy()
    )

    summary_display[
        "Visibility"
    ] = summary_display[
        "visibility_rate"
    ].apply(
        lambda value: (
            f"{float(value):.0%}"
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
                "tests_completed",
                "target_mentions",
                "Visibility",
                "Avg position",
                "input_tokens",
                "output_tokens",
            ]
        ].rename(
            columns={
                "provider":
                    "Provider",
                "tests_completed":
                    "Tests",
                "target_mentions":
                    "Target mentions",
                "input_tokens":
                    "Input tokens",
                "output_tokens":
                    "Output tokens",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )


completed_results = results[
    results[
        "status"
    ]
    == "completed"
].copy()

if not completed_results.empty:
    matrix = completed_results[
        [
            "prompt_order",
            "prompt_text",
            "provider",
            "target_mentioned",
            "target_position",
        ]
    ].copy()

    matrix[
        "Result"
    ] = matrix.apply(
        lambda row: (
            (
                "✓ #"
                + str(
                    int(
                        row[
                            "target_position"
                        ]
                    )
                )
            )
            if (
                bool(
                    row[
                        "target_mentioned"
                    ]
                )
                and pd.notna(
                    row[
                        "target_position"
                    ]
                )
            )
            else (
                "✓"
                if bool(
                    row[
                        "target_mentioned"
                    ]
                )
                else "—"
            )
        ),
        axis=1,
    )

    matrix_display = (
        matrix.pivot_table(
            index=[
                "prompt_order",
                "prompt_text",
            ],
            columns="provider",
            values="Result",
            aggfunc="first",
        )
        .reset_index()
        .sort_values(
            "prompt_order"
        )
        .rename(
            columns={
                "prompt_order":
                    "#",
                "prompt_text":
                    "Customer question",
            }
        )
    )

    st.write(
        "### Prompt-by-provider visibility"
    )

    st.dataframe(
        matrix_display,
        use_container_width=True,
        hide_index=True,
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
            == str(
                target_id
            )
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
                "mentions",
            ]
        ].rename(
            columns={
                "business_name":
                    "Business",
                "mentions":
                    "Mentions",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )


failed_results = results[
    results[
        "status"
    ]
    == "failed"
]

if not failed_results.empty:
    with st.expander(
        f"API failures ({len(failed_results)})"
    ):
        st.dataframe(
            failed_results[
                [
                    "provider",
                    "model",
                    "prompt_text",
                    "error_message",
                ]
            ].rename(
                columns={
                    "provider":
                        "Provider",
                    "model":
                        "Model",
                    "prompt_text":
                        "Prompt",
                    "error_message":
                        "Error",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )


st.write("### Inspect raw model response")

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

st.write(
    f"**Provider:** {selected_result['provider']}  \n"
    f"**Model:** {selected_result['model']}  \n"
    f"**Target detected:** "
    f"{'Yes' if bool(selected_result['target_mentioned']) else 'No'}"
)

if (
    selected_result[
        "status"
    ]
    == "completed"
):
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
        "The target name and competitor names are not "
        "included in the customer prompts. They are used "
        "only after each response to detect whether known "
        "businesses were mentioned."
    )

    st.write(
        "Position is currently the order in which known "
        "business names first appear in the response. "
        "Because providers are instructed to return a "
        "numbered recommendation list, this is a useful "
        "V1 proxy for recommendation rank."
    )

    st.write(
        "V1 does not attempt to identify unknown venues "
        "outside the stored target/competitor set. Raw "
        "responses are retained so this can be added later."
    )

    st.write(
        "Model/API results should not be presented as "
        "identical to the consumer ChatGPT, Claude or "
        "Gemini applications. Consumer products may use "
        "different models, search, location context and "
        "product-level orchestration."
    )
