from __future__ import annotations

from typing import Any

from psycopg2.extras import Json


VALID_ITEM_TYPES = {
    "alert",
    "incident",
    "recon_activity",
    "source_ip",
    "investigation",
    "evidence",
}
VALID_HYPOTHESIS_STATUSES = {"open", "supported", "rejected", "unknown"}
VALID_TASK_STATUSES = {"open", "in_progress", "done"}
VALID_INVESTIGATION_STATUSES = {"open", "new", "investigating", "waiting", "awaiting_evidence", "ready_for_review", "resolved", "closed"}
VALID_CONFIDENCE_VALUES = {"low", "medium", "high"}
VALID_DISPOSITIONS = {"true_positive", "false_positive", "benign_expected", "needs_monitoring", "escalated", "undetermined"}
VALID_EVIDENCE_RELATIONSHIPS = {"supports", "refutes", "context"}

MAX_TEXT_LENGTH = 4000
MAX_TITLE_LENGTH = 240


class WorkspaceOwnershipError(PermissionError):
    pass


def _clean_text(value: Any, *, field_name: str, max_length: int = MAX_TEXT_LENGTH) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} is required")
    if len(text) > max_length:
        raise ValueError(f"{field_name} must be {max_length} characters or fewer")
    return text


def _optional_text(value: Any, *, max_length: int = MAX_TEXT_LENGTH) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:max_length]


def _fetchone_dict(cur) -> dict[str, Any] | None:
    row = cur.fetchone()
    if row is None:
        return None
    if isinstance(row, dict):
        return dict(row)
    names = [desc[0] for desc in cur.description]
    return dict(zip(names, row))


def _fetchall_dicts(cur) -> list[dict[str, Any]]:
    names = [desc[0] for desc in cur.description]
    return [dict(zip(names, row)) if not isinstance(row, dict) else dict(row) for row in cur.fetchall()]


def _json_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _ensure_owner(owner_username: str) -> str:
    return _clean_text(owner_username, field_name="owner_username", max_length=128)


def _default_workspace_title(owner_username: str) -> str:
    return f"{owner_username}'s Investigation Workspace"


def get_or_create_default_workspace(conn, owner_username: str) -> dict[str, Any]:
    owner = _ensure_owner(owner_username)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, owner_username, name, is_default, visibility, created_at, updated_at
            FROM analyst_workspaces
            WHERE owner_username = %s AND is_default = TRUE
            ORDER BY id
            LIMIT 1
            """,
            (owner,),
        )
        existing = _fetchone_dict(cur)
        if existing:
            return _serialize_workspace(existing)

        cur.execute(
            """
            INSERT INTO analyst_workspaces (owner_username, name, is_default, visibility)
            VALUES (%s, %s, TRUE, 'private')
            RETURNING id, owner_username, name, is_default, visibility, created_at, updated_at
            """,
            (owner, _default_workspace_title(owner)),
        )
        return _serialize_workspace(_fetchone_dict(cur))


def get_workspace(conn, workspace_id: int, owner_username: str) -> dict[str, Any]:
    owner = _ensure_owner(owner_username)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, owner_username, name, is_default, visibility, created_at, updated_at
            FROM analyst_workspaces
            WHERE id = %s
            """,
            (workspace_id,),
        )
        row = _fetchone_dict(cur)
    if row is None:
        raise LookupError("workspace not found")
    if row["owner_username"] != owner:
        raise WorkspaceOwnershipError("workspace access denied")
    return _serialize_workspace(row)


def load_workspace_bundle(conn, owner_username: str) -> dict[str, Any]:
    workspace = get_or_create_default_workspace(conn, owner_username)
    workspace_id = workspace["id"]
    return {
        "workspace": workspace,
        "items": list_workspace_items(conn, workspace_id, owner_username),
        "investigations": list_investigations(conn, owner_username),
        "notes": list_notes(conn, owner_username, workspace_id=workspace_id),
        "hypotheses": list_hypotheses(conn, owner_username, workspace_id=workspace_id),
        "tasks": list_tasks(conn, owner_username, workspace_id=workspace_id),
        "evidence": list_evidence(conn, owner_username, workspace_id=workspace_id),
    }


def load_active_investigation_bundle(conn, owner_username: str, investigation_id: int) -> dict[str, Any]:
    owner = _ensure_owner(owner_username)
    workspace = get_or_create_default_workspace(conn, owner)
    investigation = get_investigation_for_owner(conn, investigation_id, owner)
    notes = list_notes(conn, owner, investigation_id=investigation_id)
    hypotheses = list_hypotheses(conn, owner, investigation_id=investigation_id)
    tasks = list_tasks(conn, owner, investigation_id=investigation_id)
    evidence = list_evidence(conn, owner, investigation_id=investigation_id)
    relationships = list_hypothesis_evidence_links(conn, owner, investigation_id=investigation_id)
    timeline = build_investigation_timeline(investigation, notes=notes, hypotheses=hypotheses, tasks=tasks, evidence=evidence)
    return {
        "workspace": workspace,
        "investigation": investigation,
        "source_context": resolve_investigation_source_context(conn, investigation),
        "notes": notes,
        "hypotheses": hypotheses,
        "tasks": tasks,
        "evidence": evidence,
        "hypothesis_evidence": relationships,
        "timeline": timeline,
        "unassigned": {
            "items": list_workspace_items(conn, workspace["id"], owner),
            "notes": list_notes(conn, owner, workspace_id=workspace["id"]),
            "hypotheses": list_hypotheses(conn, owner, workspace_id=workspace["id"]),
            "tasks": list_tasks(conn, owner, workspace_id=workspace["id"]),
            "evidence": list_evidence(conn, owner, workspace_id=workspace["id"]),
        },
    }


