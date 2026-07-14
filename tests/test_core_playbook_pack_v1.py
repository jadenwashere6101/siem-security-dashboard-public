from unittest.mock import patch

import pytest

from core import approval_store, playbook_store
from core.core_playbook_pack_v1 import (
    CORE_PLAYBOOK_PACK_V1,
    CORE_V1_BRUTE_FORCE_CONTAINMENT_ID,
    CORE_V1_CLOUD_APP_ERROR_CORRELATION_INVESTIGATION_ID,
    CORE_V1_HONEYPOT_CREDENTIAL_STUFFING_CONTAINMENT_ID,
    CORE_V1_HONEYPOT_SCANNER_REVIEW_ID,
    CORE_V1_MALICIOUS_IP_CONTAINMENT_ID,
    CORE_V1_PFSENSE_PORT_SCAN_CONTAINMENT_ID,
    CORE_V1_PFSENSE_PORT_SCAN_INVESTIGATION_ID,
    CORE_V1_PFSENSE_REPEATED_DENY_INVESTIGATION_ID,
    CORE_V1_PFSENSE_SUSPICIOUS_ALLOW_CONTAINMENT_ID,
    CORE_V1_PASSWORD_SPRAY_INVESTIGATION_ID,
    CORE_V1_REPUTATION_INVESTIGATION_ID,
    CORE_V1_SPRAY_SUCCESS_RESPONSE_ID,
    CORE_V1_SPRAY_THEN_SUCCESS_CORRELATION_INVESTIGATION_ID,
    CORE_V1_WEB_TO_APP_ATTACK_INVESTIGATION_ID,
    seed_core_playbook_pack_v1,
    validate_core_playbook_pack_v1,
)
from engines import playbook_step_executor
from engines.playbook_engine import match_playbooks
from engines.playbook_registry import validate_playbook_steps


@pytest.mark.parametrize("playbook", CORE_PLAYBOOK_PACK_V1, ids=lambda item: item["id"])
def test_core_pack_playbook_steps_validate(playbook):
    assert validate_playbook_steps(playbook["steps"]) == []


def test_core_pack_aggregate_validation_passes():
    assert validate_core_playbook_pack_v1() == []


def test_core_pack_seed_inserts_all_ten_playbooks(postgres_db):
    conn, _cur = postgres_db
    inserted = seed_core_playbook_pack_v1(conn)
    assert inserted == [item["id"] for item in CORE_PLAYBOOK_PACK_V1]
    for item in CORE_PLAYBOOK_PACK_V1:
        row = playbook_store.get_playbook_definition(conn, item["id"])
        assert row is not None
        assert row["name"] == item["name"]
        assert row["trigger_config"] == item["trigger_config"]
        assert row["steps"] == item["steps"]


def test_core_pack_seed_is_idempotent(postgres_db):
    conn, _cur = postgres_db
    first = seed_core_playbook_pack_v1(conn)
    second = seed_core_playbook_pack_v1(conn)
    assert len(first) == len(CORE_PLAYBOOK_PACK_V1)
    assert second == []


