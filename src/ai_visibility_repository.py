from __future__ import annotations

import json
import uuid
from typing import Any

import pandas as pd
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from src.database import get_engine

GSO_REPORT_METADATA_VERSION = 1


def _missing_column(exc: DBAPIError, column: str) -> bool:
    original = getattr(exc, "orig", None)
    sqlstate = getattr(original, "sqlstate", None) or getattr(original, "pgcode", None)
    return sqlstate == "42703" and column in str(exc)


def _report_rating(value: Any) -> int | None:
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if 1 <= result <= 5 else None


def create_visibility_run(
    *,
    target_google_place_id: str,
    target_business_name: str,
    primary_group: str,
    location_context: str,
    providers: list[str],
    models: dict[str, str],
    prompt_count: int,
    repeat_count: int = 1,
    benchmark_mode: str = "search_grounded",
) -> str:
    run_id = str(uuid.uuid4())
    engine = get_engine()

    query = text(
        """
        insert into ai_visibility_runs (
            id,
            target_google_place_id,
            target_business_name,
            primary_group,
            location_context,
            benchmark_mode,
            providers,
            models,
            prompt_count,
            repeat_count,
            status
        )
        values (
            :id,
            :target_google_place_id,
            :target_business_name,
            :primary_group,
            :location_context,
            :benchmark_mode,
            cast(:providers as jsonb),
            cast(:models as jsonb),
            :prompt_count,
            :repeat_count,
            'running'
        )
        """
    )

    with engine.begin() as connection:
        connection.execute(
            query,
            {
                "id": run_id,
                "target_google_place_id":
                    target_google_place_id,
                "target_business_name":
                    target_business_name,
                "benchmark_mode": benchmark_mode,
                "primary_group":
                    primary_group,
                "location_context":
                    location_context,
                "providers": json.dumps(
                    providers
                ),
                "models": json.dumps(
                    models
                ),
                "prompt_count":
                    int(prompt_count),
                "repeat_count":
                    int(
                        max(
                            1,
                            repeat_count,
                        )
                    ),
            },
        )

    return run_id


def create_visibility_queries(
    *,
    run_id: str,
    prompts: list[
        dict[str, Any]
    ],
    repetitions: int = 1,
) -> list[dict[str, Any]]:
    engine = get_engine()

    query = text(
        """
        insert into ai_visibility_queries (
            id,
            run_id,
            prompt_order,
            base_prompt_order,
            repeat_index,
            prompt_category,
            prompt_source,
            prompt_text,
            report_intent,
            report_importance,
            report_effort
        )
        values (
            :id,
            :run_id,
            :prompt_order,
            :base_prompt_order,
            :repeat_index,
            :prompt_category,
            :prompt_source,
            :prompt_text,
            :report_intent,
            :report_importance,
            :report_effort
        )
        """
    )

    payloads = []
    physical_order = 0
    repetitions = max(
        1,
        int(repetitions),
    )

    for base_order, prompt in enumerate(
        prompts,
        start=1,
    ):
        for repeat_index in range(
            1,
            repetitions + 1,
        ):
            physical_order += 1

            query_id = str(
                uuid.uuid4()
            )

            payloads.append(
                {
                    "id": query_id,
                    "run_id": run_id,
                    "prompt_order":
                        physical_order,
                    "base_prompt_order":
                        base_order,
                    "repeat_index":
                        repeat_index,
                    "prompt_category":
                        prompt.get(
                            "category"
                        ),
                    "prompt_source":
                        prompt.get(
                            "source",
                            "generated",
                        ),
                    "prompt_text":
                        prompt.get(
                            "prompt"
                        ),
                    "report_intent": (
                        str(prompt.get("report_intent") or "discovery").strip().lower()
                        if str(prompt.get("report_intent") or "discovery").strip().lower()
                        in {"discovery", "comparison", "transactional", "branded"}
                        else "discovery"
                    ),
                    "report_importance": _report_rating(prompt.get("report_importance")),
                    "report_effort": _report_rating(prompt.get("report_effort")),
                }
            )

    if payloads:
        try:
            with engine.begin() as connection:
                connection.execute(query, payloads)
        except DBAPIError as exc:
            if not (_missing_column(exc, "report_intent") or _missing_column(exc, "report_importance") or _missing_column(exc, "report_effort")):
                raise
            legacy_query = text(
                """
                insert into ai_visibility_queries (
                    id, run_id, prompt_order, base_prompt_order, repeat_index,
                    prompt_category, prompt_source, prompt_text
                ) values (
                    :id, :run_id, :prompt_order, :base_prompt_order, :repeat_index,
                    :prompt_category, :prompt_source, :prompt_text
                )
                """
            )
            with engine.begin() as connection:
                connection.execute(legacy_query, payloads)

    return payloads