def validate_reference(conn, item_type: str, referenced_object_id: str) -> None:
    if item_type not in VALID_ITEM_TYPES:
        raise ValueError("unsupported item_type")
    ref = _clean_text(referenced_object_id, field_name="referenced_object_id", max_length=512)
    with conn.cursor() as cur:
        if item_type == "alert":
            cur.execute("SELECT 1 FROM alerts WHERE id = %s", (ref,))
            if not cur.fetchone():
                raise LookupError("alert not found")
        elif item_type == "incident":
            cur.execute("SELECT 1 FROM incidents WHERE id = %s", (ref,))
            if not cur.fetchone():
                raise LookupError("incident not found")
        elif item_type == "recon_activity":
            cur.execute("SELECT 1 FROM recon_activities WHERE id = %s", (ref,))
            if not cur.fetchone():
                raise LookupError("recon activity not found")
        elif item_type == "investigation":
            cur.execute("SELECT 1 FROM investigations WHERE id = %s", (ref,))
            if not cur.fetchone():
                raise LookupError("investigation not found")


def pin_workspace_item(
    conn,
    *,
    owner_username: str,
    workspace_id: int,
    item_type: str,
    referenced_object_id: str,
    referenced_object_type: str | None = None,
    label: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    owner = _ensure_owner(owner_username)
    workspace = get_workspace(conn, workspace_id, owner)
    item_type = _clean_text(item_type, field_name="item_type", max_length=64)
    if item_type not in VALID_ITEM_TYPES:
        raise ValueError("unsupported item_type")
    ref_id = _clean_text(referenced_object_id, field_name="referenced_object_id", max_length=512)
    ref_type = _clean_text(referenced_object_type or item_type, field_name="referenced_object_type", max_length=80)
    validate_reference(conn, item_type, ref_id)
    label_value = _optional_text(label, max_length=240) or f"{ref_type} {ref_id}"
    metadata_value = _json_or_empty(metadata)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO workspace_items (
                workspace_id, owner_username, item_type, referenced_object_type,
                referenced_object_id, label, metadata, visibility
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'private')
            ON CONFLICT (workspace_id, item_type, referenced_object_type, referenced_object_id)
            DO UPDATE SET
                label = EXCLUDED.label,
                metadata = EXCLUDED.metadata,
                status = 'active',
                updated_at = NOW()
            RETURNING id, workspace_id, owner_username, item_type, referenced_object_type,
                referenced_object_id, label, status, item_order, metadata, visibility,
                created_at, updated_at
            """,
            (
                workspace["id"],
                owner,
                item_type,
                ref_type,
                ref_id,
                label_value,
                Json(metadata_value),
            ),
        )
        return _serialize_item(_fetchone_dict(cur))


def list_workspace_items(conn, workspace_id: int, owner_username: str) -> list[dict[str, Any]]:
    owner = _ensure_owner(owner_username)
    get_workspace(conn, workspace_id, owner)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, workspace_id, owner_username, item_type, referenced_object_type,
                referenced_object_id, label, status, item_order, metadata, visibility,
                created_at, updated_at
            FROM workspace_items
            WHERE workspace_id = %s AND owner_username = %s AND status = 'active'
            ORDER BY item_order ASC, created_at DESC
            """,
            (workspace_id, owner),
        )
        return [_serialize_item(row) for row in _fetchall_dicts(cur)]


def delete_owned_record(conn, *, table: str, record_id: int, owner_username: str) -> bool:
    if table not in {
        "workspace_items",
        "investigation_notes",
        "investigation_hypotheses",
        "investigation_tasks",
        "evidence_references",
        "investigations",
        "investigation_hypothesis_evidence",
    }:
        raise ValueError("unsupported table")
    owner = _ensure_owner(owner_username)
    with conn.cursor() as cur:
        cur.execute(f"SELECT * FROM {table} WHERE id = %s", (record_id,))
        row = cur.fetchone()
        if row is None:
            raise LookupError("record not found")
        names = [desc[0] for desc in cur.description]
        existing = dict(zip(names, row)) if not isinstance(row, dict) else dict(row)
        row_owner = existing["owner_username"]
        if row_owner != owner:
            raise WorkspaceOwnershipError("record access denied")
        cur.execute(f"DELETE FROM {table} WHERE id = %s AND owner_username = %s", (record_id, owner))
        if table != "investigations":
            _touch_investigation(cur, owner, existing.get("investigation_id"))
        return cur.rowcount > 0


