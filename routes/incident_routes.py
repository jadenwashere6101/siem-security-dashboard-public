from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_required

from core.audit_helpers import log_audit_event
from core.auth import analyst_or_super_admin_required
from core.db import get_db_connection
from core.incident_store import (
    ALL_INCIDENT_STATUSES,
    get_incident_detail,
    list_incidents,
    update_incident_status,
)
from core.soar_response_outcomes import (
    get_latest_outcomes_for_incidents_bulk,
    serialize_incident_outcome_timeline_entries,
)


incident_bp = Blueprint("incidents", __name__)

VALID_SEVERITIES = frozenset({"LOW", "MEDIUM", "HIGH", "CRITICAL"})
DEFAULT_LIMIT = 50
MAX_LIMIT = 100

_TIE_INCIDENT = 0
_TIE_ALERT = 1
_TIE_EXECUTION = 2
_TIE_STEP = 3
_TIE_APPROVAL_REQUEST = 4
_TIE_APPROVAL_EVENT = 5
_TIE_AUDIT = 6

_MISSING_SORT = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _iso_z(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_iso_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _step_output_metadata(output: Any) -> dict[str, Any]:
    if not isinstance(output, dict):
        return {}
    meta: dict[str, Any] = {
        "simulated": output.get("simulated"),
        "executed": output.get("executed"),
    }
    if "circuit_breaker" in output:
        meta["circuit_breaker"] = output.get("circuit_breaker")
    ar = output.get("adapter_result")
    if isinstance(ar, dict):
        meta["adapter"] = ar.get("adapter")
        meta["adapter_action"] = ar.get("action")
        meta["adapter_success"] = ar.get("success")
    return {k: v for k, v in meta.items() if v is not None}


def _map_step_event_type(entry: dict[str, Any]) -> str:
    ev = entry.get("event")
    if isinstance(ev, str) and ev:
        mapping = {
            "approval_requested": "approval_requested",
            "approval_approved": "approval_approved",
            "approval_denied": "approval_denied",
            "approval_expired": "approval_expired",
            "approval_resumed": "approval_resumed",
        }
        if ev in mapping:
            return mapping[ev]
    status = str(entry.get("status") or "").lower()
    if status == "skipped":
        return "playbook_step_skipped"
    if status == "failed":
        return "playbook_step_failed"
    out = entry.get("output")
    if isinstance(out, dict) and isinstance(out.get("adapter_result"), dict):
        ar = out["adapter_result"]
        if ar.get("success") is True:
            mode = str(
                entry.get("mode") or out.get("adapter_mode") or ar.get("mode") or ""
            ).strip().lower()
            executed = entry.get("executed")
            if executed is None:
                executed = out.get("executed")
            if mode == "real" and executed is True:
                return "playbook_adapter_real"
            return "playbook_adapter_simulated"
        return "playbook_step_failed"
    if status == "success":
        return "playbook_step_completed"
    return "playbook_step_event"


def _append_step_entries(
    entries: list[dict[str, Any]],
    *,
    execution_id: int,
    playbook_id: str,
    incident_id: int,
    steps_log: Any,
) -> None:
    if not isinstance(steps_log, list):
        return
    for raw in steps_log:
        if not isinstance(raw, dict):
            continue
        idx = raw.get("step_index")
        try:
            idx_int = int(idx) if idx is not None else -1
        except (TypeError, ValueError):
            idx_int = -1
        action = raw.get("action")
        action_s = str(action) if action is not None else ""
        started = _parse_iso_datetime(raw.get("started_at"))
        completed = _parse_iso_datetime(raw.get("completed_at"))
        sort_ts = started or completed or _MISSING_SORT
        subkey = f"{idx_int:06d}:{action_s}"
        event_type = _map_step_event_type(raw)
        summary = str(raw.get("message") or "").strip() or f"{action_s or 'step'} ({event_type})"
        title = f"Playbook step {idx_int}" if idx_int >= 0 else "Playbook step"
        sev = "error" if str(raw.get("status") or "").lower() == "failed" else "info"
        meta: dict[str, Any] = {
            "incident_id": incident_id,
            "playbook_id": playbook_id,
            "execution_id": execution_id,
            "step_index": idx_int if idx_int >= 0 else None,
            "status": raw.get("status"),
            "mode": raw.get("mode"),
        }
        mo = _step_output_metadata(raw.get("output"))
        if mo:
            meta["output"] = mo
        if raw.get("approval_request_id") is not None:
            meta["approval_request_id"] = raw.get("approval_request_id")
        ts_str = _iso_z(sort_ts if sort_ts != _MISSING_SORT else None) or _iso_z(completed) or _iso_z(started)
        entries.append(
            {
                "timestamp": ts_str,
                "event_type": event_type,
                "source": "playbook_execution",
                "source_id": execution_id,
                "title": title,
                "summary": summary[:2000],
                "severity": sev,
                "metadata": {k: v for k, v in meta.items() if v is not None},
                "_sort_ts": sort_ts,
                "_tie": _TIE_STEP,
                "_subkey": subkey,
            }
        )


def _approval_event_type(db_event_type: str) -> str:
    return {
        "created": "approval_requested",
        "approved": "approval_approved",
        "denied": "approval_denied",
        "expired": "approval_expired",
    }.get(db_event_type, "approval_event")


def _audit_row_matches_scope(
    *,
    target_alert_id: Any,
    details: Any,
    incident_id: int,
    linked_set: set[int],
    execution_ids: set[int],
    approval_ids: set[int],
) -> bool:
    aid = _safe_int(target_alert_id)
    if aid is not None and aid in linked_set:
        return True
    if not isinstance(details, dict):
        return False
    if _safe_int(details.get("incident_id")) == incident_id:
        return True
    for key in ("execution_id", "new_execution_id", "source_execution_id"):
        eid = _safe_int(details.get(key))
        if eid is not None and eid in execution_ids:
            return True
    rid = _safe_int(details.get("approval_request_id"))
    if rid is not None and rid in approval_ids:
        return True
    return False


def build_readonly_incident_timeline(conn, incident_id: int) -> dict[str, Any] | None:
    """
    Aggregate read-only SOAR timeline rows for an incident. Does not mutate data.
    """
    detail = get_incident_detail(conn, incident_id)
    if detail is None:
        return None

    entries: list[dict[str, Any]] = []
    linked_alerts = detail.get("alerts") or []
    linked_ids: list[int] = []
    linked_set: set[int] = set()
    for a in linked_alerts:
        aid = _safe_int(a.get("alert_id"))
        if aid is not None:
            linked_ids.append(aid)
            linked_set.add(aid)

    created_inc = _parse_iso_datetime(detail.get("created_at"))
    if created_inc:
        entries.append(
            {
                "timestamp": _iso_z(created_inc),
                "event_type": "incident_created",
                "source": "incident",
                "source_id": incident_id,
                "title": "Incident created",
                "summary": f"Incident {incident_id} opened ({detail.get('status', '')})",
                "severity": "info",
                "metadata": {
                    "incident_id": incident_id,
                    "status": detail.get("status"),
                    "severity": detail.get("severity"),
                    "assigned_to": detail.get("assigned_to"),
                },
                "_sort_ts": created_inc,
                "_tie": _TIE_INCIDENT,
                "_subkey": "created",
            }
        )

    resolved = _parse_iso_datetime(detail.get("resolved_at"))
    if resolved:
        entries.append(
            {
                "timestamp": _iso_z(resolved),
                "event_type": "incident_resolved",
                "source": "incident",
                "source_id": incident_id,
                "title": "Incident resolved timestamp",
                "summary": f"Incident {incident_id} has resolved_at set",
                "severity": "info",
                "metadata": {"incident_id": incident_id, "status": detail.get("status")},
                "_sort_ts": resolved,
                "_tie": _TIE_INCIDENT,
                "_subkey": "resolved",
            }
        )

    for a in linked_alerts:
        aid = _safe_int(a.get("alert_id"))
        if aid is None:
            continue
        ac = _parse_iso_datetime(a.get("created_at"))
        if ac:
            entries.append(
                {
                    "timestamp": _iso_z(ac),
                    "event_type": "alert_created",
                    "source": "alert",
                    "source_id": aid,
                    "title": "Alert created",
                    "summary": f"{a.get('alert_type') or 'alert'} ({a.get('severity') or ''})",
                    "severity": "info",
                    "metadata": {
                        "incident_id": incident_id,
                        "alert_id": aid,
                        "alert_type": a.get("alert_type"),
                        "severity": a.get("severity"),
                    },
                    "_sort_ts": ac,
                    "_tie": _TIE_ALERT,
                    "_subkey": f"alert_created:{aid}",
                }
            )
        lk = _parse_iso_datetime(a.get("linked_at"))
        if lk:
            entries.append(
                {
                    "timestamp": _iso_z(lk),
                    "event_type": "alert_linked",
                    "source": "incident_alerts",
                    "source_id": aid,
                    "title": "Alert linked to incident",
                    "summary": f"Alert {aid} linked to incident {incident_id}",
                    "severity": "info",
                    "metadata": {"incident_id": incident_id, "alert_id": aid},
                    "_sort_ts": lk,
                    "_tie": _TIE_ALERT,
                    "_subkey": f"alert_linked:{aid}",
                }
            )

    executions: dict[int, tuple[Any, ...]] = {}
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, playbook_id, alert_id, incident_id, status, started_at, completed_at,
                   last_completed_step, steps_log, created_at, failure_reason
            FROM playbook_executions
            WHERE incident_id = %s
            """,
            (incident_id,),
        )
        for row in cur.fetchall():
            executions[row[0]] = row
        if linked_ids:
            cur.execute(
                """
                SELECT id, playbook_id, alert_id, incident_id, status, started_at, completed_at,
                       last_completed_step, steps_log, created_at, failure_reason
                FROM playbook_executions
                WHERE incident_id IS NULL AND alert_id = ANY(%s)
                """,
                (linked_ids,),
            )
            for row in cur.fetchall():
                executions.setdefault(row[0], row)

    execution_ids_set = set(executions.keys())

    for eid, row in sorted(executions.items()):
        (
            _pk,
            playbook_id,
            alert_id,
            row_incident_id,
            status,
            started_at,
            completed_at,
            last_completed_step,
            steps_log,
            created_at,
            failure_reason,
        ) = row
        via_alert_fallback = row_incident_id is None and alert_id is not None
        base_meta: dict[str, Any] = {
            "incident_id": incident_id,
            "playbook_id": playbook_id,
            "execution_id": eid,
            "alert_id": alert_id,
            "via_alert_fallback": via_alert_fallback,
        }
        cr = _parse_iso_datetime(created_at)
        if cr:
            entries.append(
                {
                    "timestamp": _iso_z(cr),
                    "event_type": "playbook_execution_created",
                    "source": "playbook_execution",
                    "source_id": eid,
                    "title": "Playbook execution created",
                    "summary": f"Execution {eid} for playbook {playbook_id}",
                    "severity": "info",
                    "metadata": {**base_meta, "status": status},
                    "_sort_ts": cr,
                    "_tie": _TIE_EXECUTION,
                    "_subkey": f"{eid}:created",
                }
            )
        st_at = _parse_iso_datetime(started_at)
        if st_at:
            entries.append(
                {
                    "timestamp": _iso_z(st_at),
                    "event_type": "playbook_execution_started",
                    "source": "playbook_execution",
                    "source_id": eid,
                    "title": "Playbook execution started",
                    "summary": f"Execution {eid} started",
                    "severity": "info",
                    "metadata": base_meta,
                    "_sort_ts": st_at,
                    "_tie": _TIE_EXECUTION,
                    "_subkey": f"{eid}:started",
                }
            )
        _append_step_entries(
            entries,
            execution_id=eid,
            playbook_id=str(playbook_id),
            incident_id=incident_id,
            steps_log=steps_log,
        )
        comp_at = _parse_iso_datetime(completed_at)
        term_statuses = {"success", "failed", "abandoned", "permanently_failed", "not_actioned"}
        st_lower = str(status or "").lower()
        if st_lower in term_statuses:
            sort_ts = comp_at or cr or _MISSING_SORT
            entries.append(
                {
                    "timestamp": _iso_z(comp_at) if comp_at else _iso_z(cr),
                    "event_type": "playbook_execution_status_changed",
                    "source": "playbook_execution",
                    "source_id": eid,
                    "title": "Playbook execution status",
                    "summary": f"Execution {eid} status={status}"
                    + (f"; last_step={last_completed_step}" if last_completed_step is not None else "")
                    + (f"; {failure_reason}" if failure_reason else ""),
                    "severity": "error" if st_lower in {"failed", "permanently_failed"} else "info",
                    "metadata": {
                        **base_meta,
                        "status": status,
                        "last_completed_step": last_completed_step,
                    },
                    "_sort_ts": sort_ts,
                    "_tie": _TIE_EXECUTION,
                    "_subkey": f"{eid}:terminal",
                }
            )

    approval_ids: set[int] = set()
    with conn.cursor() as cur:
        if execution_ids_set:
            cur.execute(
                """
                SELECT id, playbook_execution_id, playbook_step_index, status, action,
                       request_reason, created_at, decided_at, risk_level
                FROM approval_requests
                WHERE incident_id = %s OR playbook_execution_id = ANY(%s)
                """,
                (incident_id, list(execution_ids_set)),
            )
        else:
            cur.execute(
                """
                SELECT id, playbook_execution_id, playbook_step_index, status, action,
                       request_reason, created_at, decided_at, risk_level
                FROM approval_requests
                WHERE incident_id = %s
                """,
                (incident_id,),
            )
        approval_rows = cur.fetchall()
        for arow in approval_rows:
            approval_ids.add(int(arow[0]))
        for arow in approval_rows:
            rid, pex_id, step_ix, st, action, reason, crt, dec_at, risk = arow
            cat = _parse_iso_datetime(crt)
            if cat:
                entries.append(
                    {
                        "timestamp": _iso_z(cat),
                        "event_type": "approval_requested",
                        "source": "approval_request",
                        "source_id": int(rid),
                        "title": "Approval request",
                        "summary": str(reason or action or "approval").strip()[:2000],
                        "severity": "info",
                        "metadata": {
                            "incident_id": incident_id,
                            "approval_request_id": int(rid),
                            "playbook_execution_id": pex_id,
                            "playbook_step_index": step_ix,
                            "status": st,
                            "action": action,
                            "risk_level": risk,
                        },
                        "_sort_ts": cat,
                        "_tie": _TIE_APPROVAL_REQUEST,
                        "_subkey": f"ar:{rid}:open",
                    }
                )
            dat = _parse_iso_datetime(dec_at)
            if dat and str(st or "").lower() != "pending":
                entries.append(
                    {
                        "timestamp": _iso_z(dat),
                        "event_type": f"approval_{st}",
                        "source": "approval_request",
                        "source_id": int(rid),
                        "title": f"Approval {st}",
                        "summary": f"Approval {rid} marked {st}",
                        "severity": "warning" if st == "denied" else "info",
                        "metadata": {
                            "incident_id": incident_id,
                            "approval_request_id": int(rid),
                            "playbook_execution_id": pex_id,
                            "playbook_step_index": step_ix,
                            "status": st,
                        },
                        "_sort_ts": dat,
                        "_tie": _TIE_APPROVAL_REQUEST,
                        "_subkey": f"ar:{rid}:decided",
                    }
                )

        event_rows: list[tuple[Any, ...]] = []
        if approval_ids:
            cur.execute(
                """
                SELECT id, approval_request_id, event_type, created_at, previous_status, new_status, comment
                FROM approval_request_events
                WHERE approval_request_id = ANY(%s)
                ORDER BY created_at ASC, id ASC
                """,
                (list(approval_ids),),
            )
            event_rows = cur.fetchall()
        for ev in event_rows:
            evid, arid, etype, ect, prev_s, new_s, comment = ev
            ect_p = _parse_iso_datetime(ect)
            if not ect_p:
                continue
            entries.append(
                {
                    "timestamp": _iso_z(ect_p),
                    "event_type": _approval_event_type(str(etype)),
                    "source": "approval_request_event",
                    "source_id": int(evid),
                    "title": f"Approval event ({etype})",
                    "summary": str(comment or f"{prev_s} -> {new_s}")[:2000],
                    "severity": "info",
                    "metadata": {
                        "incident_id": incident_id,
                        "approval_request_id": int(arid),
                        "previous_status": prev_s,
                        "new_status": new_s,
                    },
                    "_sort_ts": ect_p,
                    "_tie": _TIE_APPROVAL_EVENT,
                    "_subkey": f"arev:{evid}",
                }
            )

        audit_parts: list[str] = []
        audit_params: list[Any] = []
        if linked_ids:
            audit_parts.append("target_alert_id = ANY(%s)")
            audit_params.append(linked_ids)
        audit_parts.append(
            "(details IS NOT NULL AND details ? 'incident_id' AND details->>'incident_id' = %s)"
        )
        audit_params.append(str(incident_id))
        if execution_ids_set:
            for key in ("execution_id", "new_execution_id", "source_execution_id"):
                audit_parts.append(
                    f"(details IS NOT NULL AND details ? '{key}' "
                    f"AND (details->>'{key}')::int = ANY(%s))"
                )
                audit_params.append(list(execution_ids_set))
        if approval_ids:
            audit_parts.append(
                "(details IS NOT NULL AND details ? 'approval_request_id' "
                "AND (details->>'approval_request_id')::int = ANY(%s))"
            )
            audit_params.append(list(approval_ids))

        where_sql = " OR ".join(f"({p})" for p in audit_parts)
        cur.execute(
            f"""
            SELECT id, event_type, actor_username, details, target_alert_id, created_at
            FROM audit_log
            WHERE {where_sql}
            ORDER BY created_at ASC, id ASC
            """,
            audit_params,
        )
        for arow in cur.fetchall():
            alid, et, actor, details, talert, actime = arow
            if not _audit_row_matches_scope(
                target_alert_id=talert,
                details=details,
                incident_id=incident_id,
                linked_set=linked_set,
                execution_ids=execution_ids_set,
                approval_ids=approval_ids,
            ):
                continue
            ats = _parse_iso_datetime(actime)
            if not ats:
                continue
            entries.append(
                {
                    "timestamp": _iso_z(ats),
                    "event_type": "audit_event",
                    "source": "audit_log",
                    "source_id": int(alid),
                    "title": str(et or "audit"),
                    "summary": f"{et or 'audit_event'} by {actor or 'unknown'}",
                    "severity": "info",
                    "metadata": {
                        "incident_id": incident_id,
                        "audit_id": int(alid),
                        "audit_event_type": et,
                        "actor_username": actor,
                    },
                    "_sort_ts": ats,
                    "_tie": _TIE_AUDIT,
                    "_subkey": f"audit:{alid}",
                }
            )

    entries.sort(key=lambda e: (e["_sort_ts"], e["_tie"], e["_subkey"]))
    for e in entries:
        e.pop("_sort_ts", None)
        e.pop("_tie", None)
        e.pop("_subkey", None)

    return {"incident_id": incident_id, "timeline": entries}


def _parse_non_negative_int(value, default, field_name):
    if value is None:
        return default, None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None, f"invalid {field_name}"
    if parsed < 0:
        return None, f"invalid {field_name}"
    return parsed, None


@incident_bp.route("/incidents", methods=["GET"])
@login_required
@analyst_or_super_admin_required
def list_incidents_route():
    conn = None
    try:
        status = request.args.get("status")
        severity = request.args.get("severity")

        if status is not None and status not in ALL_INCIDENT_STATUSES:
            return jsonify({"error": "invalid status filter"}), 400

        if severity is not None:
            severity = severity.upper()
            if severity not in VALID_SEVERITIES:
                return jsonify({"error": "invalid severity filter"}), 400

        limit, limit_error = _parse_non_negative_int(
            request.args.get("limit"),
            DEFAULT_LIMIT,
            "limit",
        )
        if limit_error:
            return jsonify({"error": limit_error}), 400
        limit = min(limit, MAX_LIMIT)

        offset, offset_error = _parse_non_negative_int(
            request.args.get("offset"),
            0,
            "offset",
        )
        if offset_error:
            return jsonify({"error": offset_error}), 400

        conn = get_db_connection()
        incidents = list_incidents(
            conn,
            status=status,
            severity=severity,
            limit=limit,
            offset=offset,
        )
        response_outcomes = get_latest_outcomes_for_incidents_bulk(
            conn,
            [incident["id"] for incident in incidents],
        )
        for incident in incidents:
            incident["response_outcome"] = response_outcomes.get(incident["id"])
        return jsonify({"incidents": incidents, "count": len(incidents)}), 200
    except Exception as error:
        current_app.logger.error("Error in list_incidents_route: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()


@incident_bp.route("/incidents/<int:incident_id>", methods=["GET"])
@login_required
@analyst_or_super_admin_required
def get_incident_route(incident_id):
    conn = None
    try:
        conn = get_db_connection()
        incident = get_incident_detail(conn, incident_id)
        if incident is None:
            return jsonify({"error": "incident not found"}), 404
        incident["response_outcome"] = get_latest_outcomes_for_incidents_bulk(
            conn,
            [incident_id],
        ).get(incident_id)
        return jsonify({"incident": incident}), 200
    except Exception as error:
        current_app.logger.error("Error in get_incident_route: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()


@incident_bp.route("/incidents/<int:incident_id>/timeline", methods=["GET"])
@login_required
@analyst_or_super_admin_required
def get_incident_timeline_route(incident_id):
    conn = None
    try:
        conn = get_db_connection()
        payload = build_readonly_incident_timeline(conn, incident_id)
        if payload is None:
            return jsonify({"error": "incident not found"}), 404
        outcome_entries = serialize_incident_outcome_timeline_entries(conn, incident_id)
        if outcome_entries:
            payload["timeline"].extend(outcome_entries)
            payload["timeline"].sort(key=lambda entry: entry.get("timestamp") or "")
        return jsonify(payload), 200
    except Exception as error:
        current_app.logger.error("Error in get_incident_timeline_route: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()


@incident_bp.route("/incidents/<int:incident_id>/status", methods=["POST"])
@login_required
@analyst_or_super_admin_required
def update_incident_status_route(incident_id):
    conn = None
    try:
        data = request.get_json(silent=True) or {}
        new_status = data.get("status")

        if not new_status:
            return jsonify({"error": "status is required"}), 400

        if new_status not in ALL_INCIDENT_STATUSES:
            return jsonify({"error": "invalid status"}), 400

        conn = get_db_connection()
        actor_username = getattr(current_user, "username", None) or current_user.id
        incident = update_incident_status(conn, incident_id, new_status, actor_username)
        conn.commit()

        log_audit_event(
            "UPDATE_INCIDENT_STATUS",
            actor_username=current_user.id,
            actor_role=current_user.role,
            http_method=request.method,
            request_path=request.path,
            source_ip=request.remote_addr,
            details={"incident_id": incident_id, "status": new_status},
        )

        return jsonify({"incident": incident}), 200
    except ValueError as error:
        if conn:
            conn.rollback()
        message = str(error)
        if message == "incident not found":
            return jsonify({"error": "incident not found"}), 404
        return jsonify({"error": message}), 400
    except Exception as error:
        if conn:
            conn.rollback()
        current_app.logger.error("Error in update_incident_status_route: %s", error)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()
