"""PostgreSQL persistence helpers for deterministic NIST evidence assessments."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from psycopg2.extras import Json

from core.nist_evidence_catalog import CATALOG_HASH, CATALOG_VERSION, COLLECTOR_VERSION
from core.nist_evidence_engine import normalize_boundary_sources
from core.source_inventory import source_definition


BOUNDARY_SCOPE_DECLARATION = (
    "Assessment scope is declared by an authorized user and is not an "
    "automatically discovered CUI boundary."
)

_BOUNDARY_COLUMNS = (
    "id, name, description, selected_sources, selected_source_types, environments, "
    "default_window_hours, is_active, scope_declaration, created_by, updated_by, "
    "created_at, updated_at"
)

_RUN_COLUMNS = (
    "r.id, r.boundary_id, r.framework_id, r.framework_version, r.catalog_version, "
    "r.catalog_hash, r.collector_version, r.requested_window_start, "
    "r.requested_window_end, r.status, r.source_health_snapshot, r.actor_username, "
    "r.summary_counts, r.started_at, r.completed_at, r.created_at"
)


class NistEvidenceValidationError(ValueError):
    pass


def _text(value: Any, field: str, *, required: bool = False, max_length: int = 1000) -> str:
    normalized = str(value or "").strip()
    if required and not normalized:
        raise NistEvidenceValidationError(f"{field} is required")
    if len(normalized) > max_length:
        raise NistEvidenceValidationError(f"{field} must be at most {max_length} characters")
    return normalized


def _string_list(value: Any, field: str, *, max_items: int = 32) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise NistEvidenceValidationError(f"{field} must be an array")
    if len(value) > max_items:
        raise NistEvidenceValidationError(f"{field} must contain at most {max_items} items")
    items = tuple(sorted({_text(item, field, required=True, max_length=64) for item in value}))
    return items


def validate_boundary_payload(payload: dict[str, Any], *, partial: bool = False) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise NistEvidenceValidationError("request body must be an object")
    result: dict[str, Any] = {}
    if not partial or "name" in payload:
        result["name"] = _text(payload.get("name"), "name", required=True, max_length=120)
    if not partial or "description" in payload:
        result["description"] = _text(payload.get("description"), "description", max_length=1000)
    if not partial or "selected_sources" in payload:
        raw_sources = _string_list(payload.get("selected_sources"), "selected_sources")
        try:
            sources = normalize_boundary_sources(raw_sources)
        except ValueError as error:
            raise NistEvidenceValidationError(str(error)) from error
        result["selected_sources"] = sources
        result["selected_source_types"] = tuple(
            sorted({source_definition(source).source_type for source in sources})
        )
    if not partial or "environments" in payload:
        result["environments"] = _string_list(payload.get("environments"), "environments")
    if not partial or "default_window_hours" in payload:
        try:
            hours = int(payload.get("default_window_hours", 24))
        except (TypeError, ValueError) as error:
            raise NistEvidenceValidationError("default_window_hours must be an integer") from error
        if not 1 <= hours <= 168:
            raise NistEvidenceValidationError("default_window_hours must be between 1 and 168")
        result["default_window_hours"] = hours
    if not partial or "is_active" in payload:
        active = payload.get("is_active", True)
        if not isinstance(active, bool):
            raise NistEvidenceValidationError("is_active must be a boolean")
        result["is_active"] = active
    return result


def _boundary_row(row: tuple | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "id": row[0], "name": row[1], "description": row[2],
        "selected_sources": list(row[3]), "selected_source_types": list(row[4]),
        "environments": list(row[5]), "default_window_hours": row[6],
        "is_active": row[7], "scope_declaration": row[8], "created_by": row[9],
        "updated_by": row[10], "created_at": row[11].isoformat(),
        "updated_at": row[12].isoformat(),
    }


def create_boundary(conn, payload: dict[str, Any], *, actor_username: str) -> dict[str, Any]:
    values = validate_boundary_payload(payload)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            INSERT INTO nist_assessment_boundaries (
                name, description, selected_sources, selected_source_types, environments,
                default_window_hours, is_active, scope_declaration, created_by, updated_by
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING {_BOUNDARY_COLUMNS}
            """,
            (
                values["name"], values["description"], list(values["selected_sources"]),
                list(values["selected_source_types"]), list(values["environments"]),
                values["default_window_hours"], values["is_active"],
                BOUNDARY_SCOPE_DECLARATION, actor_username, actor_username,
            ),
        )
        return _boundary_row(cur.fetchone())