UPDATE_COLUMNS_BY_TABLE = {
    "workspace_items": {"label", "status", "item_order", "metadata"},
    "investigations": {"title", "status", "summary", "saved_state", "disposition", "confidence", "conclusion"},
    "investigation_notes": {"body"},
    "investigation_hypotheses": {"title", "body", "status", "confidence"},
    "investigation_tasks": {"title", "status", "hypothesis_id", "evidence_reference_id"},
    "evidence_references": {"label", "source", "metadata", "rationale", "relationship_type"},
    "investigation_hypothesis_evidence": {"relationship_type", "rationale"},
}


def update_owned_record(
    conn,
    *,
    table: str,
    record_id: int,
    owner_username: str,
    updates: dict[str, Any],
) -> dict[str, Any]:
    if table not in UPDATE_COLUMNS_BY_TABLE:
        raise ValueError("unsupported table")
    owner = _ensure_owner(owner_username)
    allowed_columns = UPDATE_COLUMNS_BY_TABLE[table]
    clean_updates: dict[str, Any] = {}
    for key, value in updates.items():
        if key not in allowed_columns:
            continue
        clean_updates[key] = _clean_update_value(table, key, value)
    if not clean_updates:
        raise ValueError("no supported updates provided")
    with conn.cursor() as cur:
        cur.execute(f"SELECT * FROM {table} WHERE id = %s", (record_id,))
        row = cur.fetchone()
        if row is None:
            raise LookupError("record not found")
        names = [desc[0] for desc in cur.description]
        existing = dict(zip(names, row)) if not isinstance(row, dict) else dict(row)
        row_owner = existing["owner_username"]
        if row_owner != owner:
            raise WorkspaceOwnershipError("record access denied")
        if table == "investigation_tasks":
            investigation_id = existing.get("investigation_id")
            _validate_optional_child_refs(
                conn,
                owner,
                investigation_id,
                clean_updates.get("hypothesis_id"),
                clean_updates.get("evidence_reference_id"),
            )
        if table == "evidence_references" and clean_updates.get("relationship_type") not in {None, *VALID_EVIDENCE_RELATIONSHIPS}:
            raise ValueError("unsupported relationship_type")
        assignments = [f"{column} = %s" for column in clean_updates]
        if table == "investigations" and "status" in clean_updates:
            assignments.append("closed_at = CASE WHEN %s = 'closed' THEN COALESCE(closed_at, NOW()) ELSE NULL END")
            clean_updates["_closed_status"] = clean_updates["status"]
        if table == "investigations":
            assignments.append("last_activity_at = NOW()")
        touched_investigation_id = existing.get("investigation_id")
        if table == "investigation_hypothesis_evidence":
            touched_investigation_id = existing.get("investigation_id")
        values = list(clean_updates.values())
        values.extend([record_id, owner])
        cur.execute(
            f"""
            UPDATE {table}
            SET {", ".join(assignments)}, updated_at = NOW()
            WHERE id = %s AND owner_username = %s
            RETURNING *
            """,
            values,
        )
        row = _fetchone_dict(cur)
        if table != "investigations":
            _touch_investigation(cur, owner, touched_investigation_id)
    return _serialize_owned_row(table, row)


