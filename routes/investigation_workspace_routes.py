from __future__ import annotations

from typing import Any

from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_required

from core.audit_helpers import log_audit_event
from core.auth import analyst_or_super_admin_required, deny_rbac_access
from core.db import get_db_connection
from core.investigation_workspace_store import (
    WorkspaceOwnershipError,
    create_evidence,
    create_hypothesis,
    create_investigation,
    create_note,
    create_task,
    delete_owned_record,
    get_or_create_default_workspace,
    link_hypothesis_evidence,
    list_hypothesis_evidence_links,
    list_investigations,
    load_active_investigation_bundle,
    load_workspace_bundle,
    pin_workspace_item,
    reorder_workspace_items,
    update_owned_record,
)


investigation_workspace_bp = Blueprint("investigation_workspace", __name__)


def _audit(event_type: str, *, details: dict[str, Any] | None = None, target_alert_id: int | None = None) -> None:
    log_audit_event(
        event_type,
        actor_username=getattr(current_user, "id", None),
        actor_role=getattr(current_user, "role", None),
        target_alert_id=target_alert_id,
        http_method=request.method,
        request_path=request.path,
        source_ip=request.remote_addr,
        details=details or {},
    )


def _owner() -> str:
    return str(getattr(current_user, "id", "") or "").strip()


def _json() -> dict[str, Any]:
    data = request.get_json(silent=True) or {}
    return data if isinstance(data, dict) else {}


def _handle_error(error: Exception):
    if isinstance(error, WorkspaceOwnershipError):
        _audit("INVESTIGATION_WORKSPACE_ACCESS_DENIED", details={"reason": str(error)})
        return deny_rbac_access("workspace_owner_required", "Workspace record not found or not owned by current analyst")
    if isinstance(error, LookupError):
        return jsonify({"error": str(error)}), 404
    if isinstance(error, ValueError):
        return jsonify({"error": str(error)}), 400
    current_app.logger.error("Investigation workspace route failed: %s", error)
    return jsonify({"error": "Internal server error"}), 500


@investigation_workspace_bp.route("/analyst-workspace", methods=["GET"])
@login_required
@analyst_or_super_admin_required
def get_analyst_workspace():
    conn = None
    try:
        conn = get_db_connection()
        bundle = load_workspace_bundle(conn, _owner())
        conn.commit()
        return jsonify(bundle), 200
    except Exception as error:
        if conn:
            conn.rollback()
        return _handle_error(error)
    finally:
        if conn:
            conn.close()


@investigation_workspace_bp.route("/analyst-workspace/pins", methods=["POST"])
@login_required
@analyst_or_super_admin_required
def create_workspace_pin():
    conn = None
    try:
        data = _json()
        conn = get_db_connection()
        workspace = get_or_create_default_workspace(conn, _owner())
        item = pin_workspace_item(
            conn,
            owner_username=_owner(),
            workspace_id=workspace["id"],
            item_type=data.get("item_type"),
            referenced_object_type=data.get("referenced_object_type"),
            referenced_object_id=str(data.get("referenced_object_id") or ""),
            label=data.get("label"),
            metadata=data.get("metadata") if isinstance(data.get("metadata"), dict) else {},
        )
        conn.commit()
        _audit(
            "INVESTIGATION_WORKSPACE_PIN",
            details={
                "workspace_id": workspace["id"],
                "workspace_item_id": item["id"],
                "item_type": item["item_type"],
                "referenced_object_type": item["referenced_object_type"],
                "referenced_object_id": item["referenced_object_id"],
                "system_mutation": False,
            },
            target_alert_id=int(item["referenced_object_id"]) if item["item_type"] == "alert" and str(item["referenced_object_id"]).isdigit() else None,
        )
        return jsonify(item), 201
    except Exception as error:
        if conn:
            conn.rollback()
        return _handle_error(error)
    finally:
        if conn:
            conn.close()


@investigation_workspace_bp.route("/analyst-workspace/pins/<int:item_id>", methods=["DELETE"])
@login_required
@analyst_or_super_admin_required
def delete_workspace_pin(item_id):
    conn = None
    try:
        conn = get_db_connection()
        delete_owned_record(conn, table="workspace_items", record_id=item_id, owner_username=_owner())
        conn.commit()
        _audit("INVESTIGATION_WORKSPACE_UNPIN", details={"workspace_item_id": item_id, "system_mutation": False})
        return jsonify({"deleted": True, "id": item_id}), 200
    except Exception as error:
        if conn:
            conn.rollback()
        return _handle_error(error)
    finally:
        if conn:
            conn.close()


