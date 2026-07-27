from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import patch

from psycopg2.extras import Json
from werkzeug.security import generate_password_hash

from core.ai import soc_briefing_history_store

ADMIN_USER = "testadmin"
ADMIN_PASS = "testpassword123!"


class _RouteSafeConnection:
    def __init__(self, conn):
        self._conn = conn

    def cursor(self, *args, **kwargs):
        return self._conn.cursor(*args, **kwargs)

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def close(self):
        return None


@contextmanager
def _patched_db(conn):
    wrapper = _RouteSafeConnection(conn)
    with patch("routes.soc_briefing_routes.get_db_connection", return_value=wrapper), patch(
        "core.audit_helpers.get_db_connection", return_value=wrapper
    ):
        yield


def _login_super_admin(client):
    resp = client.post("/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
    assert resp.status_code == 200


def _fake_user(username, password, role):
    return {
        "username": username,
        "password_hash": generate_password_hash(password, method="pbkdf2:sha256"),
        "role": role,
        "is_active": True,
    }


def _login_role(client, username, password, role):
    fake = _fake_user(username, password, role)
    return patch("routes.auth_routes.get_user_by_username", return_value=fake), patch(
        "core.auth.get_user_by_username", return_value=fake
    )


def _insert_briefing(conn, *, summary="Critical auth anomaly reviewed.", content_status="ready", status="success", sections=None):
    sections = sections or {
        "alerts_reviewed": ["Alert #1001 reviewed"],
        "dismissed_low_priority_findings": ["One known scanner event dismissed"],
        "escalations": ["Escalate auth anomaly for analyst review"],
        "critical_findings": ["Repeated admin login failures"],
        "evidence": ["Evidence reference ev-1"],
        "recommendations": ["Review source IP reputation"],
    }
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO soc_briefing_schedules (name, enabled, next_due_at)
            VALUES ('Morning SOC briefing', TRUE, %s)
            RETURNING id
            """,
            (datetime(2026, 7, 27, 8, 0, tzinfo=timezone.utc),),
        )
        schedule_id = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO soc_briefing_schedule_windows (
                schedule_id,
                window_start,
                window_end,
                idempotency_key,
                status
            )
            VALUES (%s, %s, %s, %s, 'success')
            RETURNING id
            """,
            (
                schedule_id,
                datetime(2026, 7, 27, 7, 0, tzinfo=timezone.utc),
                datetime(2026, 7, 27, 8, 0, tzinfo=timezone.utc),
                f"window-{schedule_id}",
            ),
        )
        window_id = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO soc_briefing_jobs (schedule_id, window_id, idempotency_key, status)
            VALUES (%s, %s, %s, 'success')
            RETURNING id
            """,
            (schedule_id, window_id, f"job-{schedule_id}"),
        )
        job_id = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO soc_briefing_runs (
                job_id,
                schedule_id,
                window_id,
                run_key,
                status,
                ai_gateway_status,
                provider_status,
                completed_at
            )
            VALUES (%s, %s, %s, %s, %s, 'success', 'local', %s)
            RETURNING id
            """,
            (
                job_id,
                schedule_id,
                window_id,
                f"run-{schedule_id}",
                status,
                datetime(2026, 7, 27, 8, 1, tzinfo=timezone.utc),
            ),
        )
        run_id = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO soc_briefing_run_steps (
                run_id,
                step_index,
                step_type,
                status,
                tool_name,
                sanitized_input,
                evidence_refs,
                decision_summary
            )
            VALUES (%s, 1, 'soc_tool', 'success', 'list_recent_alerts', %s, %s, 'Collected bounded alert evidence.')
            """,
            (run_id, Json({"limit": 10}), Json(["alert:1001"])),
        )
        cur.execute(
            """
            INSERT INTO soc_briefings (
                run_id,
                schedule_id,
                window_id,
                status,
                lifecycle_status,
                generated_at,
                content_status,
                summary,
                sections,
                evidence_refs
            )
            VALUES (%s, %s, %s, %s, 'content_ready', %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                run_id,
                schedule_id,
                window_id,
                status,
                datetime(2026, 7, 27, 8, 2, tzinfo=timezone.utc),
                content_status,
                summary,
                Json(sections),
                Json(["alert:1001"]),
            ),
        )
        briefing_id = cur.fetchone()[0]
    conn.commit()
    return {
        "briefing_id": briefing_id,
        "run_id": run_id,
        "schedule_id": schedule_id,
        "window_id": window_id,
    }


def test_briefing_history_requires_login(client):
    assert client.get("/soc-briefings").status_code == 401


def test_briefing_history_viewer_forbidden(client, mock_db):
    p1, p2 = _login_role(client, "brief_viewer", "vpass", "viewer")
    with p1, p2:
        assert client.post("/login", json={"username": "brief_viewer", "password": "vpass"}).status_code == 200
        assert client.get("/soc-briefings").status_code == 403
        assert client.get("/soc-briefings/1").status_code == 403
        assert client.post("/soc-briefings/1/deliveries/slack/retry").status_code == 403