def update_boundary(
    conn, boundary_id: int, payload: dict[str, Any], *, actor_username: str
) -> dict[str, Any] | None:
    values = validate_boundary_payload(payload, partial=True)
    if not values:
        raise NistEvidenceValidationError("at least one boundary field is required")
    assignments = []
    params: list[Any] = []
    for field in (
        "name", "description", "selected_sources", "selected_source_types",
        "environments", "default_window_hours", "is_active",
    ):
        if field in values:
            assignments.append(f"{field} = %s")
            value = values[field]
            params.append(list(value) if isinstance(value, tuple) else value)
    assignments.extend(["updated_by = %s", "updated_at = NOW()"])
    params.extend([actor_username, boundary_id])
    with conn.cursor() as cur:
        cur.execute(
            f"""
            UPDATE nist_assessment_boundaries
            SET {', '.join(assignments)}
            WHERE id = %s
            RETURNING {_BOUNDARY_COLUMNS}
            """,
            tuple(params),
        )
        return _boundary_row(cur.fetchone())


def get_boundary(conn, boundary_id: int) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT {_BOUNDARY_COLUMNS} FROM nist_assessment_boundaries WHERE id = %s",
            (boundary_id,),
        )
        return _boundary_row(cur.fetchone())


def list_boundaries(conn, *, include_inactive: bool = False, limit: int = 100) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 100))
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT {_BOUNDARY_COLUMNS}
            FROM nist_assessment_boundaries
            WHERE (%s OR is_active = TRUE)
            ORDER BY updated_at DESC, id DESC
            LIMIT %s
            """,
            (include_inactive, safe_limit),
        )
        return [_boundary_row(row) for row in cur.fetchall()]


def create_run_record(
    conn,
    *,
    boundary_id: int,
    framework_id: str,
    framework_version: str,
    window_start: datetime,
    window_end: datetime,
    source_health_snapshot: dict[str, Any],
    actor_username: str,
) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO nist_assessment_runs (
                boundary_id, framework_id, framework_version, catalog_version,
                catalog_hash, collector_version, requested_window_start,
                requested_window_end, source_health_snapshot, actor_username
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                boundary_id, framework_id, framework_version, CATALOG_VERSION,
                CATALOG_HASH, COLLECTOR_VERSION, window_start, window_end,
                Json(source_health_snapshot), actor_username,
            ),
        )
        return int(cur.fetchone()[0])


def insert_requirement_result(
    conn,
    *,
    run_id: int,
    mapping,
    evaluation,
    evaluated_at: datetime,
) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO nist_requirement_results (
                run_id, requirement_id, requirement_name, mapping_strength,
                evidence_status, collection_confidence, reason_code, limitation,
                evidence_count, omitted_count, evaluated_at, catalog_version,
                catalog_hash, collector_version
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                run_id, mapping.requirement_id, mapping.requirement_name,
                mapping.mapping_strength, evaluation.evidence_status,
                evaluation.collection_confidence, evaluation.reason_code,
                evaluation.limitation, evaluation.evidence_count,
                evaluation.omitted_count, evaluated_at, CATALOG_VERSION,
                CATALOG_HASH, COLLECTOR_VERSION,
            ),
        )
        return int(cur.fetchone()[0])


def insert_evidence_reference(
    conn,
    *,
    run_id: int,
    requirement_result_id: int,
    requirement_id: str,
    reference,
    omitted_count: int,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO nist_evidence_references (
                run_id, requirement_result_id, requirement_id, evidence_category,
                evidence_type, canonical_source, source_type, source_health_state,
                entity_type, entity_id, occurrence_timestamp, ingestion_timestamp,
                collection_timestamp, query_window_start, query_window_end, query_hash,
                operational_classification, has_omitted_records, omitted_count,
                catalog_version, mapping_version, collector_version, evidence_summary,
                reference_metadata
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                run_id, requirement_result_id, requirement_id,
                reference.evidence_category, reference.evidence_type,
                reference.canonical_source, reference.source_type,
                reference.source_health_state, reference.entity_type,
                reference.entity_id, reference.occurrence_timestamp,
                reference.ingestion_timestamp, reference.collection_timestamp,
                reference.window_start, reference.window_end, reference.query_hash,
                reference.operational_classification, omitted_count > 0,
                omitted_count, CATALOG_VERSION, CATALOG_VERSION, COLLECTOR_VERSION,
                reference.summary, Json(reference.metadata),
            ),
        )


def complete_run(conn, run_id: int, *, summary_counts: dict[str, Any], partial: bool = False) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE nist_assessment_runs
            SET status = %s, summary_counts = %s, completed_at = NOW()
            WHERE id = %s
            """,
            ("completed_with_partial_evidence" if partial else "completed", Json(summary_counts), run_id),
        )


