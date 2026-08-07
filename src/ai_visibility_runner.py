from __future__ import annotations

from concurrent.futures import (
    ThreadPoolExecutor,
    as_completed,
)
from typing import Any, Callable

import pandas as pd

from src.ai_visibility_analysis import (
    analyse_visibility_response,
)
from src.ai_visibility_repository import (
    finish_visibility_run,
    get_run_results,
    save_visibility_result,
)
from src.llm_providers.anthropic_provider import (
    call_anthropic,
)
from src.llm_providers.gemini_provider import (
    call_gemini,
)
from src.llm_providers.openai_provider import (
    call_openai,
)


def _call_provider(
    *,
    provider: str,
    api_key: str,
    model: str,
    prompt: str,
):
    if provider == "OpenAI":
        return call_openai(
            api_key=api_key,
            model=model,
            prompt=prompt,
        )

    if provider == "Claude":
        return call_anthropic(
            api_key=api_key,
            model=model,
            prompt=prompt,
        )

    if provider == "Gemini":
        return call_gemini(
            api_key=api_key,
            model=model,
            prompt=prompt,
        )

    raise ValueError(
        f"Unsupported provider: {provider}"
    )


def build_retry_plan(
    *,
    queries: pd.DataFrame,
    results: pd.DataFrame,
    providers: list[str],
) -> list[dict[str, Any]]:
    result_lookup = {}

    if not results.empty:
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

    plan = []

    for query in queries.to_dict(
        "records"
    ):
        query_id = str(
            query["id"]
        )

        for provider in providers:
            existing = result_lookup.get(
                (
                    query_id,
                    provider,
                )
            )

            response_complete = (
                False
                if existing is None
                else existing.get(
                    "response_complete"
                )
            )

            try:
                complete_flag = (
                    bool(
                        response_complete
                    )
                    if pd.notna(
                        response_complete
                    )
                    else False
                )
            except (
                TypeError,
                ValueError,
            ):
                complete_flag = False

            needs_retry = (
                existing is None
                or existing.get(
                    "status"
                )
                != "completed"
                or not complete_flag
            )

            if needs_retry:
                plan.append(
                    {
                        **query,
                        "provider":
                            provider,
                    }
                )

    return plan


def _save_provider_outcome(
    *,
    run_id: str,
    query_id: str,
    provider: str,
    model: str,
    prompt_text: str,
    provider_response: Any | None,
    error: Exception | None,
    target_google_place_id: str,
    target_business_name: str,
    known_businesses: list[
        dict[str, str]
    ],
) -> None:
    if error is not None:
        save_visibility_result(
            run_id=run_id,
            query_id=query_id,
            provider=provider,
            model=model,
            raw_response=None,
            analysis={
                "target_mentioned":
                    False,
                "target_recommended":
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
            reasoning_tokens=None,
            latency_ms=None,
            finish_reason=(
                "request_failed"
            ),
            response_complete=False,
            status="failed",
            error_message=str(
                error
            )[:2000],
        )
        return

    analysis = (
        analyse_visibility_response(
            response_text=(
                provider_response.text
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
        )
    )

    save_visibility_result(
        run_id=run_id,
        query_id=query_id,
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
        reasoning_tokens=(
            provider_response.reasoning_tokens
        ),
        latency_ms=(
            provider_response.latency_ms
        ),
        finish_reason=(
            provider_response.finish_reason
        ),
        response_complete=(
            provider_response.response_complete
        ),
        status="completed",
    )


def execute_calls(
    *,
    run_id: str,
    call_plan: list[
        dict[str, Any]
    ],
    models: dict[str, str],
    api_keys: dict[str, str],
    target_google_place_id: str,
    target_business_name: str,
    known_businesses: list[
        dict[str, str]
    ],
    progress_callback: Callable[
        [int, int],
        None,
    ] | None = None,
    status_callback: Callable[
        [str],
        None,
    ] | None = None,
) -> None:
    if not call_plan:
        return

    # Group by prompt. Providers for one prompt run in parallel, which
    # materially reduces the chance of a long Streamlit session being
    # interrupted without creating a burst across all prompts.
    prompt_groups = {}

    for item in call_plan:
        query_id = str(
            item["id"]
        )

        prompt_groups.setdefault(
            query_id,
            [],
        ).append(item)

    total = len(call_plan)
    processed = 0

    for query_id, items in (
        prompt_groups.items()
    ):
        prompt_text = str(
            items[0][
                "prompt_text"
            ]
        )

        if status_callback:
            status_callback(
                prompt_text
            )

        futures = {}

        with ThreadPoolExecutor(
            max_workers=max(
                1,
                len(items),
            )
        ) as executor:
            for item in items:
                provider = str(
                    item["provider"]
                )
                model = str(
                    models[
                        provider
                    ]
                )
                api_key = str(
                    api_keys[
                        provider
                    ]
                )

                future = executor.submit(
                    _call_provider,
                    provider=provider,
                    api_key=api_key,
                    model=model,
                    prompt=prompt_text,
                )

                futures[
                    future
                ] = {
                    "provider":
                        provider,
                    "model":
                        model,
                }

            for future in as_completed(
                futures
            ):
                meta = futures[
                    future
                ]

                provider_response = None
                error = None

                try:
                    provider_response = (
                        future.result()
                    )
                except Exception as exc:
                    error = exc

                _save_provider_outcome(
                    run_id=run_id,
                    query_id=query_id,
                    provider=meta[
                        "provider"
                    ],
                    model=meta[
                        "model"
                    ],
                    prompt_text=(
                        prompt_text
                    ),
                    provider_response=(
                        provider_response
                    ),
                    error=error,
                    target_google_place_id=(
                        target_google_place_id
                    ),
                    target_business_name=(
                        target_business_name
                    ),
                    known_businesses=(
                        known_businesses
                    ),
                )

                processed += 1

                if progress_callback:
                    progress_callback(
                        processed,
                        total,
                    )


def finalise_run_from_results(
    *,
    run_id: str,
    expected_call_count: int,
) -> str:
    results = get_run_results(
        run_id
    )

    if results.empty:
        status = "failed"
        message = (
            "No provider results were saved."
        )
    else:
        valid = results[
            (
                results[
                    "status"
                ]
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

        valid_count = len(valid)

        if (
            valid_count
            == expected_call_count
        ):
            status = "completed"
            message = None
        elif valid_count > 0:
            status = "partial"
            message = (
                f"{expected_call_count - valid_count} "
                "call(s) are missing, failed or incomplete."
            )
        else:
            status = "failed"
            message = (
                "No valid complete provider responses."
            )

    finish_visibility_run(
        run_id=run_id,
        status=status,
        error_message=message,
    )

    return status