@investigation_workspace_bp.route("/analyst-workspace/pins/<int:item_id>", methods=["PATCH"])
@login_required
@analyst_or_super_admin_required
def update_workspace_pin(item_id):
    return _update_record(
        table="workspace_items",
        record_id=item_id,
        event_type="INVESTIGATION_WORKSPACE_UPDATE",
        detail_key="workspace_item_id",
    )


@investigation_workspace_bp.route("/analyst-workspace/pins/reorder", methods=["POST"])
@login_required
@analyst_or_super_admin_required
def reorder_workspace_pins():
    conn = None
    try:
        data = _json()
        conn = get_db_connection()
        workspace = get_or_create_default_workspace(conn, _owner())
        workspace_id = data.get("workspace_id") or workspace["id"]
        ordered_ids = data.get("ordered_item_ids") or []
        if not isinstance(ordered_ids, list):
            raise ValueError("ordered_item_ids must be a list")
        items = reorder_workspace_items(
            conn,
            owner_username=_owner(),
            workspace_id=workspace_id,
            ordered_item_ids=[int(item_id) for item_id in ordered_ids],
        )
        conn.commit()
        _audit(
            "INVESTIGATION_WORKSPACE_REORDER",
            details={"workspace_id": workspace_id, "ordered_item_ids": ordered_ids, "system_mutation": False},
        )
        return jsonify({"items": items}), 200
    except Exception as error:
        if conn:
            conn.rollback()
        return _handle_error(error)
    finally:
        if conn:
            conn.close()


@investigation_workspace_bp.route("/investigations", methods=["POST"])
@login_required
@analyst_or_super_admin_required
def create_investigation_route():
    conn = None
    try:
        data = _json()
        conn = get_db_connection()
        workspace = get_or_create_default_workspace(conn, _owner())
        investigation = create_investigation(
            conn,
            owner_username=_owner(),
            workspace_id=workspace["id"],
            title=data.get("title") or "Investigation",
            status=data.get("status") or "open",
            summary=data.get("summary"),
            linked_alert_id=data.get("linked_alert_id"),
            linked_incident_id=data.get("linked_incident_id"),
            linked_source_ip=data.get("linked_source_ip"),
            saved_state=data.get("saved_state") if isinstance(data.get("saved_state"), dict) else {},
            disposition=data.get("disposition") or "undetermined",
            confidence=data.get("confidence") or "medium",
            conclusion=data.get("conclusion"),
        )
        conn.commit()
        _audit("INVESTIGATION_CREATE", details={"investigation_id": investigation["id"], "workspace_id": workspace["id"], "system_mutation": False})
        return jsonify(investigation), 201
    except Exception as error:
        if conn:
            conn.rollback()
        return _handle_error(error)
    finally:
        if conn:
            conn.close()


@investigation_workspace_bp.route("/investigations", methods=["GET"])
@login_required
@analyst_or_super_admin_required
def list_investigations_route():
    conn = None
    try:
        conn = get_db_connection()
        investigations = list_investigations(conn, _owner())
        conn.commit()
        return jsonify({"investigations": investigations}), 200
    except Exception as error:
        if conn:
            conn.rollback()
        return _handle_error(error)
    finally:
        if conn:
            conn.close()


@investigation_workspace_bp.route("/investigations/<int:investigation_id>/workspace", methods=["GET"])
@login_required
@analyst_or_super_admin_required
def get_active_investigation_workspace(investigation_id):
    conn = None
    try:
        conn = get_db_connection()
        bundle = load_active_investigation_bundle(conn, _owner(), investigation_id)
        conn.commit()
        return jsonify(bundle), 200
    except Exception as error:
        if conn:
            conn.rollback()
        return _handle_error(error)
    finally:
        if conn:
            conn.close()


@investigation_workspace_bp.route("/investigations/<int:investigation_id>", methods=["DELETE"])
@login_required
@analyst_or_super_admin_required
def delete_investigation_route(investigation_id):
    conn = None
    try:
        conn = get_db_connection()
        delete_owned_record(conn, table="investigations", record_id=investigation_id, owner_username=_owner())
        conn.commit()
        _audit("INVESTIGATION_DELETE", details={"investigation_id": investigation_id, "system_mutation": False})
        return jsonify({"deleted": True, "id": investigation_id}), 200
    except Exception as error:
        if conn:
            conn.rollback()
        return _handle_error(error)
    finally:
        if conn:
            conn.close()