def test_list_detail_filters_pagination_and_read_side_effects(client, postgres_db):
    conn, _cur = postgres_db
    first = _insert_briefing(conn, summary="Critical auth anomaly reviewed.")
    _insert_briefing(conn, summary="Low priority scanner dismissed.", content_status="failed", status="partial")
    p1, p2 = _login_role(client, "brief_analyst", "apass", "analyst")
    with p1, p2:
        assert client.post("/login", json={"username": "brief_analyst", "password": "apass"}).status_code == 200
        with _patched_db(conn):
            resp = client.get("/soc-briefings?search=auth&content_status=ready&limit=1&offset=0")
            detail = client.get(f"/soc-briefings/{first['briefing_id']}")
            missing = client.get("/soc-briefings/999999")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["limit"] == 1
    assert body["total"] == 1
    assert body["items"][0]["summary"] == "Critical auth anomaly reviewed."
    assert body["items"][0]["delivery"]["attempt_count"] == 0
    assert detail.status_code == 200
    detail_body = detail.get_json()
    assert set(detail_body["sections"]) == set(soc_briefing_history_store.BRIEFING_SECTION_KEYS)
    assert detail_body["run_steps"][0]["tool_name"] == "list_recent_alerts"
    assert detail_body["deliveries"] == []
    assert missing.status_code == 404
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM soc_briefing_delivery_attempts")
        assert cur.fetchone()[0] == 0


def test_slack_disabled_records_skipped_without_changing_briefing(client, postgres_db):
    conn, _cur = postgres_db
    row = _insert_briefing(conn)
    _login_super_admin(client)
    with _patched_db(conn):
        resp = client.post(f"/soc-briefings/{row['briefing_id']}/deliveries/slack/retry", json={})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "skipped"
    assert body["attempt"]["failure_code"] == "slack_disabled"
    with conn.cursor() as cur:
        cur.execute("SELECT status, content_status FROM soc_briefings WHERE id = %s", (row["briefing_id"],))
        assert cur.fetchone() == ("success", "ready")
        cur.execute("SELECT event_type, details FROM audit_log WHERE event_type = 'soc_briefing_slack_skipped'")
        event_type, details = cur.fetchone()
    assert event_type == "soc_briefing_slack_skipped"
    assert details["briefing_id"] == row["briefing_id"]


def test_slack_success_is_sanitized_and_duplicate_suppressed(client, postgres_db):
    conn, _cur = postgres_db
    row = _insert_briefing(
        conn,
        summary="Secret token https://hooks.slack.com/services/T000/B000/XXX should not leak.",
        sections={
            "alerts_reviewed": ["Alert #1001"],
            "dismissed_low_priority_findings": [],
            "escalations": ["Review bearer token exposure"],
            "critical_findings": ["Webhook URL https://example.test/private found"],
            "evidence": ["raw evidence omitted"],
            "recommendations": ["Rotate api key"],
        },
    )
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO notification_policy (id, slack_enabled)
            VALUES (1, TRUE)
            ON CONFLICT (id) DO UPDATE SET slack_enabled = TRUE
            """
        )
    conn.commit()
    captured = {}

    class _FakeAdapter:
        def execute(self, action, params, context):
            captured["action"] = action
            captured["params"] = params
            captured["context"] = context
            return {
                "success": True,
                "mode": "simulation",
                "executed": False,
                "simulated": True,
                "message": "sent",
                "metadata": {"provider_success": True},
            }

    _login_super_admin(client)
    with _patched_db(conn), patch(
        "core.ai.soc_briefing_history_store.get_integration_adapter",
        return_value=_FakeAdapter(),
    ):
        first = client.post(f"/soc-briefings/{row['briefing_id']}/deliveries/slack/retry", json={"siem_url": "https://siem.example/briefings/1"})
        second = client.post(f"/soc-briefings/{row['briefing_id']}/deliveries/slack/retry", json={})
    assert first.status_code == 200
    assert first.get_json()["status"] == "sent"
    assert second.status_code == 200
    assert second.get_json()["status"] == "duplicate_suppressed"
    text = captured["params"]["text"].lower()
    assert "https://" not in text
    assert "token" not in text
    assert "secret" not in text
    assert captured["context"]["purpose"] == "scheduled_soc_briefing"
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM soc_briefing_delivery_attempts WHERE briefing_id = %s", (row["briefing_id"],))
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT COUNT(*) FROM audit_log WHERE event_type = 'soc_briefing_slack_duplicate_suppressed'")
        assert cur.fetchone()[0] == 1


def test_slack_failure_records_bounded_retry_backoff(client, postgres_db):
    conn, _cur = postgres_db
    row = _insert_briefing(conn)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO notification_policy (id, slack_enabled)
            VALUES (1, TRUE)
            ON CONFLICT (id) DO UPDATE SET slack_enabled = TRUE
            """
        )
    conn.commit()

    class _FailingAdapter:
        def execute(self, action, params, context):
            return {
                "success": False,
                "mode": "simulation",
                "executed": False,
                "simulated": True,
                "message": "Provider failed at https://internal.example/webhook",
                "metadata": {"failure_classification": "transient"},
            }

    _login_super_admin(client)
    with _patched_db(conn), patch(
        "core.ai.soc_briefing_history_store.get_integration_adapter",
        return_value=_FailingAdapter(),
    ):
        resp = client.post(f"/soc-briefings/{row['briefing_id']}/deliveries/slack/retry", json={})
        retry = client.post(f"/soc-briefings/{row['briefing_id']}/deliveries/slack/retry", json={})
    assert resp.status_code == 200
    attempt = resp.get_json()["attempt"]
    assert attempt["status"] == "retry_scheduled"
    assert attempt["attempt_count"] == 1
    assert attempt["next_retry_at"] is not None
    assert attempt["failure_code"] == "transient"
    assert "https://" not in attempt["failure_message"]
    assert retry.status_code == 200
    assert retry.get_json()["attempt"]["attempt_count"] == 2
    assert retry.get_json()["status"] == "retry_scheduled"
    with conn.cursor() as cur:
        cur.execute("SELECT status, content_status FROM soc_briefings WHERE id = %s", (row["briefing_id"],))
        assert cur.fetchone() == ("success", "ready")
        cur.execute("SELECT COUNT(*) FROM soc_briefing_delivery_attempts WHERE briefing_id = %s", (row["briefing_id"],))
        assert cur.fetchone()[0] == 1