def _insert_alert(cur, **kwargs):
    values = {
        "alert_type": "failed_login_threshold",
        "severity": "HIGH",
        "source_ip": "198.51.100.10",
        "message": "Synthetic alert message",
        "source": "bank_app",
        "reputation_score": 85,
        "reputation_summary": "Known abusive source",
    }
    values.update(kwargs)
    cur.execute(
        """
        INSERT INTO alerts (
            alert_type, severity, source_ip, message, source,
            reputation_score, reputation_summary
        )
        VALUES (%s, %s, %s::inet, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            values["alert_type"],
            values["severity"],
            values["source_ip"],
            values["message"],
            values["source"],
            values["reputation_score"],
            values["reputation_summary"],
        ),
    )
    return cur.fetchone()[0]


@pytest.mark.parametrize(
    ("playbook_id", "alert_kwargs"),
    [
        (
            CORE_V1_BRUTE_FORCE_CONTAINMENT_ID,
            {"alert_type": "failed_login_threshold", "severity": "HIGH"},
        ),
        (
            CORE_V1_PASSWORD_SPRAY_INVESTIGATION_ID,
            {"alert_type": "password_spraying_threshold", "severity": "HIGH"},
        ),
        (
            CORE_V1_SPRAY_SUCCESS_RESPONSE_ID,
            {
                "alert_type": "successful_login_after_spray",
                "severity": "CRITICAL",
            },
        ),
        (
            CORE_V1_MALICIOUS_IP_CONTAINMENT_ID,
            {
                "alert_type": "port_scan_threshold",
                "severity": "MEDIUM",
                "reputation_score": 90,
            },
        ),
        (
            CORE_V1_REPUTATION_INVESTIGATION_ID,
            {
                "alert_type": "http_error_threshold",
                "severity": "LOW",
                "reputation_score": 45,
            },
        ),
        (
            CORE_V1_WEB_TO_APP_ATTACK_INVESTIGATION_ID,
            {
                "alert_type": "web_to_app_attack_pattern",
                "severity": "CRITICAL",
            },
        ),
        (
            CORE_V1_CLOUD_APP_ERROR_CORRELATION_INVESTIGATION_ID,
            {
                "alert_type": "cloud_app_error_pattern",
                "severity": "HIGH",
            },
        ),
        (
            CORE_V1_SPRAY_THEN_SUCCESS_CORRELATION_INVESTIGATION_ID,
            {
                "alert_type": "spray_then_success_pattern",
                "severity": "CRITICAL",
            },
        ),
        (
            CORE_V1_HONEYPOT_SCANNER_REVIEW_ID,
            {
                "alert_type": "honeypot_scanner_detected",
                "severity": "MEDIUM",
            },
        ),
        (
            CORE_V1_HONEYPOT_CREDENTIAL_STUFFING_CONTAINMENT_ID,
            {
                "alert_type": "honeypot_credential_stuffing_threshold",
                "severity": "HIGH",
            },
        ),
    ],
)
def test_core_pack_playbook_triggers_match_synthetic_alert(
    postgres_db, playbook_id, alert_kwargs
):
    conn, cur = postgres_db
    seed_core_playbook_pack_v1(conn)
    aid = _insert_alert(cur, **alert_kwargs)
    matched = match_playbooks(conn, aid)
    assert any(row["id"] == playbook_id for row in matched)


def test_core_pack_playbook_triggers_do_not_match_wrong_alert(postgres_db):
    conn, cur = postgres_db
    seed_core_playbook_pack_v1(conn)
    aid = _insert_alert(cur, alert_type="failed_login_threshold", severity="LOW")
    matched = match_playbooks(conn, aid)
    assert CORE_V1_BRUTE_FORCE_CONTAINMENT_ID not in {row["id"] for row in matched}


@pytest.mark.parametrize(
    ("alert_kwargs", "expected_playbook_ids"),
    [
        (
            {
                "alert_type": "pfsense_firewall_repeated_deny",
                "severity": "MEDIUM",
                "reputation_score": 90,
            },
            {CORE_V1_PFSENSE_REPEATED_DENY_INVESTIGATION_ID},
        ),
        (
            {
                "alert_type": "pfsense_firewall_port_scan",
                "severity": "HIGH",
                "reputation_score": 90,
            },
            {
                CORE_V1_PFSENSE_PORT_SCAN_INVESTIGATION_ID,
                CORE_V1_PFSENSE_PORT_SCAN_CONTAINMENT_ID,
            },
        ),
        (
            {
                "alert_type": "pfsense_firewall_suspicious_allow",
                "severity": "HIGH",
                "reputation_score": 90,
            },
            {CORE_V1_PFSENSE_SUSPICIOUS_ALLOW_CONTAINMENT_ID},
        ),
    ],
)
def test_core_pack_reputation_playbook_excludes_dedicated_pfsense_alert_types(
    postgres_db, alert_kwargs, expected_playbook_ids
):
    conn, cur = postgres_db
    seed_core_playbook_pack_v1(conn)
    aid = _insert_alert(cur, **alert_kwargs)
    matched_ids = {row["id"] for row in match_playbooks(conn, aid)}
    assert CORE_V1_REPUTATION_INVESTIGATION_ID not in matched_ids
    assert expected_playbook_ids.issubset(matched_ids)


def test_core_pack_reputation_playbook_still_matches_http_error_threshold(postgres_db):
    conn, cur = postgres_db
    seed_core_playbook_pack_v1(conn)
    aid = _insert_alert(
        cur,
        alert_type="http_error_threshold",
        severity="LOW",
        reputation_score=45,
    )
    matched_ids = {row["id"] for row in match_playbooks(conn, aid)}
    assert CORE_V1_REPUTATION_INVESTIGATION_ID in matched_ids


def test_core_pack_reputation_playbook_still_matches_pfsense_noisy_source(postgres_db):
    conn, cur = postgres_db
    seed_core_playbook_pack_v1(conn)
    aid = _insert_alert(
        cur,
        alert_type="pfsense_firewall_noisy_source",
        severity="LOW",
        reputation_score=45,
        source="pfsense",
    )
    matched_ids = {row["id"] for row in match_playbooks(conn, aid)}
    assert CORE_V1_REPUTATION_INVESTIGATION_ID in matched_ids


@pytest.mark.parametrize(
    ("alert_kwargs", "expected_playbook_ids"),
    [
        (
            {
                "alert_type": "pfsense_firewall_repeated_deny",
                "severity": "MEDIUM",
                "reputation_score": 90,
            },
            {CORE_V1_PFSENSE_REPEATED_DENY_INVESTIGATION_ID},
        ),
        (
            {
                "alert_type": "pfsense_firewall_port_scan",
                "severity": "HIGH",
                "reputation_score": 90,
            },
            {
                CORE_V1_PFSENSE_PORT_SCAN_INVESTIGATION_ID,
                CORE_V1_PFSENSE_PORT_SCAN_CONTAINMENT_ID,
            },
        ),
        (
            {
                "alert_type": "pfsense_firewall_suspicious_allow",
                "severity": "HIGH",
                "reputation_score": 90,
            },
            {CORE_V1_PFSENSE_SUSPICIOUS_ALLOW_CONTAINMENT_ID},
        ),
    ],
)
def test_core_pack_malicious_ip_playbook_excludes_dedicated_pfsense_alert_types(
    postgres_db, alert_kwargs, expected_playbook_ids
):
    conn, cur = postgres_db
    seed_core_playbook_pack_v1(conn)
    aid = _insert_alert(cur, **alert_kwargs)
    matched_ids = {row["id"] for row in match_playbooks(conn, aid)}
    assert CORE_V1_MALICIOUS_IP_CONTAINMENT_ID not in matched_ids
    assert expected_playbook_ids.issubset(matched_ids)


def test_core_pack_malicious_ip_playbook_still_matches_non_pfsense_reputation_alerts(
    postgres_db,
):
    conn, cur = postgres_db
    seed_core_playbook_pack_v1(conn)
    aid = _insert_alert(
        cur,
        alert_type="port_scan_threshold",
        severity="MEDIUM",
        reputation_score=90,
        source="bank_app",
    )
    matched_ids = {row["id"] for row in match_playbooks(conn, aid)}
    assert CORE_V1_MALICIOUS_IP_CONTAINMENT_ID in matched_ids


def test_core_pack_malicious_ip_playbook_still_matches_pfsense_noisy_source(postgres_db):
    conn, cur = postgres_db
    seed_core_playbook_pack_v1(conn)
    aid = _insert_alert(
        cur,
        alert_type="pfsense_firewall_noisy_source",
        severity="MEDIUM",
        reputation_score=90,
        source="pfsense",
    )
    matched_ids = {row["id"] for row in match_playbooks(conn, aid)}
    assert CORE_V1_MALICIOUS_IP_CONTAINMENT_ID in matched_ids


def test_password_spray_investigation_executes_with_dynamic_notification(postgres_db):
    conn, cur = postgres_db
    seed_core_playbook_pack_v1(conn)
    aid = _insert_alert(
        cur,
        alert_type="password_spraying_threshold",
        reputation_summary="Spray source reputation context",
    )
    eid = playbook_store.create_pending_playbook_execution_once(
        conn, CORE_V1_PASSWORD_SPRAY_INVESTIGATION_ID, aid
    )

    captured = {}

    def capture_adapter(*_args, **kwargs):
        captured["params"] = kwargs.get("params")
        return {
            "adapter": "slack",
            "action": "send_message",
            "mode": "simulation",
            "simulated": True,
            "executed": False,
            "success": True,
            "message": "ok",
            "params": kwargs.get("params") or {},
            "context": kwargs.get("context") or {},
            "metadata": {},
        }

    with patch(
        "engines.playbook_step_executor.execute_playbook_simulated_adapter",
        side_effect=capture_adapter,
    ):
        result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "success"
    assert captured["params"]["message"] == "Spray source reputation context"


def test_password_spray_investigation_enriches_context_before_notification(postgres_db):
    conn, cur = postgres_db
    seed_core_playbook_pack_v1(conn)
    aid = _insert_alert(
        cur,
        alert_type="password_spraying_threshold",
        reputation_summary="Spray source reputation context",
    )
    eid = playbook_store.create_pending_playbook_execution_once(
        conn, CORE_V1_PASSWORD_SPRAY_INVESTIGATION_ID, aid
    )

    result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "success"
    row = playbook_store.get_playbook_execution(conn, eid)
    assert row["steps_log"][0]["action"] == "enrich_context"
    assert row["steps_log"][0]["status"] == "success"


def test_brute_force_containment_block_ip_resolves_after_approval(postgres_db):
    conn, cur = postgres_db
    seed_core_playbook_pack_v1(conn)
    offender_ip = "198.51.100.88"
    aid = _insert_alert(
        cur,
        alert_type="failed_login_threshold",
        severity="HIGH",
        source_ip=offender_ip,
    )
    eid = playbook_store.create_pending_playbook_execution_once(
        conn, CORE_V1_BRUTE_FORCE_CONTAINMENT_ID, aid
    )
    cur.execute(
        """
        INSERT INTO users (username, password_hash, role)
        VALUES ('core-pack-approver', 'hash', 'analyst')
        RETURNING id
        """
    )
    user_id = cur.fetchone()[0]

    captured = {}

    def capture_adapter(adapter_name, adapter_action, **kwargs):
        if adapter_name == "firewall" and adapter_action == "block_ip":
            captured["params"] = kwargs.get("params")
        return {
            "adapter": adapter_name,
            "action": adapter_action,
            "mode": "simulation",
            "simulated": True,
            "executed": False,
            "success": True,
            "message": "ok",
            "params": kwargs.get("params") or {},
            "context": kwargs.get("context") or {},
            "metadata": {},
        }

    with patch(
        "engines.playbook_step_executor.execute_playbook_simulated_adapter",
        side_effect=capture_adapter,
    ):
        pause = playbook_step_executor.process_playbook_execution(conn, eid)
        assert pause["outcome"] == "awaiting_approval"
        approval_entry = next(
            entry
            for entry in playbook_store.get_playbook_execution(conn, eid)["steps_log"]
            if entry.get("action") == "require_approval"
        )
        approval_id = approval_entry["approval_request_id"]
        approval_store.approve_request(conn, approval_id, actor_user_id=user_id)
        result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "success"
    assert captured["params"]["source_ip"] == offender_ip
    row = playbook_store.get_playbook_execution(conn, eid)
    block_entry = next(entry for entry in row["steps_log"] if entry["action"] == "block_ip")
    assert block_entry["output"]["resolved_params"]["source_ip"] == offender_ip


def test_malicious_ip_containment_matches_reputation_trigger_only(postgres_db):
    conn, cur = postgres_db
    seed_core_playbook_pack_v1(conn)
    aid = _insert_alert(
        cur,
        alert_type="honeypot_scanner_detected",
        severity="MEDIUM",
        reputation_score=95,
    )
    matched = match_playbooks(conn, aid)
    assert CORE_V1_MALICIOUS_IP_CONTAINMENT_ID in {row["id"] for row in matched}

    low_rep_aid = _insert_alert(
        cur,
        alert_type="honeypot_scanner_detected",
        severity="MEDIUM",
        source_ip="198.51.100.99",
        reputation_score=50,
    )
    low_rep_matched = match_playbooks(conn, low_rep_aid)
    assert CORE_V1_MALICIOUS_IP_CONTAINMENT_ID not in {row["id"] for row in low_rep_matched}


def test_honeypot_credential_stuffing_containment_pauses_for_approval(postgres_db):
    conn, cur = postgres_db
    seed_core_playbook_pack_v1(conn)
    aid = _insert_alert(
        cur,
        alert_type="honeypot_credential_stuffing_threshold",
        severity="HIGH",
        source_ip="198.51.100.120",
    )
    eid = playbook_store.create_pending_playbook_execution_once(
        conn, CORE_V1_HONEYPOT_CREDENTIAL_STUFFING_CONTAINMENT_ID, aid
    )

    result = playbook_step_executor.process_playbook_execution(conn, eid)

    assert result["outcome"] == "awaiting_approval"
    row = playbook_store.get_playbook_execution(conn, eid)
    actions = [entry["action"] for entry in row["steps_log"]]
    assert actions[:3] == ["flag_high_priority", "enrich_context", "require_approval"]