def reorder_workspace_items(
    conn,
    *,
    owner_username: str,
    workspace_id: int,
    ordered_item_ids: list[int],
) -> list[dict[str, Any]]:
    owner = _ensure_owner(owner_username)
    get_workspace(conn, workspace_id, owner)
    if not ordered_item_ids:
        raise ValueError("ordered_item_ids is required")
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id
            FROM workspace_items
            WHERE workspace_id = %s AND owner_username = %s AND id = ANY(%s)
            """,
            (workspace_id, owner, ordered_item_ids),
        )
        owned_ids = {row[0] if not isinstance(row, dict) else row["id"] for row in cur.fetchall()}
        missing_ids = set(ordered_item_ids) - owned_ids
        if missing_ids:
            raise WorkspaceOwnershipError("workspace item access denied")
        for index, item_id in enumerate(ordered_item_ids, start=1):
            cur.execute(
                """
                UPDATE workspace_items
                SET item_order = %s, updated_at = NOW()
                WHERE id = %s AND workspace_id = %s AND owner_username = %s
                """,
                (index, item_id, workspace_id, owner),
            )
    return list_workspace_items(conn, workspace_id, owner)


def _clean_update_value(table: str, key: str, value: Any) -> Any:
    if key in {"metadata", "saved_state"}:
        return Json(_json_or_empty(value))
    if key == "item_order":
        return int(value)
    if key == "status":
        text = _clean_text(value, field_name="status", max_length=64)
        if table == "workspace_items" and text not in {"active", "archived"}:
            raise ValueError("unsupported workspace item status")
        if table == "investigations" and text not in VALID_INVESTIGATION_STATUSES:
            raise ValueError("unsupported investigation status")
        if table == "investigation_hypotheses" and text not in VALID_HYPOTHESIS_STATUSES:
            raise ValueError("unsupported hypothesis status")
        if table == "investigation_tasks" and text not in VALID_TASK_STATUSES:
            raise ValueError("unsupported task status")
        return text
    if key == "confidence":
        text = _clean_text(value, field_name="confidence", max_length=64)
        if text not in VALID_CONFIDENCE_VALUES:
            raise ValueError("unsupported confidence")
        return text
    if key == "disposition":
        text = _clean_text(value, field_name="disposition", max_length=64)
        if text not in VALID_DISPOSITIONS:
            raise ValueError("unsupported disposition")
        return text
    if key == "relationship_type":
        text = _clean_text(value, field_name="relationship_type", max_length=64)
        if text not in VALID_EVIDENCE_RELATIONSHIPS:
            raise ValueError("unsupported relationship_type")
        return text
    if key in {"hypothesis_id", "evidence_reference_id"}:
        return int(value) if value not in {None, ""} else None
    if key in {"title", "label"}:
        return _clean_text(value, field_name=key, max_length=MAX_TITLE_LENGTH)
    if key == "body":
        return _clean_text(value, field_name=key)
    if key in {"summary", "conclusion", "rationale"}:
        return _optional_text(value)
    if key == "source":
        return _optional_text(value, max_length=240)
    return value


def _serialize_owned_row(table: str, row: dict[str, Any]) -> dict[str, Any]:
    if table == "workspace_items":
        return _serialize_item(row)
    if table == "investigations":
        return _serialize_investigation(row)
    if table == "investigation_notes":
        return _serialize_note(row)
    if table == "investigation_hypotheses":
        return _serialize_hypothesis(row)
    if table == "investigation_tasks":
        return _serialize_task(row)
    if table == "evidence_references":
        return _serialize_evidence(row)
    if table == "investigation_hypothesis_evidence":
        return _serialize_hypothesis_evidence_link(row)
    raise ValueError("unsupported table")


def create_investigation(
    conn,
    *,
    owner_username: str,
    workspace_id: int | None,
    title: str,
    status: str = "open",
    summary: str | None = None,
    linked_alert_id: int | None = None,
    linked_incident_id: int | None = None,
    linked_source_ip: str | None = None,
    saved_state: dict[str, Any] | None = None,
    disposition: str = "undetermined",
    confidence: str = "medium",
    conclusion: str | None = None,
) -> dict[str, Any]:
    owner = _ensure_owner(owner_username)
    if workspace_id is not None:
        get_workspace(conn, workspace_id, owner)
    title_value = _clean_text(title, field_name="title", max_length=MAX_TITLE_LENGTH)
    if status not in VALID_INVESTIGATION_STATUSES:
        raise ValueError("unsupported investigation status")
    if disposition not in VALID_DISPOSITIONS:
        raise ValueError("unsupported disposition")
    if confidence not in VALID_CONFIDENCE_VALUES:
        raise ValueError("unsupported confidence")
    if linked_alert_id is not None:
        validate_reference(conn, "alert", str(linked_alert_id))
    if linked_incident_id is not None:
        validate_reference(conn, "incident", str(linked_incident_id))
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO investigations (
                owner_username, workspace_id, title, status, summary,
                linked_alert_id, linked_incident_id, linked_source_ip, saved_state,
                disposition, confidence, conclusion, closed_at, last_activity_at, visibility
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                CASE WHEN %s = 'closed' THEN NOW() ELSE NULL END, NOW(), 'private')
            RETURNING id, owner_username, workspace_id, title, status, summary,
                linked_alert_id, linked_incident_id, linked_source_ip::TEXT AS linked_source_ip,
                disposition, confidence, conclusion, closed_at, last_activity_at,
                visibility, saved_state, created_at, updated_at
            """,
            (
                owner,
                workspace_id,
                title_value,
                status,
                _optional_text(summary),
                linked_alert_id,
                linked_incident_id,
                linked_source_ip,
                Json(_json_or_empty(saved_state)),
                disposition,
                confidence,
                _optional_text(conclusion),
                status,
            ),
        )
        return _serialize_investigation(_fetchone_dict(cur))


def list_investigations(conn, owner_username: str) -> list[dict[str, Any]]:
    owner = _ensure_owner(owner_username)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, owner_username, workspace_id, title, status, summary,
                linked_alert_id, linked_incident_id, linked_source_ip::TEXT AS linked_source_ip,
                disposition, confidence, conclusion, closed_at, last_activity_at,
                visibility, saved_state, created_at, updated_at
            FROM investigations
            WHERE owner_username = %s
            ORDER BY last_activity_at DESC, updated_at DESC, id DESC
            """,
            (owner,),
        )
        return [_serialize_investigation(row) for row in _fetchall_dicts(cur)]


def create_note(conn, *, owner_username: str, workspace_id: int | None, investigation_id: int | None, body: str) -> dict[str, Any]:
    owner = _ensure_owner(owner_username)
    workspace_id, investigation_id = _validate_parent(conn, owner, workspace_id, investigation_id)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO investigation_notes (owner_username, workspace_id, investigation_id, body)
            VALUES (%s, %s, %s, %s)
            RETURNING id, owner_username, workspace_id, investigation_id, body, created_at, updated_at
            """,
            (owner, workspace_id, investigation_id, _clean_text(body, field_name="body")),
        )
        _touch_investigation(cur, owner, investigation_id)
        return _serialize_note(_fetchone_dict(cur))