def save_visibility_result(
    *,
    run_id: str,
    query_id: str,
    provider: str,
    model: str,
    raw_response: str | None,
    analysis: dict[str, Any],
    input_tokens: int | None,
    output_tokens: int | None,
    total_tokens: int | None,
    reasoning_tokens: int | None,
    latency_ms: int | None,
    finish_reason: str | None,
    response_complete: bool,
    status: str,
    report_metadata: dict[str, Any] | None = None,
    error_message: str | None = None,
) -> None:
    engine = get_engine()

    query = text(
        """
        insert into ai_visibility_results (
            run_id,
            query_id,
            provider,
            model,
            raw_response,
            target_mentioned,
            target_recommended,
            target_position,
            mentioned_competitors,
            mentioned_known_businesses,
            input_tokens,
            output_tokens,
            total_tokens,
            reasoning_tokens,
            latency_ms,
            finish_reason,
            response_complete,
            status,
            report_metadata,
            error_message
        )
        values (
            :run_id,
            :query_id,
            :provider,
            :model,
            :raw_response,
            :target_mentioned,
            :target_recommended,
            :target_position,
            cast(:mentioned_competitors as jsonb),
            cast(:mentioned_known_businesses as jsonb),
            :input_tokens,
            :output_tokens,
            :total_tokens,
            :reasoning_tokens,
            :latency_ms,
            :finish_reason,
            :response_complete,
            :status,
            cast(:report_metadata as jsonb),
            :error_message
        )
        on conflict (
            run_id,
            query_id,
            provider
        )
        do update set
            model = excluded.model,
            raw_response =
                excluded.raw_response,
            target_mentioned =
                excluded.target_mentioned,
            target_recommended =
                excluded.target_recommended,
            target_position =
                excluded.target_position,
            mentioned_competitors =
                excluded.mentioned_competitors,
            mentioned_known_businesses =
                excluded.mentioned_known_businesses,
            input_tokens =
                excluded.input_tokens,
            output_tokens =
                excluded.output_tokens,
            total_tokens =
                excluded.total_tokens,
            reasoning_tokens =
                excluded.reasoning_tokens,
            latency_ms =
                excluded.latency_ms,
            finish_reason =
                excluded.finish_reason,
            response_complete =
                excluded.response_complete,
            status =
                excluded.status,
            report_metadata =
                excluded.report_metadata,
            error_message =
                excluded.error_message,
            created_at = now()
        """
    )

    parameters = {
                "run_id": run_id,
                "query_id": query_id,
                "provider": provider,
                "model": model,
                "raw_response":
                    raw_response,
                "target_mentioned":
                    bool(
                        analysis.get(
                            "target_mentioned",
                            False,
                        )
                    ),
                "target_recommended":
                    bool(
                        analysis.get(
                            "target_recommended",
                            False,
                        )
                    ),
                "target_position":
                    analysis.get(
                        "target_position"
                    ),
                "mentioned_competitors":
                    json.dumps(
                        analysis.get(
                            "mentioned_competitors",
                            [],
                        )
                    ),
                "mentioned_known_businesses":
                    json.dumps(
                        analysis.get(
                            "mentioned_known_businesses",
                            [],
                        )
                    ),
                "input_tokens":
                    input_tokens,
                "output_tokens":
                    output_tokens,
                "total_tokens":
                    total_tokens,
                "reasoning_tokens":
                    reasoning_tokens,
                "latency_ms":
                    latency_ms,
                "finish_reason":
                    finish_reason,
                "response_complete":
                    bool(
                        response_complete
                    ),
                "status": status,
                "report_metadata": json.dumps(report_metadata or {
                    "capture_version": "gso-provider-metadata-v1",
                    "citation_status": "unavailable",
                    "citations": [],
                    "refused": False,
                }),
                "error_message":
                    error_message,
            }
    try:
        with engine.begin() as connection:
            connection.execute(query, parameters)
    except DBAPIError as exc:
        if not _missing_column(exc, "report_metadata"):
            raise
        legacy_query = text(
            """
            insert into ai_visibility_results (
                run_id, query_id, provider, model, raw_response, target_mentioned,
                target_recommended, target_position, mentioned_competitors,
                mentioned_known_businesses, input_tokens, output_tokens, total_tokens,
                reasoning_tokens, latency_ms, finish_reason, response_complete,
                status, error_message
            ) values (
                :run_id, :query_id, :provider, :model, :raw_response, :target_mentioned,
                :target_recommended, :target_position, cast(:mentioned_competitors as jsonb),
                cast(:mentioned_known_businesses as jsonb), :input_tokens, :output_tokens,
                :total_tokens, :reasoning_tokens, :latency_ms, :finish_reason,
                :response_complete, :status, :error_message
            )
            on conflict (run_id, query_id, provider) do update set
                model = excluded.model, raw_response = excluded.raw_response,
                target_mentioned = excluded.target_mentioned,
                target_recommended = excluded.target_recommended,
                target_position = excluded.target_position,
                mentioned_competitors = excluded.mentioned_competitors,
                mentioned_known_businesses = excluded.mentioned_known_businesses,
                input_tokens = excluded.input_tokens, output_tokens = excluded.output_tokens,
                total_tokens = excluded.total_tokens, reasoning_tokens = excluded.reasoning_tokens,
                latency_ms = excluded.latency_ms, finish_reason = excluded.finish_reason,
                response_complete = excluded.response_complete, status = excluded.status,
                error_message = excluded.error_message, created_at = now()
            """
        )
        legacy_parameters = {key: value for key, value in parameters.items() if key != "report_metadata"}
        with engine.begin() as connection:
            connection.execute(legacy_query, legacy_parameters)