@investigation_workspace_bp.route("/investigations/<int:investigation_id>", methods=["PATCH"])
@login_required
@analyst_or_super_admin_required
def update_investigation_route(investigation_id):
    return _update_record(
        table="investigations",
        record_id=investigation_id,
        event_type="INVESTIGATION_UPDATE",
        detail_key="investigation_id",
    )


@investigation_workspace_bp.route("/analyst-workspace/notes", methods=["POST"])
@login_required
@analyst_or_super_admin_required
def create_workspace_note():
    return _create_child_record("note")


@investigation_workspace_bp.route("/analyst-workspace/hypotheses", methods=["POST"])
@login_required
@analyst_or_super_admin_required
def create_workspace_hypothesis():
    return _create_child_record("hypothesis")


@investigation_workspace_bp.route("/analyst-workspace/tasks", methods=["POST"])
@login_required
@analyst_or_super_admin_required
def create_workspace_task():
    return _create_child_record("task")


@investigation_workspace_bp.route("/analyst-workspace/evidence", methods=["POST"])
@login_required
@analyst_or_super_admin_required
def create_workspace_evidence():
    return _create_child_record("evidence")


@investigation_workspace_bp.route("/analyst-workspace/notes/<int:record_id>", methods=["PATCH", "DELETE"])
@login_required
@analyst_or_super_admin_required
def mutate_workspace_note(record_id):
    return _mutate_child_record("investigation_notes", record_id, "INVESTIGATION_WORKSPACE_NOTE")


@investigation_workspace_bp.route("/analyst-workspace/hypotheses/<int:record_id>", methods=["PATCH", "DELETE"])
@login_required
@analyst_or_super_admin_required
def mutate_workspace_hypothesis(record_id):
    return _mutate_child_record("investigation_hypotheses", record_id, "INVESTIGATION_WORKSPACE_HYPOTHESIS")


@investigation_workspace_bp.route("/analyst-workspace/tasks/<int:record_id>", methods=["PATCH", "DELETE"])
@login_required
@analyst_or_super_admin_required
def mutate_workspace_task(record_id):
    return _mutate_child_record("investigation_tasks", record_id, "INVESTIGATION_WORKSPACE_TASK")


@investigation_workspace_bp.route("/analyst-workspace/evidence/<int:record_id>", methods=["PATCH", "DELETE"])
@login_required
@analyst_or_super_admin_required
def mutate_workspace_evidence(record_id):
    return _mutate_child_record("evidence_references", record_id, "INVESTIGATION_WORKSPACE_EVIDENCE")


def _create_child_record(kind: str):
    conn = None
    try:
        data = _json()
        conn = get_db_connection()
        workspace = get_or_create_default_workspace(conn, _owner())
        workspace_id = data.get("workspace_id") or workspace["id"]
        investigation_id = data.get("investigation_id")
        if kind == "note":
            record = create_note(conn, owner_username=_owner(), workspace_id=workspace_id, investigation_id=investigation_id, body=data.get("body"))
            event_type = "INVESTIGATION_WORKSPACE_NOTE_CREATE"
        elif kind == "hypothesis":
            record = create_hypothesis(
                conn,
                owner_username=_owner(),
                workspace_id=workspace_id,
                investigation_id=investigation_id,
                title=data.get("title"),
                body=data.get("body"),
                status=data.get("status") or "open",
                confidence=data.get("confidence") or "medium",
            )
            event_type = "INVESTIGATION_WORKSPACE_HYPOTHESIS_CREATE"
        elif kind == "task":
            record = create_task(
                conn,
                owner_username=_owner(),
                workspace_id=workspace_id,
                investigation_id=investigation_id,
                title=data.get("title"),
                status=data.get("status") or "open",
                hypothesis_id=data.get("hypothesis_id"),
                evidence_reference_id=data.get("evidence_reference_id"),
            )
            event_type = "INVESTIGATION_WORKSPACE_TASK_CREATE"
        elif kind == "evidence":
            record = create_evidence(
                conn,
                owner_username=_owner(),
                workspace_id=workspace_id,
                investigation_id=investigation_id,
                referenced_object_type=data.get("referenced_object_type"),
                referenced_object_id=str(data.get("referenced_object_id") or ""),
                label=data.get("label"),
                source=data.get("source"),
                metadata=data.get("metadata") if isinstance(data.get("metadata"), dict) else {},
                rationale=data.get("rationale"),
                relationship_type=data.get("relationship_type") or "context",
            )
            event_type = "INVESTIGATION_WORKSPACE_EVIDENCE_CREATE"
        else:
            raise ValueError("unsupported workspace record kind")
        conn.commit()
        _audit(event_type, details={"record_id": record["id"], "workspace_id": workspace_id, "investigation_id": investigation_id, "system_mutation": False})
        return jsonify(record), 201
    except Exception as error:
        if conn:
            conn.rollback()
        return _handle_error(error)
    finally:
        if conn:
            conn.close()