def list_notes(conn, owner_username: str, *, workspace_id: int | None = None, investigation_id: int | None = None) -> list[dict[str, Any]]:
    owner = _ensure_owner(owner_username)
    where, params = _parent_where(owner, workspace_id, investigation_id)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT id, owner_username, workspace_id, investigation_id, body, created_at, updated_at
            FROM investigation_notes
            WHERE {where}
            ORDER BY created_at DESC
            """,
            params,
        )
        return [_serialize_note(row) for row in _fetchall_dicts(cur)]


def create_hypothesis(
    conn,
    *,
    owner_username: str,
    workspace_id: int | None,
    investigation_id: int | None,
    title: str,
    body: str | None = None,
    status: str = "open",
    confidence: str = "medium",
) -> dict[str, Any]:
    owner = _ensure_owner(owner_username)
    workspace_id, investigation_id = _validate_parent(conn, owner, workspace_id, investigation_id)
    if status not in VALID_HYPOTHESIS_STATUSES:
        raise ValueError("unsupported hypothesis status")
    if confidence not in VALID_CONFIDENCE_VALUES:
        raise ValueError("unsupported confidence")
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO investigation_hypotheses (owner_username, workspace_id, investigation_id, title, body, status, confidence)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id, owner_username, workspace_id, investigation_id, title, body, status, confidence, created_at, updated_at
            """,
            (owner, workspace_id, investigation_id, _clean_text(title, field_name="title", max_length=MAX_TITLE_LENGTH), _optional_text(body), status, confidence),
        )
        _touch_investigation(cur, owner, investigation_id)
        return _serialize_hypothesis(_fetchone_dict(cur))


def list_hypotheses(conn, owner_username: str, *, workspace_id: int | None = None, investigation_id: int | None = None) -> list[dict[str, Any]]:
    owner = _ensure_owner(owner_username)
    where, params = _parent_where(owner, workspace_id, investigation_id)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT id, owner_username, workspace_id, investigation_id, title, body, status, confidence, created_at, updated_at
            FROM investigation_hypotheses
            WHERE {where}
            ORDER BY created_at DESC
            """,
            params,
        )
        return [_serialize_hypothesis(row) for row in _fetchall_dicts(cur)]


def create_task(
    conn,
    *,
    owner_username: str,
    workspace_id: int | None,
    investigation_id: int | None,
    title: str,
    status: str = "open",
    hypothesis_id: int | None = None,
    evidence_reference_id: int | None = None,
) -> dict[str, Any]:
    owner = _ensure_owner(owner_username)
    workspace_id, investigation_id = _validate_parent(conn, owner, workspace_id, investigation_id)
    if status not in VALID_TASK_STATUSES:
        raise ValueError("unsupported task status")
    _validate_optional_child_refs(conn, owner, investigation_id, hypothesis_id, evidence_reference_id)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO investigation_tasks (
                owner_username, workspace_id, investigation_id, title, status,
                hypothesis_id, evidence_reference_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id, owner_username, workspace_id, investigation_id, title, status,
                hypothesis_id, evidence_reference_id, created_at, updated_at
            """,
            (owner, workspace_id, investigation_id, _clean_text(title, field_name="title", max_length=MAX_TITLE_LENGTH), status, hypothesis_id, evidence_reference_id),
        )
        _touch_investigation(cur, owner, investigation_id)
        return _serialize_task(_fetchone_dict(cur))


def list_tasks(conn, owner_username: str, *, workspace_id: int | None = None, investigation_id: int | None = None) -> list[dict[str, Any]]:
    owner = _ensure_owner(owner_username)
    where, params = _parent_where(owner, workspace_id, investigation_id)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT id, owner_username, workspace_id, investigation_id, title, status,
                hypothesis_id, evidence_reference_id, created_at, updated_at
            FROM investigation_tasks
            WHERE {where}
            ORDER BY status ASC, created_at DESC
            """,
            params,
        )
        return [_serialize_task(row) for row in _fetchall_dicts(cur)]


def create_evidence(
    conn,
    *,
    owner_username: str,
    workspace_id: int | None,
    investigation_id: int | None,
    referenced_object_type: str,
    referenced_object_id: str,
    label: str,
    source: str | None = None,
    metadata: dict[str, Any] | None = None,
    rationale: str | None = None,
    relationship_type: str = "context",
) -> dict[str, Any]:
    owner = _ensure_owner(owner_username)
    workspace_id, investigation_id = _validate_parent(conn, owner, workspace_id, investigation_id)
    parent_type = "investigation" if investigation_id is not None else "workspace"
    if relationship_type not in VALID_EVIDENCE_RELATIONSHIPS:
        raise ValueError("unsupported relationship_type")
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO evidence_references (
                owner_username, workspace_id, investigation_id, parent_type,
                referenced_object_type, referenced_object_id, label, source, metadata,
                rationale, relationship_type
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, owner_username, workspace_id, investigation_id, parent_type,
                referenced_object_type, referenced_object_id, label, source, metadata,
                rationale, relationship_type,
                created_at, updated_at
            """,
            (
                owner,
                workspace_id,
                investigation_id,
                parent_type,
                _clean_text(referenced_object_type, field_name="referenced_object_type", max_length=80),
                _clean_text(referenced_object_id, field_name="referenced_object_id", max_length=512),
                _clean_text(label, field_name="label", max_length=240),
                _optional_text(source, max_length=240),
                Json(_json_or_empty(metadata)),
                _optional_text(rationale),
                relationship_type,
            ),
        )
        _touch_investigation(cur, owner, investigation_id)
        return _serialize_evidence(_fetchone_dict(cur))


