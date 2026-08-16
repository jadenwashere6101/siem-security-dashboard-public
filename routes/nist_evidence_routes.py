"""Deterministic NIST SP 800-171 Rev. 3 evidence-support API."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from io import StringIO
import json

from flask import Blueprint, Response, current_app, jsonify, request
from flask_login import current_user, login_required
from psycopg2 import IntegrityError

from core.audit_helpers import log_audit_event
from core.auth import analyst_or_super_admin_required, super_admin_required
from core.db import get_db_connection
from core.nist_evidence_catalog import catalog_document
from core.nist_evidence_service import execute_assessment_run
from core.nist_evidence_explanation import (
    NistExplanationBindingError,
    NistExplanationValidationError,
    enqueue_explanation,
)
from core.nist_evidence_store import (
    NistEvidenceValidationError,
    create_boundary,
    get_boundary,
    get_requirement_result,
    get_run,
    list_boundaries,
    list_boundary_runs,
    list_evidence_references,
    list_requirement_results,
    update_boundary,
)


nist_evidence_bp = Blueprint("nist_evidence", __name__)


def _positive_int(value, default: int, *, maximum: int) -> int:
    try:
        parsed = int(value if value not in (None, "") else default)
    except (TypeError, ValueError) as error:
        raise NistEvidenceValidationError("pagination values must be integers") from error
    if parsed < 0:
        raise NistEvidenceValidationError("pagination values must be non-negative")
    return min(parsed, maximum)


def _audit(event_type: str, details: dict) -> None:
    log_audit_event(
        event_type,
        actor_username=current_user.id,
        actor_role=current_user.role,
        http_method=request.method,
        request_path=request.path,
        source_ip=request.remote_addr,
        details=details,
    )


def _cursor_datetime(value: str | None) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as error:
        raise NistEvidenceValidationError(
            "before_created_at must be an ISO-8601 timestamp"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise NistEvidenceValidationError(
            "before_created_at must include a timezone offset"
        )
    return parsed.astimezone(timezone.utc)


@nist_evidence_bp.route("/nist/evidence/catalog", methods=["GET"])
@login_required
@analyst_or_super_admin_required
def get_nist_evidence_catalog():
    return jsonify(catalog_document()), 200


@nist_evidence_bp.route("/nist/evidence/boundaries", methods=["GET"])
@login_required
@analyst_or_super_admin_required
def get_nist_boundaries():
    conn = None
    try:
        conn = get_db_connection()
        include_inactive = request.args.get("include_inactive", "false").lower() == "true"
        limit = _positive_int(request.args.get("limit"), 100, maximum=100)
        return jsonify({"items": list_boundaries(conn, include_inactive=include_inactive, limit=limit)}), 200
    except NistEvidenceValidationError as error:
        return jsonify({"error": str(error)}), 400
    except Exception as error:
        current_app.logger.error("Error listing NIST assessment boundaries: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()


@nist_evidence_bp.route("/nist/evidence/boundaries/<int:boundary_id>", methods=["GET"])
@login_required
@analyst_or_super_admin_required
def get_nist_boundary(boundary_id: int):
    conn = None
    try:
        conn = get_db_connection()
        boundary = get_boundary(conn, boundary_id)
        if not boundary:
            return jsonify({"error": "Assessment boundary not found"}), 404
        return jsonify(boundary), 200
    except Exception as error:
        current_app.logger.error("Error reading NIST assessment boundary: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()


@nist_evidence_bp.route("/nist/evidence/boundaries", methods=["POST"])
@login_required
@super_admin_required
def create_nist_boundary():
    conn = None
    try:
        conn = get_db_connection()
        boundary = create_boundary(conn, request.get_json(silent=True) or {}, actor_username=current_user.id)
        conn.commit()
        _audit("NIST_EVIDENCE_BOUNDARY_CREATED", {"boundary_id": boundary["id"]})
        return jsonify(boundary), 201
    except NistEvidenceValidationError as error:
        if conn:
            conn.rollback()
        return jsonify({"error": str(error)}), 400
    except IntegrityError:
        if conn:
            conn.rollback()
        return jsonify({"error": "Assessment boundary name already exists"}), 409
    except Exception as error:
        if conn:
            conn.rollback()
        current_app.logger.error("Error creating NIST assessment boundary: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()


@nist_evidence_bp.route("/nist/evidence/boundaries/<int:boundary_id>", methods=["PATCH"])
@login_required
@super_admin_required
def update_nist_boundary(boundary_id: int):
    conn = None
    try:
        conn = get_db_connection()
        boundary = update_boundary(
            conn, boundary_id, request.get_json(silent=True) or {}, actor_username=current_user.id
        )
        if not boundary:
            conn.rollback()
            return jsonify({"error": "Assessment boundary not found"}), 404
        conn.commit()
        _audit("NIST_EVIDENCE_BOUNDARY_UPDATED", {"boundary_id": boundary_id})
        return jsonify(boundary), 200
    except NistEvidenceValidationError as error:
        if conn:
            conn.rollback()
        return jsonify({"error": str(error)}), 400
    except IntegrityError:
        if conn:
            conn.rollback()
        return jsonify({"error": "Assessment boundary name already exists"}), 409
    except Exception as error:
        if conn:
            conn.rollback()
        current_app.logger.error("Error updating NIST assessment boundary: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()


@nist_evidence_bp.route("/nist/evidence/boundaries/<int:boundary_id>/runs", methods=["POST"])
@login_required
@super_admin_required
def start_nist_assessment_run(boundary_id: int):
    conn = None
    try:
        conn = get_db_connection()
        run_id = execute_assessment_run(
            conn,
            boundary_id=boundary_id,
            payload=request.get_json(silent=True) or {},
            actor_username=current_user.id,
        )
        run = get_run(conn, run_id)
        _audit("NIST_EVIDENCE_RUN_CREATED", {"boundary_id": boundary_id, "run_id": run_id})
        return jsonify(run), 201
    except NistEvidenceValidationError as error:
        if conn:
            conn.rollback()
        status = 404 if "not found" in str(error).lower() else 400
        return jsonify({"error": str(error)}), status
    except Exception as error:
        if conn:
            conn.rollback()
        current_app.logger.error("Error executing NIST evidence run: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()


@nist_evidence_bp.route("/nist/evidence/boundaries/<int:boundary_id>/runs", methods=["GET"])
@login_required
@analyst_or_super_admin_required
def get_nist_boundary_runs(boundary_id: int):
    conn = None
    try:
        conn = get_db_connection()
        if not get_boundary(conn, boundary_id):
            return jsonify({"error": "Assessment boundary not found"}), 404
        limit = _positive_int(request.args.get("limit"), 25, maximum=50)
        if limit == 0:
            raise NistEvidenceValidationError("limit must be a positive integer")
        raw_before_id = request.args.get("before_id")
        before_created_at = _cursor_datetime(request.args.get("before_created_at"))
        before_id = (
            _positive_int(raw_before_id, 0, maximum=2**63 - 1)
            if raw_before_id not in (None, "") else None
        )
        if (before_created_at is None) != (before_id is None):
            raise NistEvidenceValidationError(
                "before_created_at and before_id must be provided together"
            )
        if before_id == 0:
            raise NistEvidenceValidationError("before_id must be a positive integer")
        return jsonify(
            list_boundary_runs(
                conn,
                boundary_id,
                limit=limit,
                before_created_at=before_created_at,
                before_id=before_id,
            )
        ), 200
    except NistEvidenceValidationError as error:
        return jsonify({"error": str(error)}), 400
    except Exception as error:
        current_app.logger.error("Error listing NIST assessment runs: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()


@nist_evidence_bp.route("/nist/evidence/runs/<int:run_id>", methods=["GET"])
@login_required
@analyst_or_super_admin_required
def get_nist_assessment_run(run_id: int):
    conn = None
    try:
        conn = get_db_connection()
        run = get_run(conn, run_id)
        if not run:
            return jsonify({"error": "Assessment run not found"}), 404
        return jsonify(run), 200
    except Exception as error:
        current_app.logger.error("Error reading NIST evidence run: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()


@nist_evidence_bp.route("/nist/evidence/runs/<int:run_id>/results", methods=["GET"])
@login_required
@analyst_or_super_admin_required
def get_nist_requirement_results(run_id: int):
    conn = None
    try:
        conn = get_db_connection()
        if not get_run(conn, run_id):
            return jsonify({"error": "Assessment run not found"}), 404
        return jsonify({"items": list_requirement_results(conn, run_id)}), 200
    except Exception as error:
        current_app.logger.error("Error reading NIST requirement results: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()


@nist_evidence_bp.route(
    "/nist/evidence/runs/<int:run_id>/results/<requirement_id>/evidence", methods=["GET"]
)
@login_required
@analyst_or_super_admin_required
def get_nist_requirement_evidence(run_id: int, requirement_id: str):
    conn = None
    try:
        conn = get_db_connection()
        if not get_run(conn, run_id):
            return jsonify({"error": "Assessment run not found"}), 404
        if not get_requirement_result(conn, run_id, requirement_id):
            return jsonify({"error": "Requirement result not found"}), 404
        limit = _positive_int(request.args.get("limit"), 100, maximum=100)
        offset = _positive_int(request.args.get("offset"), 0, maximum=10000)
        return jsonify(
            list_evidence_references(conn, run_id, requirement_id, limit=limit, offset=offset)
        ), 200
    except NistEvidenceValidationError as error:
        return jsonify({"error": str(error)}), 400
    except Exception as error:
        current_app.logger.error("Error reading NIST evidence references: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()


@nist_evidence_bp.route("/nist/evidence/explanations", methods=["POST"])
@login_required
@analyst_or_super_admin_required
def queue_nist_evidence_explanation():
    conn = None
    payload = request.get_json(silent=True)
    try:
        conn = get_db_connection()
        result, created = enqueue_explanation(
            conn,
            payload,
            actor_username=current_user.id,
            actor_role=current_user.role,
        )
        conn.commit()
        binding = result["binding"]
        _audit(
            "NIST_EVIDENCE_EXPLANATION_QUEUED"
            if created else "NIST_EVIDENCE_EXPLANATION_DUPLICATE",
            {
                "workflow_request_id": result.get("request_id"),
                **binding,
                "created": created,
            },
        )
        return jsonify(result), 202 if created else 200
    except NistExplanationValidationError as error:
        if conn:
            conn.rollback()
        return jsonify({"error": str(error), "error_code": "invalid_explanation_request"}), 400
    except NistExplanationBindingError:
        if conn:
            conn.rollback()
        safe = payload if isinstance(payload, dict) else {}
        _audit(
            "NIST_EVIDENCE_EXPLANATION_BINDING_REJECTED",
            {
                "workflow_request_id": None,
                "boundary_id": safe.get("boundary_id"),
                "run_id": safe.get("run_id"),
                "requirement_result_id": safe.get("requirement_result_id"),
                "requirement_id": safe.get("requirement_id"),
                "outcome": "rejected",
                "error_code": "binding_invalid",
            },
        )
        return jsonify({"error": "NIST evidence result not found", "error_code": "binding_invalid"}), 404
    except Exception as error:
        if conn:
            conn.rollback()
        current_app.logger.error("Error queueing NIST evidence explanation: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()


def _export_payload(conn, run_id: int) -> dict | None:
    run = get_run(conn, run_id)
    if not run:
        return None
    boundary = get_boundary(conn, run["boundary_id"])
    results = list_requirement_results(conn, run_id)
    for result in results:
        result["evidence_references"] = list_evidence_references(
            conn, run_id, result["requirement_id"], limit=100
        )["items"]
    return {
        "assessment_support_notice": "Evidence availability does not determine requirement satisfaction.",
        "framework": {"id": run["framework_id"], "version": run["framework_version"]},
        "boundary": boundary,
        "run": run,
        "requirement_results": results,
    }


@nist_evidence_bp.route("/nist/evidence/runs/<int:run_id>/export", methods=["GET"])
@login_required
@analyst_or_super_admin_required
def export_nist_assessment_run(run_id: int):
    conn = None
    try:
        conn = get_db_connection()
        payload = _export_payload(conn, run_id)
        if not payload:
            return jsonify({"error": "Assessment run not found"}), 404
        export_format = request.args.get("format", "json").strip().lower()
        if export_format not in {"json", "csv"}:
            return jsonify({"error": "format must be json or csv"}), 400
        _audit("NIST_EVIDENCE_RUN_EXPORTED", {"run_id": run_id, "format": export_format})
        if export_format == "json":
            return Response(
                json.dumps(payload, sort_keys=True, separators=(",", ":")),
                mimetype="application/json",
                headers={"Content-Disposition": f'attachment; filename="nist-evidence-run-{run_id}.json"'},
            )

        output = StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "framework_id", "framework_version", "run_id", "boundary_id",
            "requirement_id", "requirement_name", "mapping_strength", "evidence_status",
            "collection_confidence", "reason_code", "limitation", "evidence_count",
            "omitted_count", "evidence_category", "entity_type", "entity_id",
            "canonical_source", "occurrence_timestamp", "ingestion_timestamp",
            "operational_classification", "query_hash",
        ])
        for result in payload["requirement_results"]:
            references = result["evidence_references"] or [None]
            for reference in references:
                writer.writerow([
                    payload["framework"]["id"], payload["framework"]["version"], run_id,
                    payload["boundary"]["id"], result["requirement_id"],
                    result["requirement_name"], result["mapping_strength"],
                    result["evidence_status"], result["collection_confidence"],
                    result["reason_code"], result["limitation"], result["evidence_count"],
                    result["omitted_count"], reference["evidence_category"] if reference else "",
                    reference["entity_type"] if reference else "",
                    reference["entity_id"] if reference else "",
                    reference["canonical_source"] if reference else "",
                    reference["occurrence_timestamp"] if reference else "",
                    reference["ingestion_timestamp"] if reference else "",
                    reference["operational_classification"] if reference else "",
                    reference["query_hash"] if reference else "",
                ])
        return Response(
            output.getvalue(),
            mimetype="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="nist-evidence-run-{run_id}.csv"'},
        )
    except Exception as error:
        current_app.logger.error("Error exporting NIST evidence run: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()