def mark_run_error(conn, run_id: int) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE nist_assessment_runs
            SET status = 'error', completed_at = NOW()
            WHERE id = %s
            """,
            (run_id,),
        )


def _run_row(row: tuple | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "id": row[0], "boundary_id": row[1], "framework_id": row[2],
        "framework_version": row[3], "catalog_version": row[4],
        "catalog_hash": row[5].strip(), "collector_version": row[6],
        "requested_window_start": row[7].isoformat(),
        "requested_window_end": row[8].isoformat(), "status": row[9],
        "source_health_snapshot": row[10], "actor_username": row[11],
        "summary_counts": row[12], "started_at": row[13].isoformat(),
        "completed_at": row[14].isoformat() if row[14] else None,
        "created_at": row[15].isoformat(),
    }


def get_run(conn, run_id: int) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(f"SELECT {_RUN_COLUMNS} FROM nist_assessment_runs r WHERE r.id = %s", (run_id,))
        return _run_row(cur.fetchone())


def list_requirement_results(conn, run_id: int) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, run_id, requirement_id, requirement_name, mapping_strength,
                   evidence_status, collection_confidence, reason_code, limitation,
                   evidence_count, omitted_count, evaluated_at, catalog_version,
                   catalog_hash, collector_version
            FROM nist_requirement_results
            WHERE run_id = %s
            ORDER BY requirement_id
            """,
            (run_id,),
        )
        return [
            {
                "id": row[0], "run_id": row[1], "requirement_id": row[2],
                "requirement_name": row[3], "mapping_strength": row[4],
                "evidence_status": row[5], "collection_confidence": row[6],
                "reason_code": row[7], "limitation": row[8],
                "evidence_count": row[9], "omitted_count": row[10],
                "evaluated_at": row[11].isoformat(), "catalog_version": row[12],
                "catalog_hash": row[13].strip(), "collector_version": row[14],
            }
            for row in cur.fetchall()
        ]


def list_evidence_references(
    conn, run_id: int, requirement_id: str, *, limit: int = 100, offset: int = 0
) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit), 100))
    safe_offset = max(0, int(offset))
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, requirement_id, evidence_category, evidence_type,
                   canonical_source, source_type, source_health_state, entity_type,
                   entity_id, occurrence_timestamp, ingestion_timestamp,
                   collection_timestamp, query_window_start, query_window_end,
                   query_hash, operational_classification, has_omitted_records,
                   omitted_count, catalog_version, mapping_version, collector_version,
                   evidence_summary, reference_metadata, COUNT(*) OVER()
            FROM nist_evidence_references
            WHERE run_id = %s AND requirement_id = %s
            ORDER BY evidence_category, occurrence_timestamp DESC NULLS LAST,
                     ingestion_timestamp DESC NULLS LAST, id
            LIMIT %s OFFSET %s
            """,
            (run_id, requirement_id, safe_limit, safe_offset),
        )
        rows = cur.fetchall()
    items = [
        {
            "id": row[0], "requirement_id": row[1], "evidence_category": row[2],
            "evidence_type": row[3], "canonical_source": row[4],
            "source_type": row[5], "source_health_state": row[6],
            "entity_type": row[7], "entity_id": row[8],
            "occurrence_timestamp": row[9].isoformat() if row[9] else None,
            "ingestion_timestamp": row[10].isoformat() if row[10] else None,
            "collection_timestamp": row[11].isoformat(),
            "query_window_start": row[12].isoformat(),
            "query_window_end": row[13].isoformat(), "query_hash": row[14].strip(),
            "operational_classification": row[15], "is_truncated": row[16],
            "omitted_count": row[17], "catalog_version": row[18],
            "mapping_version": row[19], "collector_version": row[20],
            "evidence_summary": row[21], "reference_metadata": row[22],
        }
        for row in rows
    ]
    return {"items": items, "total": int(rows[0][23]) if rows else 0, "limit": safe_limit, "offset": safe_offset}