def list_evidence(conn, owner_username: str, *, workspace_id: int | None = None, investigation_id: int | None = None) -> list[dict[str, Any]]:
    owner = _ensure_owner(owner_username)
    where, params = _parent_where(owner, workspace_id, investigation_id)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT id, owner_username, workspace_id, investigation_id, parent_type,
                referenced_object_type, referenced_object_id, label, source, metadata,
                rationale, relationship_type,
                created_at, updated_at
            FROM evidence_references
            WHERE {where}
            ORDER BY created_at DESC
            """,
            params,
        )
        return [_serialize_evidence(row) for row in _fetchall_dicts(cur)]


def get_investigation_for_owner(conn, investigation_id: int, owner_username: str) -> dict[str, Any]:
    owner = _ensure_owner(owner_username)
    investigation = _get_investigation(conn, investigation_id)
    if investigation["owner_username"] != owner:
        raise WorkspaceOwnershipError("investigation access denied")
    return _serialize_investigation(investigation)


def link_hypothesis_evidence(
    conn,
    *,
    owner_username: str,
    investigation_id: int,
    hypothesis_id: int,
    evidence_reference_id: int,
    relationship_type: str = "context",
    rationale: str | None = None,
) -> dict[str, Any]:
    owner = _ensure_owner(owner_username)
    if relationship_type not in VALID_EVIDENCE_RELATIONSHIPS:
        raise ValueError("unsupported relationship_type")
    get_investigation_for_owner(conn, investigation_id, owner)
    _validate_hypothesis_owner(conn, owner, investigation_id, hypothesis_id)
    _validate_evidence_owner(conn, owner, investigation_id, evidence_reference_id)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO investigation_hypothesis_evidence (
                owner_username, investigation_id, hypothesis_id, evidence_reference_id,
                relationship_type, rationale
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (hypothesis_id, evidence_reference_id)
            DO UPDATE SET relationship_type = EXCLUDED.relationship_type,
                rationale = EXCLUDED.rationale,
                updated_at = NOW()
            RETURNING id, owner_username, investigation_id, hypothesis_id,
                evidence_reference_id, relationship_type, rationale, created_at, updated_at
            """,
            (owner, investigation_id, hypothesis_id, evidence_reference_id, relationship_type, _optional_text(rationale)),
        )
        _touch_investigation(cur, owner, investigation_id)
        return _serialize_hypothesis_evidence_link(_fetchone_dict(cur))


def list_hypothesis_evidence_links(conn, owner_username: str, *, investigation_id: int) -> list[dict[str, Any]]:
    owner = _ensure_owner(owner_username)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, owner_username, investigation_id, hypothesis_id,
                evidence_reference_id, relationship_type, rationale, created_at, updated_at
            FROM investigation_hypothesis_evidence
            WHERE owner_username = %s AND investigation_id = %s
            ORDER BY created_at DESC
            """,
            (owner, investigation_id),
        )
        return [_serialize_hypothesis_evidence_link(row) for row in _fetchall_dicts(cur)]


def _validate_parent(conn, owner: str, workspace_id: int | None, investigation_id: int | None) -> tuple[int | None, int | None]:
    if workspace_id is None and investigation_id is None:
        workspace = get_or_create_default_workspace(conn, owner)
        workspace_id = workspace["id"]
    if workspace_id is not None:
        get_workspace(conn, workspace_id, owner)
    if investigation_id is not None:
        investigation = _get_investigation(conn, investigation_id)
        if investigation["owner_username"] != owner:
            raise WorkspaceOwnershipError("investigation access denied")
    return workspace_id, investigation_id


def _validate_optional_child_refs(
    conn,
    owner: str,
    investigation_id: int | None,
    hypothesis_id: int | None,
    evidence_reference_id: int | None,
) -> None:
    if hypothesis_id is not None:
        _validate_hypothesis_owner(conn, owner, investigation_id, hypothesis_id)
    if evidence_reference_id is not None:
        _validate_evidence_owner(conn, owner, investigation_id, evidence_reference_id)


def _validate_hypothesis_owner(conn, owner: str, investigation_id: int | None, hypothesis_id: int) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT owner_username, investigation_id
            FROM investigation_hypotheses
            WHERE id = %s
            """,
            (hypothesis_id,),
        )
        row = _fetchone_dict(cur)
    if row is None:
        raise LookupError("hypothesis not found")
    if row["owner_username"] != owner:
        raise WorkspaceOwnershipError("hypothesis access denied")
    if investigation_id is not None and row.get("investigation_id") != investigation_id:
        raise ValueError("hypothesis must belong to the same investigation")


