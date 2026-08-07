from __future__ import annotations

import json
import uuid
from typing import Any

import pandas as pd
from sqlalchemy import text

from src.database import get_engine


def create_visibility_run(
    *,
    target_google_place_id: str,
    target_business_name: str,
    primary_group: str,
    location_context: str,
    providers: list[str],
    models: dict[str, str],
    prompt_count: int,
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
            status
        )
        values (
            :id,
            :target_google_place_id,
            :target_business_name,
            :primary_group,
            :location_context,
            'model_memory',
            cast(:providers as jsonb),
            cast(:models as jsonb),
            :prompt_count,
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
            },
        )

    return run_id


def create_visibility_queries(
    *,
    run_id: str,
    prompts: list[
        dict[str, Any]
    ],
) -> list[dict[str, Any]]:
    engine = get_engine()
    query = text(
        """
        insert into ai_visibility_queries (
            id,
            run_id,
            prompt_order,
            prompt_category,
            prompt_source,
            prompt_text
        )
        values (
            :id,
            :run_id,
            :prompt_order,
            :prompt_category,
            :prompt_source,
            :prompt_text
        )
        """
    )

    payloads = []

    for index, prompt in enumerate(
        prompts,
        start=1,
    ):
        query_id = str(
            uuid.uuid4()
        )

        payloads.append(
            {
                "id": query_id,
                "run_id": run_id,
                "prompt_order":
                    index,
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
            }
        )

    if payloads:
        with engine.begin() as connection:
            connection.execute(
                query,
                payloads,
            )

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
    latency_ms: int | None,
    status: str,
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
            target_position,
            mentioned_competitors,
            mentioned_known_businesses,
            input_tokens,
            output_tokens,
            total_tokens,
            latency_ms,
            status,
            error_message
        )
        values (
            :run_id,
            :query_id,
            :provider,
            :model,
            :raw_response,
            :target_mentioned,
            :target_position,
            cast(:mentioned_competitors as jsonb),
            cast(:mentioned_known_businesses as jsonb),
            :input_tokens,
            :output_tokens,
            :total_tokens,
            :latency_ms,
            :status,
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
            latency_ms =
                excluded.latency_ms,
            status =
                excluded.status,
            error_message =
                excluded.error_message,
            created_at = now()
        """
    )

    with engine.begin() as connection:
        connection.execute(
            query,
            {
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
                "latency_ms":
                    latency_ms,
                "status": status,
                "error_message":
                    error_message,
            },
        )


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


def get_run_queries(
    run_id: str,
) -> pd.DataFrame:
    engine = get_engine()

    query = text(
        """
        select
            id,
            prompt_order,
            prompt_category,
            prompt_source,
            prompt_text
        from ai_visibility_queries
        where run_id = :run_id
        order by prompt_order
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
            q.prompt_category,
            q.prompt_text,
            r.provider,
            r.model,
            r.raw_response,
            r.target_mentioned,
            r.target_position,
            r.mentioned_competitors,
            r.mentioned_known_businesses,
            r.input_tokens,
            r.output_tokens,
            r.total_tokens,
            r.latency_ms,
            r.status,
            r.error_message,
            r.created_at
        from ai_visibility_results r
        join ai_visibility_queries q
          on q.id = r.query_id
        where r.run_id = :run_id
        order by
            q.prompt_order,
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
