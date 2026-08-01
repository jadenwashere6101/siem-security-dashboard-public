from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from werkzeug.security import generate_password_hash

from core.ai.workflow_orchestrator import WORKFLOW_DEEP_INVESTIGATE, WORKFLOW_QUICK_EXPLAIN
from core.ai.workflow_request_service import queue_workflow_request
from core.ai.workflow_request_store import (
    ASYNC_WORKFLOW_DECISION_SUPPORT,
    ASYNC_WORKFLOW_GENERATE_ARTIFACT,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_QUEUED,
    STATUS_RUNNING,
    STATUS_TIMED_OUT,
    claim_next_request,
    create_or_get_request,
    get_request,
    recover_stale_requests,
    serialize_request,
    utc_now,
)
from core.ai.workflow_request_worker import AnakinWorkflowWorkerConfig, run_anakin_workflow_worker


class NoCloseConnection:
    def __init__(self, conn):
        self._conn = conn

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def close(self):
        return None


def _fake_user(username: str, password: str, role: str):
    return {
        "username": username,
        "password_hash": generate_password_hash(password, method="pbkdf2:sha256"),
        "role": role,
        "is_active": True,
    }


def _login_role(client, *, username: str = "async_ai_analyst", role: str = "analyst"):
    password = "testpassword123!"
    user = _fake_user(username, password, role)
    patchers = [
        patch("routes.auth_routes.get_user_by_username", return_value=user),
        patch("core.auth.get_user_by_username", return_value=user),
    ]
    for patcher in patchers:
        patcher.start()
    response = client.post("/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return patchers


def _stop_patchers(patchers):
    for patcher in reversed(patchers):
        patcher.stop()


def _decision_payload(**overrides):
    payload = {
        "workflow": ASYNC_WORKFLOW_DECISION_SUPPORT,
        "prompt": "Should I monitor, escalate, or block?",
        "context_type": "alert",
        "context": {"alert_id": 1001, "source_ip": "203.0.113.77"},
        "client_request_id": "async-decision-1001",
    }
    payload.update(overrides)
    return payload


def _artifact_payload(**overrides):
    payload = {
        "workflow": ASYNC_WORKFLOW_GENERATE_ARTIFACT,
        "prompt": "Generate an investigation checklist for review only.",
        "context_type": "alert",
        "context": {"alert_id": 1001, "source_ip": "203.0.113.77"},
        "artifact": {"type": "investigation_checklist"},
        "client_request_id": "async-artifact-1001",
    }
    payload.update(overrides)
    return payload


def _auto_payload(prompt: str, **overrides):
    payload = {
        "workflow": "auto",
        "prompt": prompt,
        "context_type": "alert",
        "context": {"alert_id": 1001, "source_ip": "203.0.113.77"},
        "client_request_id": f"auto-{abs(hash(prompt))}",
    }
    payload.update(overrides)
    return payload


def test_queue_workflow_request_is_durable_idempotent_and_does_not_run_in_request(postgres_db, monkeypatch):
    conn, _cur = postgres_db
    monkeypatch.setattr("core.ai.workflow_request_service.get_db_connection", lambda: NoCloseConnection(conn))

    payload = _decision_payload()
    first, first_status = queue_workflow_request(payload, actor_username="analyst", actor_role="analyst")
    second, second_status = queue_workflow_request(payload, actor_username="analyst", actor_role="analyst")

    assert first_status == 202
    assert second_status == 200
    assert first["request_id"] == second["request_id"]
    assert first["status"] == STATUS_QUEUED
    assert first["workflow"] == ASYNC_WORKFLOW_DECISION_SUPPORT
    assert first["result"] is None
    assert first["metadata"]["async"] is True


def test_auto_quick_explain_returns_immediate_result_without_queueing(postgres_db, monkeypatch):
    conn, _cur = postgres_db
    monkeypatch.setattr("core.ai.workflow_request_service.get_db_connection", lambda: NoCloseConnection(conn))

    def fake_run_workflow(payload):
        assert payload["workflow"] == "auto"
        return SimpleNamespace(
            status_code=200,
            payload={
                "status": "success",
                "workflow": WORKFLOW_QUICK_EXPLAIN,
                "classification": {"classified_workflow": WORKFLOW_QUICK_EXPLAIN, "confidence": "medium"},
                "result": {"answer": "This is a quick explanation."},
                "metadata": {"profile": "fast_triage"},
                "error": None,
            },
        )

    monkeypatch.setattr("core.ai.workflow_request_service.run_workflow", fake_run_workflow)

    result, status = queue_workflow_request(
        _auto_payload("Explain this alert briefly.", client_request_id="auto-quick-1"),
        actor_username="analyst",
        actor_role="analyst",
    )

    assert status == 200
    assert result["workflow"] == WORKFLOW_QUICK_EXPLAIN
    assert result["metadata"]["async"] is False
    assert result["metadata"]["immediate"] is True
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM ai_workflow_requests")
        assert cur.fetchone()[0] == 0


def test_auto_deep_investigate_queues_after_backend_classification(postgres_db, monkeypatch):
    conn, _cur = postgres_db
    monkeypatch.setattr("core.ai.workflow_request_service.get_db_connection", lambda: NoCloseConnection(conn))

    result, status = queue_workflow_request(
        _auto_payload("Deep investigate this alert and identify evidence gaps.", client_request_id="auto-deep-1"),
        actor_username="analyst",
        actor_role="analyst",
    )

    assert status == 202
    assert result["status"] == STATUS_QUEUED
    assert result["workflow"] == WORKFLOW_DEEP_INVESTIGATE
    assert result["classification"]["requested_workflow"] == "auto"
    assert result["classification"]["classified_workflow"] == WORKFLOW_DEEP_INVESTIGATE


def test_auto_decision_support_queues_and_is_idempotent(postgres_db, monkeypatch):
    conn, _cur = postgres_db
    monkeypatch.setattr("core.ai.workflow_request_service.get_db_connection", lambda: NoCloseConnection(conn))
    payload = _auto_payload("Should I escalate or monitor this alert?", client_request_id="auto-decision-1")

    first, first_status = queue_workflow_request(payload, actor_username="analyst", actor_role="analyst")
    second, second_status = queue_workflow_request(payload, actor_username="analyst", actor_role="analyst")

    assert first_status == 202
    assert second_status == 200
    assert first["request_id"] == second["request_id"]
    assert first["workflow"] == ASYNC_WORKFLOW_DECISION_SUPPORT
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM ai_workflow_requests")
        assert cur.fetchone()[0] == 1


def test_low_confidence_auto_returns_chooser_without_queueing(postgres_db, monkeypatch):
    conn, _cur = postgres_db
    monkeypatch.setattr("core.ai.workflow_request_service.get_db_connection", lambda: NoCloseConnection(conn))

    result, status = queue_workflow_request(
        _auto_payload("Please repo deploy and run briefing now.", client_request_id="auto-chooser-1"),
        actor_username="analyst",
        actor_role="analyst",
    )

    assert status == 200
    assert result["status"] == "chooser_required"
    assert result["classification"]["chooser_required"] is True
    assert "request_id" not in result
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM ai_workflow_requests")
        assert cur.fetchone()[0] == 0


def test_restricted_workflows_cannot_be_queued_through_async_auto_path(postgres_db, monkeypatch):
    conn, _cur = postgres_db
    monkeypatch.setattr("core.ai.workflow_request_service.get_db_connection", lambda: NoCloseConnection(conn))

    for workflow in ("soc_briefing", "repo_assistant"):
        try:
            queue_workflow_request(
                {
                    "workflow": workflow,
                    "prompt": "Run the restricted assistant.",
                    "context_type": "alert",
                    "context": {"alert_id": 1},
                    "client_request_id": f"restricted-{workflow}",
                },
                actor_username="analyst",
                actor_role="analyst",
            )
        except Exception as error:
            assert getattr(error, "error_code", "") == "workflow_not_async"
        else:
            raise AssertionError(f"{workflow} should not be queueable")
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM ai_workflow_requests")
        assert cur.fetchone()[0] == 0


def test_worker_claims_and_completes_each_async_workflow_without_persistence(postgres_db, monkeypatch):
    conn, _cur = postgres_db
    workflows = [
        ("deep_investigate", {"workflow": "deep_investigate", "prompt": "Deep investigate this alert.", "context_type": "alert", "context": {"alert_id": 1}, "client_request_id": "deep-1"}),
        (ASYNC_WORKFLOW_DECISION_SUPPORT, _decision_payload(client_request_id="decision-1")),
        (ASYNC_WORKFLOW_GENERATE_ARTIFACT, _artifact_payload(client_request_id="artifact-1")),
    ]
    for workflow, payload in workflows:
        create_or_get_request(
            conn,
            workflow=workflow,
            context_type=payload["context_type"],
            payload=payload,
            classification={"classified_workflow": workflow, "confidence": "explicit", "reason": "test"},
            actor_username="analyst",
            actor_role="analyst",
            now=utc_now() - timedelta(seconds=1),
        )
    conn.commit()

    def fake_run_workflow(payload):
        workflow = payload["workflow"]
        if workflow == ASYNC_WORKFLOW_GENERATE_ARTIFACT:
            return SimpleNamespace(
                status_code=200,
                payload={
                    "status": "success",
                    "workflow": workflow,
                    "result": {
                        "status": "success",
                        "draft": {
                            "draft_type": "investigation_checklist",
                            "labels": {"persisted": False, "applied": False},
                        },
                        "metadata": {"profile": "guided_analysis"},
                    },
                    "metadata": {"profile": "guided_analysis"},
                },
            )
        return SimpleNamespace(
            status_code=200,
            payload={
                "status": "success",
                "workflow": workflow,
                "result": {"status": "success", "answer": "Read-only recommendation.", "metadata": {"profile": "guided_analysis"}},
                "metadata": {"profile": "guided_analysis"},
            },
        )

    monkeypatch.setattr("core.ai.workflow_request_worker._run_with_user_context", lambda payload, **_kwargs: fake_run_workflow(payload))

    stats = run_anakin_workflow_worker(
        config=AnakinWorkflowWorkerConfig(batch_size=3, max_runtime_seconds=30),
        worker_id="test-worker",
        connect=lambda: NoCloseConnection(conn),
        flask_app=None,
    )

    assert stats["processed"] == 3
    assert stats["success"] == 3
    for _workflow, payload in workflows:
        row = get_request(conn, f"aiwf_missing_{payload['client_request_id']}", actor_username="analyst")
        assert row is None
    with conn.cursor() as cur:
        cur.execute("SELECT workflow, status, stage, result_payload FROM ai_workflow_requests ORDER BY workflow")
        rows = cur.fetchall()
    assert {row[1] for row in rows} == {STATUS_COMPLETED}
    artifact = next(row[3] for row in rows if row[0] == ASYNC_WORKFLOW_GENERATE_ARTIFACT)
    assert artifact["result"]["draft"]["labels"]["persisted"] is False
    assert artifact["result"]["draft"]["labels"]["applied"] is False


def test_stale_running_job_recovery_is_bounded(postgres_db):
    conn, _cur = postgres_db
    row, _created = create_or_get_request(
        conn,
        workflow=ASYNC_WORKFLOW_DECISION_SUPPORT,
        context_type="alert",
        payload=_decision_payload(client_request_id="stale-1"),
        classification={"classified_workflow": ASYNC_WORKFLOW_DECISION_SUPPORT, "confidence": "explicit"},
        actor_username="analyst",
        actor_role="analyst",
        max_attempts=2,
        now=utc_now() - timedelta(minutes=11),
    )
    claimed = claim_next_request(conn, lease_owner="stale-worker", now=utc_now() - timedelta(minutes=10), lease_duration_seconds=60)
    assert claimed["request_id"] == row["request_id"]
    conn.commit()

    recovery = recover_stale_requests(conn, now=utc_now(), limit=1)
    conn.commit()
    recovered = get_request(conn, row["request_id"], actor_username="analyst")

    assert recovery["recovered"] == 1
    assert recovered["status"] == STATUS_QUEUED
    assert recovered["recovery_count"] == 1


def test_stale_running_job_fails_after_recovery_limit(postgres_db):
    conn, _cur = postgres_db
    row, _created = create_or_get_request(
        conn,
        workflow=ASYNC_WORKFLOW_DECISION_SUPPORT,
        context_type="alert",
        payload=_decision_payload(client_request_id="stale-fail-1"),
        classification={"classified_workflow": ASYNC_WORKFLOW_DECISION_SUPPORT, "confidence": "explicit"},
        actor_username="analyst",
        actor_role="analyst",
        now=utc_now() - timedelta(minutes=11),
    )
    claimed = claim_next_request(conn, lease_owner="stale-worker", now=utc_now() - timedelta(minutes=10), lease_duration_seconds=60)
    assert claimed["request_id"] == row["request_id"]
    with conn.cursor() as cur:
        cur.execute("UPDATE ai_workflow_requests SET attempt_count = max_attempts WHERE request_id = %s", (row["request_id"],))
    conn.commit()

    recovery = recover_stale_requests(conn, now=utc_now(), limit=1)
    conn.commit()
    recovered = get_request(conn, row["request_id"], actor_username="analyst")

    assert recovery["failed"] == 1
    assert recovered["status"] == STATUS_TIMED_OUT
    assert recovered["error_code"] == "stale_lease_expired"


def test_async_workflow_routes_queue_and_read_for_actor_only(client, postgres_db, monkeypatch):
    conn, _cur = postgres_db
    monkeypatch.setattr("core.ai.workflow_request_service.get_db_connection", lambda: NoCloseConnection(conn))
    monkeypatch.setattr("routes.ai_routes.log_audit_event", lambda *args, **kwargs: None)
    patchers = _login_role(client, username="route_analyst", role="analyst")
    try:
        queued = client.post("/ai/workflows/requests", json=_decision_payload(client_request_id="route-decision-1"))
        assert queued.status_code == 202
        body = queued.get_json()
        assert body["status"] == STATUS_QUEUED
        assert body["request_id"]

        read = client.get(f"/ai/workflows/requests/{body['request_id']}")
        assert read.status_code == 200
        assert read.get_json()["request_id"] == body["request_id"]
    finally:
        _stop_patchers(patchers)

    other_patchers = _login_role(client, username="other_analyst", role="analyst")
    try:
        denied = client.get(f"/ai/workflows/requests/{body['request_id']}")
        assert denied.status_code == 404
    finally:
        _stop_patchers(other_patchers)


def test_async_route_blocks_client_mutation_and_quick_explain(client, postgres_db, monkeypatch):
    conn, _cur = postgres_db
    monkeypatch.setattr("core.ai.workflow_request_service.get_db_connection", lambda: NoCloseConnection(conn))
    monkeypatch.setattr("routes.ai_routes.log_audit_event", lambda *args, **kwargs: None)
    patchers = _login_role(client, username="safe_analyst", role="analyst")
    try:
        mutation = client.post("/ai/workflows/requests", json=_decision_payload(confirm=True))
        quick = client.post(
            "/ai/workflows/requests",
            json={"workflow": "quick_explain", "prompt": "Explain this.", "context_type": "alert", "context": {"alert_id": 1}},
        )
    finally:
        _stop_patchers(patchers)

    assert mutation.status_code == 400
    assert mutation.get_json()["error_code"] == "async_workflow_read_only"
    assert quick.status_code == 400
    assert quick.get_json()["error_code"] == "workflow_not_async"