def _validate_evidence_owner(conn, owner: str, investigation_id: int | None, evidence_reference_id: int) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT owner_username, investigation_id
            FROM evidence_references
            WHERE id = %s
            """,
            (evidence_reference_id,),
        )
        row = _fetchone_dict(cur)
    if row is None:
        raise LookupError("evidence reference not found")
    if row["owner_username"] != owner:
        raise WorkspaceOwnershipError("evidence access denied")
    if investigation_id is not None and row.get("investigation_id") != investigation_id:
        raise ValueError("evidence must belong to the same investigation")


def _touch_investigation(cur, owner: str, investigation_id: int | None) -> None:
    if investigation_id is None:
        return
    cur.execute(
        """
        UPDATE investigations
        SET last_activity_at = NOW(), updated_at = NOW()
        WHERE id = %s AND owner_username = %s
        """,
        (investigation_id, owner),
    )


def _get_investigation(conn, investigation_id: int) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, owner_username, workspace_id, title, status, summary,
                linked_alert_id, linked_incident_id, linked_source_ip::TEXT AS linked_source_ip,
                disposition, confidence, conclusion, closed_at, last_activity_at,
                visibility, saved_state, created_at, updated_at
            FROM investigations
            WHERE id = %s
            """,
            (investigation_id,),
        )
        row = _fetchone_dict(cur)
    if row is None:
        raise LookupError("investigation not found")
    return row


def resolve_investigation_source_context(conn, investigation: dict[str, Any]) -> dict[str, Any]:
    context: dict[str, Any] = {
        "alert": None,
        "incident": None,
        "source_ip": investigation.get("linked_source_ip"),
        "partial": [],
    }
    with conn.cursor() as cur:
        alert_id = investigation.get("linked_alert_id")
        if alert_id is not None:
            cur.execute(
                """
                SELECT id, alert_type, severity, source, source_ip::TEXT AS source_ip,
                    message, status, created_at
                FROM alerts
                WHERE id = %s
                """,
                (alert_id,),
            )
            row = _fetchone_dict(cur)
            context["alert"] = _serialize_source_row(row) if row else None
            if row is None:
                context["partial"].append("linked alert unavailable")
        incident_id = investigation.get("linked_incident_id")
        if incident_id is not None:
            cur.execute(
                """
                SELECT id, title, severity, priority, status, source_ip::TEXT AS source_ip,
                    created_at, updated_at
                FROM incidents
                WHERE id = %s
                """,
                (incident_id,),
            )
            row = _fetchone_dict(cur)
            context["incident"] = _serialize_source_row(row) if row else None
            if row is None:
                context["partial"].append("linked incident unavailable")
    if not context["alert"] and not context["incident"] and not context["source_ip"]:
        context["partial"].append("no linked source context")
    return context


def build_investigation_timeline(
    investigation: dict[str, Any],
    *,
    notes: list[dict[str, Any]],
    hypotheses: list[dict[str, Any]],
    tasks: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    events = [
        {
            "id": f"investigation-created-{investigation.get('id')}",
            "kind": "analyst",
            "label": "Investigation created",
            "timestamp": investigation.get("created_at"),
            "detail": investigation.get("title"),
        }
    ]
    for item in evidence:
        events.append({
            "id": f"evidence-{item.get('id')}",
            "kind": "analyst",
            "label": "Evidence saved",
            "timestamp": item.get("created_at"),
            "detail": item.get("label"),
        })
    for hypothesis in hypotheses:
        events.append({
            "id": f"hypothesis-{hypothesis.get('id')}",
            "kind": "analyst",
            "label": "Hypothesis recorded",
            "timestamp": hypothesis.get("created_at"),
            "detail": hypothesis.get("title"),
        })
    for task in tasks:
        if task.get("status") == "done":
            events.append({
                "id": f"task-done-{task.get('id')}",
                "kind": "analyst",
                "label": "Task completed",
                "timestamp": task.get("updated_at"),
                "detail": task.get("title"),
            })
    for note in notes:
        events.append({
            "id": f"note-{note.get('id')}",
            "kind": "analyst",
            "label": "Analyst note",
            "timestamp": note.get("created_at"),
            "detail": note.get("body"),
        })
    if investigation.get("closed_at"):
        events.append({
            "id": f"investigation-closed-{investigation.get('id')}",
            "kind": "analyst",
            "label": "Investigation closed",
            "timestamp": investigation.get("closed_at"),
            "detail": investigation.get("conclusion") or investigation.get("disposition"),
        })
    return sorted(events, key=lambda item: item.get("timestamp") or "")


def _serialize_source_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {key: (_str_ts(value) if key.endswith("_at") else value) for key, value in row.items()}


def _parent_where(owner: str, workspace_id: int | None, investigation_id: int | None) -> tuple[str, tuple[Any, ...]]:
    if investigation_id is not None:
        return "owner_username = %s AND investigation_id = %s", (owner, investigation_id)
    if workspace_id is not None:
        return "owner_username = %s AND workspace_id = %s AND investigation_id IS NULL", (owner, workspace_id)
    return "owner_username = %s", (owner,)


def _serialize_workspace(row: dict[str, Any] | None) -> dict[str, Any]:
    row = row or {}
    return {
        "id": row.get("id"),
        "owner_username": row.get("owner_username"),
        "name": row.get("name"),
        "is_default": bool(row.get("is_default")),
        "visibility": row.get("visibility") or "private",
        "created_at": _str_ts(row.get("created_at")),
        "updated_at": _str_ts(row.get("updated_at")),
    }


def _serialize_item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "workspace_id": row.get("workspace_id"),
        "owner_username": row.get("owner_username"),
        "item_type": row.get("item_type"),
        "referenced_object_type": row.get("referenced_object_type"),
        "referenced_object_id": row.get("referenced_object_id"),
        "label": row.get("label"),
        "status": row.get("status"),
        "item_order": row.get("item_order"),
        "metadata": _json_or_empty(row.get("metadata")),
        "visibility": row.get("visibility") or "private",
        "created_at": _str_ts(row.get("created_at")),
        "updated_at": _str_ts(row.get("updated_at")),
    }


