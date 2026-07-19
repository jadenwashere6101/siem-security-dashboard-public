from __future__ import annotations

from typing import Any


MAX_NOTE_LENGTH = 2000


def validate_note_text(value: Any, *, field_name: str = "note_text") -> str:
    note_text = str(value or "").strip()
    if not note_text:
        raise ValueError(f"{field_name} is required")
    if len(note_text) > MAX_NOTE_LENGTH:
        raise ValueError(f"{field_name} must be {MAX_NOTE_LENGTH} characters or fewer")
    return note_text


def _note_row_to_dict(row: tuple[Any, ...], *, target_field: str) -> dict[str, Any]:
    return {
        "id": row[0],
        target_field: row[1],
        "author": row[2],
        "note_text": row[3],
        "created_at": str(row[4]),
    }


def list_alert_notes(conn, alert_id: int) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, alert_id, author, note_text, created_at
            FROM alert_notes
            WHERE alert_id = %s
            ORDER BY created_at DESC
            """,
            (alert_id,),
        )
        return [_note_row_to_dict(row, target_field="alert_id") for row in cur.fetchall()]


def create_alert_note(conn, *, alert_id: int, author: str, note_text: str) -> dict[str, Any]:
    note_text = validate_note_text(note_text)
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM alerts WHERE id = %s", (alert_id,))
        if not cur.fetchone():
            raise LookupError("alert not found")

        cur.execute(
            """
            INSERT INTO alert_notes (alert_id, author, note_text)
            VALUES (%s, %s, %s)
            RETURNING id, alert_id, author, note_text, created_at
            """,
            (alert_id, author, note_text),
        )
        return _note_row_to_dict(cur.fetchone(), target_field="alert_id")


def list_incident_notes(conn, incident_id: int) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, incident_id, author, note_text, created_at
            FROM incident_notes
            WHERE incident_id = %s
            ORDER BY created_at DESC
            """,
            (incident_id,),
        )
        return [_note_row_to_dict(row, target_field="incident_id") for row in cur.fetchall()]


def create_incident_note(conn, *, incident_id: int, author: str, note_text: str) -> dict[str, Any]:
    note_text = validate_note_text(note_text)
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM incidents WHERE id = %s", (incident_id,))
        if not cur.fetchone():
            raise LookupError("incident not found")

        cur.execute(
            """
            INSERT INTO incident_notes (incident_id, author, note_text)
            VALUES (%s, %s, %s)
            RETURNING id, incident_id, author, note_text, created_at
            """,
            (incident_id, author, note_text),
        )
        return _note_row_to_dict(cur.fetchone(), target_field="incident_id")