def finish_visibility_run(
    *,
    run_id: str,
    status: str,
    error_message: str | None = None,
) -> None:
    engine = get_engine()

    query = text(
        """
        update ai_visibility_runs
        set
            status = :status,
            error_message =
                :error_message,
            completed_at = now()
        where id = :run_id
        """
    )

    with engine.begin() as connection:
        connection.execute(
            query,
            {
                "run_id": run_id,
                "status": status,
                "error_message":
                    error_message,
            },
        )


def get_latest_run(
    target_google_place_id: str,
) -> dict[str, Any]:
    engine = get_engine()

    query = text(
        """
        select *
        from ai_visibility_runs
        where
            target_google_place_id =
                :target_google_place_id
        order by started_at desc
        limit 1
        """
    )

    with engine.connect() as connection:
        row = connection.execute(
            query,
            {
                "target_google_place_id":
                    target_google_place_id,
            },
        ).mappings().first()

    return dict(row) if row else {}


def get_visibility_run(run_id: str) -> dict[str, Any]:
    """Load the exact benchmark attached to a report, not merely the latest one."""

    engine = get_engine()
    query = text("select * from ai_visibility_runs where id = :run_id")
    with engine.connect() as connection:
        row = connection.execute(query, {"run_id": run_id}).mappings().first()
    return dict(row) if row else {}


def get_run_queries(
    run_id: str,
) -> pd.DataFrame:
    engine = get_engine()

    query = text(
        """
        select
            q.id,
            q.prompt_order,
            q.base_prompt_order,
            q.repeat_index,
            q.prompt_category,
            q.prompt_source,
            q.prompt_text,
            coalesce(to_jsonb(q)->>'report_intent', 'discovery') as report_intent,
            to_jsonb(q)->>'report_importance' as report_importance,
            to_jsonb(q)->>'report_effort' as report_effort
        from ai_visibility_queries q
        where q.run_id = :run_id
        order by
            q.base_prompt_order,
            q.repeat_index,
            q.prompt_order
        """
    )

    with engine.connect() as connection:
        rows = connection.execute(
            query,
            {
                "run_id": run_id,
            },
        ).mappings().all()

    return pd.DataFrame(rows)


def get_run_results(
    run_id: str,
) -> pd.DataFrame:
    engine = get_engine()

    query = text(
        """
        select
            r.id,
            r.query_id,
            q.prompt_order,
            q.base_prompt_order,
            q.repeat_index,
            q.prompt_category,
            q.prompt_source,
            q.prompt_text,
            r.provider,
            r.model,
            r.raw_response,
            r.target_mentioned,
            r.target_recommended,
            r.target_position,
            r.mentioned_competitors,
            r.mentioned_known_businesses,
            coalesce(to_jsonb(r)->'report_metadata', '{}'::jsonb) as report_metadata,
            coalesce(to_jsonb(q)->>'report_intent', 'discovery') as report_intent,
            to_jsonb(q)->>'report_importance' as report_importance,
            to_jsonb(q)->>'report_effort' as report_effort,
            r.input_tokens,
            r.output_tokens,
            r.total_tokens,
            r.reasoning_tokens,
            r.latency_ms,
            r.finish_reason,
            r.response_complete,
            r.status,
            r.error_message,
            r.created_at
        from ai_visibility_results r
        join ai_visibility_queries q
          on q.id = r.query_id
        where r.run_id = :run_id
        order by
            q.base_prompt_order,
            q.repeat_index,
            r.provider
        """
    )

    with engine.connect() as connection:
        rows = connection.execute(
            query,
            {
                "run_id": run_id,
            },
        ).mappings().all()

    frame = pd.DataFrame(rows)

    if frame.empty:
        return frame

    for column in [
        "mentioned_competitors",
        "mentioned_known_businesses",
    ]:
        frame[column] = frame[
            column
        ].apply(
            lambda value: (
                value
                if isinstance(
                    value,
                    list,
                )
                else []
            )
        )

    return frame