def _serialize_investigation(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "owner_username": row.get("owner_username"),
        "workspace_id": row.get("workspace_id"),
        "title": row.get("title"),
        "status": row.get("status"),
        "summary": row.get("summary"),
        "disposition": row.get("disposition") or "undetermined",
        "confidence": row.get("confidence") or "medium",
        "conclusion": row.get("conclusion"),
        "closed_at": _str_ts(row.get("closed_at")),
        "last_activity_at": _str_ts(row.get("last_activity_at")) or _str_ts(row.get("updated_at")),
        "linked_alert_id": row.get("linked_alert_id"),
        "linked_incident_id": row.get("linked_incident_id"),
        "linked_source_ip": row.get("linked_source_ip"),
        "visibility": row.get("visibility") or "private",
        "saved_state": _json_or_empty(row.get("saved_state")),
        "created_at": _str_ts(row.get("created_at")),
        "updated_at": _str_ts(row.get("updated_at")),
    }


def _serialize_note(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "owner_username": row.get("owner_username"),
        "workspace_id": row.get("workspace_id"),
        "investigation_id": row.get("investigation_id"),
        "body": row.get("body"),
        "created_at": _str_ts(row.get("created_at")),
        "updated_at": _str_ts(row.get("updated_at")),
    }


def _serialize_hypothesis(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "owner_username": row.get("owner_username"),
        "workspace_id": row.get("workspace_id"),
        "investigation_id": row.get("investigation_id"),
        "title": row.get("title"),
        "body": row.get("body"),
        "status": row.get("status"),
        "confidence": row.get("confidence") or "medium",
        "created_at": _str_ts(row.get("created_at")),
        "updated_at": _str_ts(row.get("updated_at")),
    }


def _serialize_task(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "owner_username": row.get("owner_username"),
        "workspace_id": row.get("workspace_id"),
        "investigation_id": row.get("investigation_id"),
        "title": row.get("title"),
        "status": row.get("status"),
        "hypothesis_id": row.get("hypothesis_id"),
        "evidence_reference_id": row.get("evidence_reference_id"),
        "created_at": _str_ts(row.get("created_at")),
        "updated_at": _str_ts(row.get("updated_at")),
    }


def _serialize_evidence(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "owner_username": row.get("owner_username"),
        "workspace_id": row.get("workspace_id"),
        "investigation_id": row.get("investigation_id"),
        "parent_type": row.get("parent_type"),
        "referenced_object_type": row.get("referenced_object_type"),
        "referenced_object_id": row.get("referenced_object_id"),
        "label": row.get("label"),
        "source": row.get("source"),
        "metadata": _json_or_empty(row.get("metadata")),
        "rationale": row.get("rationale"),
        "relationship_type": row.get("relationship_type") or "context",
        "created_at": _str_ts(row.get("created_at")),
        "updated_at": _str_ts(row.get("updated_at")),
    }


def _serialize_hypothesis_evidence_link(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "owner_username": row.get("owner_username"),
        "investigation_id": row.get("investigation_id"),
        "hypothesis_id": row.get("hypothesis_id"),
        "evidence_reference_id": row.get("evidence_reference_id"),
        "relationship_type": row.get("relationship_type") or "context",
        "rationale": row.get("rationale"),
        "created_at": _str_ts(row.get("created_at")),
        "updated_at": _str_ts(row.get("updated_at")),
    }


def _str_ts(value: Any) -> str | None:
    return str(value) if value is not None else None
