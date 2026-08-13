"""Transactional orchestration for deterministic NIST evidence runs."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from core.nist_evidence_catalog import (
    CATALOG_VERSION,
    FRAMEWORK_ID,
    FRAMEWORK_VERSION,
    V1_MAPPINGS,
)
from core.nist_evidence_collectors import CollectorContext, collect_all_categories
from core.nist_evidence_engine import (
    CONFIDENCE_UNKNOWN,
    PARTIAL_EVIDENCE,
    collection_confidence_for_sources,
    evaluate_requirement,
    validate_window,
)
from core.nist_evidence_store import (
    NistEvidenceValidationError,
    complete_run,
    create_run_record,
    get_boundary,
    insert_evidence_reference,
    insert_requirement_result,
    mark_run_error,
)
from core.source_health import aggregate_source_health


def _parse_datetime(value: Any, field: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise NistEvidenceValidationError(f"{field} must be an ISO-8601 timestamp") from error
    else:
        raise NistEvidenceValidationError(f"{field} must be an ISO-8601 timestamp")
    if parsed.tzinfo is None:
        raise NistEvidenceValidationError(f"{field} must include a timezone offset")
    return parsed.astimezone(timezone.utc)


def resolve_run_window(boundary: dict[str, Any], payload: dict[str, Any], *, now: datetime) -> tuple[datetime, datetime]:
    raw_start = payload.get("window_start")
    raw_end = payload.get("window_end")
    if (raw_start is None) != (raw_end is None):
        raise NistEvidenceValidationError("window_start and window_end must be provided together")
    if raw_start is None:
        end = now.astimezone(timezone.utc)
        start = end - timedelta(hours=int(boundary["default_window_hours"]))
    else:
        start = _parse_datetime(raw_start, "window_start")
        end = _parse_datetime(raw_end, "window_end")
    try:
        return validate_window(start, end)
    except ValueError as error:
        raise NistEvidenceValidationError(str(error)) from error


def _mapping_sources(mapping, boundary_sources: tuple[str, ...]) -> tuple[str, ...]:
    if not mapping.source_requirements:
        return boundary_sources
    return tuple(sorted(set(mapping.source_requirements) & set(boundary_sources)))


def execute_assessment_run(
    conn,
    *,
    boundary_id: int,
    payload: dict[str, Any],
    actor_username: str,
    now: datetime | None = None,
) -> int:
    observed_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    boundary = get_boundary(conn, boundary_id)
    if not boundary:
        raise NistEvidenceValidationError("assessment boundary not found")
    if not boundary["is_active"]:
        raise NistEvidenceValidationError("assessment boundary is inactive")
    window_start, window_end = resolve_run_window(boundary, payload, now=observed_at)
    health_snapshot = aggregate_source_health(conn, generated_at=observed_at)
    run_id = create_run_record(
        conn,
        boundary_id=boundary_id,
        framework_id=FRAMEWORK_ID,
        framework_version=FRAMEWORK_VERSION,
        window_start=window_start,
        window_end=window_end,
        source_health_snapshot=health_snapshot,
        actor_username=actor_username,
    )
    conn.commit()

    try:
        with conn.cursor() as cur:
            bundles = collect_all_categories(
                cur,
                CollectorContext(
                    source_ids=tuple(boundary["selected_sources"]),
                    environments=tuple(boundary["environments"]),
                    window_start=window_start,
                    window_end=window_end,
                    collected_at=observed_at,
                    source_health_snapshot=health_snapshot,
                ),
            )

        statuses: Counter[str] = Counter()
        confidences: Counter[str] = Counter()
        partial_run = False
        for mapping in V1_MAPPINGS:
            relevant_sources = _mapping_sources(mapping, tuple(boundary["selected_sources"]))
            confidence = (
                collection_confidence_for_sources(
                    health_snapshot, relevant_sources, observed_at=observed_at
                )
                if relevant_sources else CONFIDENCE_UNKNOWN
            )
            evaluation = evaluate_requirement(
                mapping,
                (bundles[category] for category in mapping.evidence_categories),
                collection_confidence=confidence,
                window_start=window_start,
                window_end=window_end,
            )
            result_id = insert_requirement_result(
                conn, run_id=run_id, mapping=mapping, evaluation=evaluation,
                evaluated_at=observed_at,
            )
            for category in mapping.evidence_categories:
                bundle = bundles[category]
                for reference in bundle.references:
                    insert_evidence_reference(
                        conn, run_id=run_id, requirement_result_id=result_id,
                        requirement_id=mapping.requirement_id, reference=reference,
                        omitted_count=bundle.omitted_count,
                    )
            statuses[evaluation.evidence_status] += 1
            confidences[evaluation.collection_confidence] += 1
            partial_run = partial_run or evaluation.evidence_status == PARTIAL_EVIDENCE

        complete_run(
            conn,
            run_id,
            summary_counts={
                "requirement_count": len(V1_MAPPINGS),
                "by_evidence_status": dict(sorted(statuses.items())),
                "by_collection_confidence": dict(sorted(confidences.items())),
                "catalog_version": CATALOG_VERSION,
            },
            partial=partial_run,
        )
        conn.commit()
        return run_id
    except Exception:
        conn.rollback()
        mark_run_error(conn, run_id)
        conn.commit()
        raise
