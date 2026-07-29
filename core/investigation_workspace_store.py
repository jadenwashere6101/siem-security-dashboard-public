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
VALID_INVESTIGATION_STATUSES = {"open", "investigating", "waiting", "resolved", "closed"}

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
    }:
        raise ValueError("unsupported table")
    owner = _ensure_owner(owner_username)
    with conn.cursor() as cur:
        cur.execute(f"SELECT owner_username FROM {table} WHERE id = %s", (record_id,))
        row = cur.fetchone()
        if row is None:
            raise LookupError("record not found")
        row_owner = row[0] if not isinstance(row, dict) else row["owner_username"]
        if row_owner != owner:
            raise WorkspaceOwnershipError("record access denied")
        cur.execute(f"DELETE FROM {table} WHERE id = %s AND owner_username = %s", (record_id, owner))
        return cur.rowcount > 0


UPDATE_COLUMNS_BY_TABLE = {
    "workspace_items": {"label", "status", "item_order", "metadata"},
    "investigations": {"title", "status", "summary", "saved_state"},
    "investigation_notes": {"body"},
    "investigation_hypotheses": {"title", "body", "status"},
    "investigation_tasks": {"title", "status"},
    "evidence_references": {"label", "source", "metadata"},
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
        cur.execute(f"SELECT owner_username FROM {table} WHERE id = %s", (record_id,))
        row = cur.fetchone()
        if row is None:
            raise LookupError("record not found")
        row_owner = row[0] if not isinstance(row, dict) else row["owner_username"]
        if row_owner != owner:
            raise WorkspaceOwnershipError("record access denied")
        assignments = [f"{column} = %s" for column in clean_updates]
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
    if key in {"title", "label"}:
        return _clean_text(value, field_name=key, max_length=MAX_TITLE_LENGTH)
    if key == "body":
        return _clean_text(value, field_name=key)
    if key == "summary":
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
) -> dict[str, Any]:
    owner = _ensure_owner(owner_username)
    if workspace_id is not None:
        get_workspace(conn, workspace_id, owner)
    title_value = _clean_text(title, field_name="title", max_length=MAX_TITLE_LENGTH)
    if status not in VALID_INVESTIGATION_STATUSES:
        raise ValueError("unsupported investigation status")
    if linked_alert_id is not None:
        validate_reference(conn, "alert", str(linked_alert_id))
    if linked_incident_id is not None:
        validate_reference(conn, "incident", str(linked_incident_id))
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO investigations (
                owner_username, workspace_id, title, status, summary,
                linked_alert_id, linked_incident_id, linked_source_ip, saved_state, visibility
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'private')
            RETURNING id, owner_username, workspace_id, title, status, summary,
                linked_alert_id, linked_incident_id, linked_source_ip::TEXT AS linked_source_ip,
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
                visibility, saved_state, created_at, updated_at
            FROM investigations
            WHERE owner_username = %s
            ORDER BY updated_at DESC, id DESC
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
) -> dict[str, Any]:
    owner = _ensure_owner(owner_username)
    workspace_id, investigation_id = _validate_parent(conn, owner, workspace_id, investigation_id)
    if status not in VALID_HYPOTHESIS_STATUSES:
        raise ValueError("unsupported hypothesis status")
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO investigation_hypotheses (owner_username, workspace_id, investigation_id, title, body, status)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id, owner_username, workspace_id, investigation_id, title, body, status, created_at, updated_at
            """,
            (owner, workspace_id, investigation_id, _clean_text(title, field_name="title", max_length=MAX_TITLE_LENGTH), _optional_text(body), status),
        )
        return _serialize_hypothesis(_fetchone_dict(cur))


def list_hypotheses(conn, owner_username: str, *, workspace_id: int | None = None, investigation_id: int | None = None) -> list[dict[str, Any]]:
    owner = _ensure_owner(owner_username)
    where, params = _parent_where(owner, workspace_id, investigation_id)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT id, owner_username, workspace_id, investigation_id, title, body, status, created_at, updated_at
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
) -> dict[str, Any]:
    owner = _ensure_owner(owner_username)
    workspace_id, investigation_id = _validate_parent(conn, owner, workspace_id, investigation_id)
    if status not in VALID_TASK_STATUSES:
        raise ValueError("unsupported task status")
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO investigation_tasks (owner_username, workspace_id, investigation_id, title, status)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, owner_username, workspace_id, investigation_id, title, status, created_at, updated_at
            """,
            (owner, workspace_id, investigation_id, _clean_text(title, field_name="title", max_length=MAX_TITLE_LENGTH), status),
        )
        return _serialize_task(_fetchone_dict(cur))


def list_tasks(conn, owner_username: str, *, workspace_id: int | None = None, investigation_id: int | None = None) -> list[dict[str, Any]]:
    owner = _ensure_owner(owner_username)
    where, params = _parent_where(owner, workspace_id, investigation_id)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT id, owner_username, workspace_id, investigation_id, title, status, created_at, updated_at
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
) -> dict[str, Any]:
    owner = _ensure_owner(owner_username)
    workspace_id, investigation_id = _validate_parent(conn, owner, workspace_id, investigation_id)
    parent_type = "investigation" if investigation_id is not None else "workspace"
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO evidence_references (
                owner_username, workspace_id, investigation_id, parent_type,
                referenced_object_type, referenced_object_id, label, source, metadata
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, owner_username, workspace_id, investigation_id, parent_type,
                referenced_object_type, referenced_object_id, label, source, metadata,
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
            ),
        )
        return _serialize_evidence(_fetchone_dict(cur))


def list_evidence(conn, owner_username: str, *, workspace_id: int | None = None, investigation_id: int | None = None) -> list[dict[str, Any]]:
    owner = _ensure_owner(owner_username)
    where, params = _parent_where(owner, workspace_id, investigation_id)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT id, owner_username, workspace_id, investigation_id, parent_type,
                referenced_object_type, referenced_object_id, label, source, metadata,
                created_at, updated_at
            FROM evidence_references
            WHERE {where}
            ORDER BY created_at DESC
            """,
            params,
        )
        return [_serialize_evidence(row) for row in _fetchall_dicts(cur)]


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


def _get_investigation(conn, investigation_id: int) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, owner_username, workspace_id, title, status, summary,
                linked_alert_id, linked_incident_id, linked_source_ip::TEXT AS linked_source_ip,
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
        "created_at": _str_ts(row.get("created_at")),
        "updated_at": _str_ts(row.get("updated_at")),
    }


def _str_ts(value: Any) -> str | None:
    return str(value) if value is not None else None
