from unittest.mock import patch


def _login_session(client, user_id):
    with client.session_transaction() as session:
        session["_user_id"] = user_id
        session["_fresh"] = True


def test_soc_briefing_worker_metrics_requires_login(client):
    resp = client.get("/metrics/soc-briefing-worker")
    assert resp.status_code == 401


def test_soc_briefing_worker_metrics_allows_super_admin(client):
    _login_session(client, "admin")
    payload = {
        "worker": {"status": "unknown", "worker_instance_id": None},
        "service_actor": "scheduled_soc_briefing_worker",
        "read_only": True,
        "jobs": {"pending": 0},
    }

    with patch("routes.metrics_routes.get_soc_briefing_runtime_metrics", return_value=payload):
        resp = client.get("/metrics/soc-briefing-worker")

    assert resp.status_code == 200
    assert resp.get_json()["service_actor"] == "scheduled_soc_briefing_worker"


def test_soc_briefing_worker_metrics_forbids_viewer(client):
    _login_session(client, "viewer-user")

    with patch(
        "core.auth.get_user_by_username",
        return_value={
            "username": "viewer-user",
            "password_hash": "x",
            "role": "viewer",
            "is_active": True,
        },
    ), patch("core.audit_helpers.get_db_connection"):
        resp = client.get("/metrics/soc-briefing-worker")

    assert resp.status_code == 403