@investigation_workspace_bp.route("/investigations/<int:investigation_id>/hypothesis-evidence", methods=["GET", "POST"])
@login_required
@analyst_or_super_admin_required
def hypothesis_evidence_links_route(investigation_id):
    conn = None
    try:
        conn = get_db_connection()
        if request.method == "GET":
            links = list_hypothesis_evidence_links(conn, _owner(), investigation_id=investigation_id)
            conn.commit()
            return jsonify({"hypothesis_evidence": links}), 200
        data = _json()
        try:
            hypothesis_id = int(data.get("hypothesis_id"))
            evidence_reference_id = int(data.get("evidence_reference_id"))
        except (TypeError, ValueError):
            raise ValueError("hypothesis_id and evidence_reference_id are required")
        link = link_hypothesis_evidence(
            conn,
            owner_username=_owner(),
            investigation_id=investigation_id,
            hypothesis_id=hypothesis_id,
            evidence_reference_id=evidence_reference_id,
            relationship_type=data.get("relationship_type") or "context",
            rationale=data.get("rationale"),
        )
        conn.commit()
        _audit(
            "INVESTIGATION_HYPOTHESIS_EVIDENCE_LINK",
            details={
                "investigation_id": investigation_id,
                "hypothesis_id": link["hypothesis_id"],
                "evidence_reference_id": link["evidence_reference_id"],
                "relationship_type": link["relationship_type"],
                "system_mutation": False,
            },
        )
        return jsonify(link), 201
    except Exception as error:
        if conn:
            conn.rollback()
        return _handle_error(error)
    finally:
        if conn:
            conn.close()


@investigation_workspace_bp.route("/investigations/hypothesis-evidence/<int:link_id>", methods=["PATCH", "DELETE"])
@login_required
@analyst_or_super_admin_required
def mutate_hypothesis_evidence_link(link_id):
    return _mutate_child_record("investigation_hypothesis_evidence", link_id, "INVESTIGATION_HYPOTHESIS_EVIDENCE")


def _mutate_child_record(table: str, record_id: int, event_prefix: str):
    if request.method == "DELETE":
        return _delete_record(table=table, record_id=record_id, event_type=f"{event_prefix}_DELETE")
    return _update_record(
        table=table,
        record_id=record_id,
        event_type=f"{event_prefix}_UPDATE",
        detail_key="record_id",
    )


def _delete_record(*, table: str, record_id: int, event_type: str):
    conn = None
    try:
        conn = get_db_connection()
        delete_owned_record(conn, table=table, record_id=record_id, owner_username=_owner())
        conn.commit()
        _audit(event_type, details={"record_id": record_id, "system_mutation": False})
        return jsonify({"deleted": True, "id": record_id}), 200
    except Exception as error:
        if conn:
            conn.rollback()
        return _handle_error(error)
    finally:
        if conn:
            conn.close()


def _update_record(*, table: str, record_id: int, event_type: str, detail_key: str):
    conn = None
    try:
        conn = get_db_connection()
        record = update_owned_record(
            conn,
            table=table,
            record_id=record_id,
            owner_username=_owner(),
            updates=_json(),
        )
        conn.commit()
        _audit(
            event_type,
            details={detail_key: record_id, "updated_fields": sorted(_json().keys()), "system_mutation": False},
        )
        return jsonify(record), 200
    except Exception as error:
        if conn:
            conn.rollback()
        return _handle_error(error)
    finally:
        if conn:
            conn.close()
