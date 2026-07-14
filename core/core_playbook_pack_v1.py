"""
Core Playbook Pack v1 definitions.

Ten production playbooks authored as data for `playbook_definitions`. Notification
params use whole-value dynamic bindings (`{{alert.<field>}}`) per the parameter-binding
engine; composite inline templates are not supported at save time.
"""

from __future__ import annotations

from typing import Any

from core.playbook_store import create_playbook_definition, get_playbook_definition
from engines.playbook_registry import validate_playbook_steps

CORE_V1_BRUTE_FORCE_CONTAINMENT_ID = "core-v1-brute-force-containment"
CORE_V1_PASSWORD_SPRAY_INVESTIGATION_ID = "core-v1-password-spray-investigation"
CORE_V1_SPRAY_SUCCESS_RESPONSE_ID = "core-v1-spray-success-response"
CORE_V1_MALICIOUS_IP_CONTAINMENT_ID = "core-v1-malicious-ip-containment"
CORE_V1_REPUTATION_INVESTIGATION_ID = "core-v1-reputation-investigation"
CORE_V1_WEB_TO_APP_ATTACK_INVESTIGATION_ID = "core-v1-web-to-app-attack-investigation"
CORE_V1_CLOUD_APP_ERROR_CORRELATION_INVESTIGATION_ID = (
    "core-v1-cloud-app-error-correlation-investigation"
)
CORE_V1_SPRAY_THEN_SUCCESS_CORRELATION_INVESTIGATION_ID = (
    "core-v1-spray-then-success-correlation-investigation"
)
CORE_V1_HONEYPOT_SCANNER_REVIEW_ID = "core-v1-honeypot-scanner-review"
CORE_V1_HONEYPOT_CREDENTIAL_STUFFING_CONTAINMENT_ID = (
    "core-v1-honeypot-credential-stuffing-containment"
)
CORE_V1_PFSENSE_REPEATED_DENY_INVESTIGATION_ID = "core-v1-pfsense-repeated-deny-investigation"
CORE_V1_PFSENSE_PORT_SCAN_INVESTIGATION_ID = "core-v1-pfsense-port-scan-investigation"
CORE_V1_PFSENSE_PORT_SCAN_CONTAINMENT_ID = "core-v1-pfsense-port-scan-containment"
CORE_V1_PFSENSE_SUSPICIOUS_ALLOW_CONTAINMENT_ID = "core-v1-pfsense-suspicious-allow-containment"

CORE_PLAYBOOK_PACK_V1: tuple[dict[str, Any], ...] = (
    {
        "id": CORE_V1_BRUTE_FORCE_CONTAINMENT_ID,
        "name": "Brute Force Containment",
        "description": (
            "Escalate sustained failed-login patterns with enriched context and "
            "approval-gated IP containment."
        ),
        "trigger_config": {
            "alert_type": "failed_login_threshold",
            "min_severity": "high",
        },
        "steps": [
            {"action": "flag_high_priority"},
            {"action": "enrich_context"},
            {
                "action": "require_approval",
                "risk_level": "high",
                "expires_in_minutes": 30,
                "reason": "Sustained failed-login pattern — approve IP block",
            },
            {"action": "block_ip", "params": {"source_ip": "{{alert.source_ip}}"}},
            {"action": "notify_slack", "params": {"message": "{{alert.message}}"}},
        ],
    },
    {
        "id": CORE_V1_PASSWORD_SPRAY_INVESTIGATION_ID,
        "name": "Password Spray Investigation",
        "description": (
            "Investigate password-spray activity with enriched alert context and "
            "no automatic blocking."
        ),
        "trigger_config": {"alert_type": "password_spraying_threshold"},
        "steps": [
            {"action": "enrich_context"},
            {"action": "monitor"},
            {
                "action": "notify_slack",
                "params": {"message": "{{alert.reputation_summary}}"},
            },
        ],
    },
    {
        "id": CORE_V1_SPRAY_SUCCESS_RESPONSE_ID,
        "name": "Password Spray Compromise Containment",
        "description": (
            "Contain likely account compromise after password spraying using "
            "enriched context and approval-gated IP blocking."
        ),
        "trigger_config": {
            "alert_type": "successful_login_after_spray",
            "min_severity": "critical",
        },
        "steps": [
            {"action": "flag_high_priority"},
            {"action": "enrich_context"},
            {
                "action": "require_approval",
                "risk_level": "critical",
                "expires_in_minutes": 15,
                "reason": (
                    "Successful login following password-spray — "
                    "near-certain compromise, approve IP block"
                ),
            },
            {"action": "block_ip", "params": {"source_ip": "{{alert.source_ip}}"}},
            {"action": "notify_slack", "params": {"message": "{{alert.message}}"}},
            {
                "action": "notify_email",
                "params": {
                    "subject": "{{alert.alert_type}}",
                    "message": "{{alert.message}}",
                },
            },
        ],
    },
    {
        "id": CORE_V1_MALICIOUS_IP_CONTAINMENT_ID,
        "name": "Malicious IP Containment",
        "description": (
            "Approval-gated containment for medium-or-higher alerts from "
            "high-reputation-risk source IPs, with enriched context."
        ),
        "trigger_config": {
            "reputation_score_min": 80,
            "min_severity": "medium",
        },
        "steps": [
            {"action": "flag_high_priority"},
            {"action": "enrich_context"},
            {
                "action": "require_approval",
                "risk_level": "high",
                "reason": "Known-malicious source IP — approve block",
            },
            {"action": "block_ip", "params": {"source_ip": "{{alert.source_ip}}"}},
            {"action": "notify_slack", "params": {"message": "{{alert.message}}"}},
        ],
    },
    {
        "id": CORE_V1_REPUTATION_INVESTIGATION_ID,
        "name": "High Reputation Review",
        "description": (
            "Review low-severity alerts that carry elevated reputation risk, "
            "with enriched context and no containment."
        ),
        "trigger_config": {
            "reputation_score_min": 40,
            "min_severity": "low",
            "exclude_alert_types": [
                "pfsense_firewall_port_scan",
                "pfsense_firewall_repeated_deny",
                "pfsense_firewall_suspicious_allow",
            ],
        },
        "steps": [
            {"action": "enrich_context"},
            {"action": "monitor"},
            {
                "action": "notify_slack",
                "params": {"message": "{{alert.reputation_summary}}"},
            },
        ],
    },
    {
        "id": CORE_V1_WEB_TO_APP_ATTACK_INVESTIGATION_ID,
        "name": "Web-to-App Attack Investigation",
        "description": (
            "Investigate correlated web-to-application attack patterns with "
            "enriched context and analyst notification."
        ),
        "trigger_config": {
            "alert_type": "web_to_app_attack_pattern",
            "min_severity": "critical",
        },
        "steps": [
            {"action": "enrich_context"},
            {"action": "monitor"},
            {"action": "notify_slack", "params": {"message": "{{alert.message}}"}},
        ],
    },
    {
        "id": CORE_V1_CLOUD_APP_ERROR_CORRELATION_INVESTIGATION_ID,
        "name": "Cloud/App Error Correlation Investigation",
        "description": (
            "Investigate correlated cloud and web application error patterns "
            "with enriched context."
        ),
        "trigger_config": {
            "alert_type": "cloud_app_error_pattern",
            "min_severity": "high",
        },
        "steps": [
            {"action": "enrich_context"},
            {"action": "monitor"},
            {"action": "notify_slack", "params": {"message": "{{alert.message}}"}},
        ],
    },
    {
        "id": CORE_V1_SPRAY_THEN_SUCCESS_CORRELATION_INVESTIGATION_ID,
        "name": "Spray-Then-Success Correlation Investigation",
        "description": (
            "Contain high-confidence spray-then-success correlation alerts with "
            "enriched context and approval-gated IP blocking."
        ),
        "trigger_config": {
            "alert_type": "spray_then_success_pattern",
            "min_severity": "critical",
        },
        "steps": [
            {"action": "flag_high_priority"},
            {"action": "enrich_context"},
            {
                "action": "require_approval",
                "risk_level": "critical",
                "expires_in_minutes": 15,
                "reason": "Spray-then-success correlation detected — approve IP block",
            },
            {"action": "block_ip", "params": {"source_ip": "{{alert.source_ip}}"}},
            {"action": "notify_slack", "params": {"message": "{{alert.message}}"}},
        ],
    },
    {
        "id": CORE_V1_HONEYPOT_SCANNER_REVIEW_ID,
        "name": "Honeypot Scanner Review",
        "description": (
            "Review scanner activity detected by honeypot telemetry using "
            "enriched context and analyst notification."
        ),
        "trigger_config": {
            "alert_type": "honeypot_scanner_detected",
            "min_severity": "medium",
        },
        "steps": [
            {"action": "enrich_context"},
            {"action": "monitor"},
            {"action": "notify_slack", "params": {"message": "{{alert.message}}"}},
        ],
    },
    {
        "id": CORE_V1_HONEYPOT_CREDENTIAL_STUFFING_CONTAINMENT_ID,
        "name": "Honeypot Credential Stuffing Containment",
        "description": (
            "Contain honeypot credential-stuffing alerts with enriched context "
            "and approval-gated IP blocking."
        ),
        "trigger_config": {
            "alert_type": "honeypot_credential_stuffing_threshold",
            "min_severity": "high",
        },
        "steps": [
            {"action": "flag_high_priority"},
            {"action": "enrich_context"},
            {
                "action": "require_approval",
                "risk_level": "high",
                "expires_in_minutes": 30,
                "reason": "Honeypot credential stuffing detected — approve IP block",
            },
            {"action": "block_ip", "params": {"source_ip": "{{alert.source_ip}}"}},
            {"action": "notify_slack", "params": {"message": "{{alert.message}}"}},
        ],
    },
    {
        "id": CORE_V1_PFSENSE_REPEATED_DENY_INVESTIGATION_ID,
        "name": "pfSense Repeated Deny Investigation",
        "description": (
            "Investigate repeated pfSense firewall denies with enriched context "
            "and no automatic blocking. Investigation-only outcome: visible on "
            "the alert dashboard and Detection Health, does not page Slack "
            "(reserved for containment-outcome playbooks)."
        ),
        "trigger_config": {
            "alert_type": "pfsense_firewall_repeated_deny",
            "min_severity": "medium",
        },
        "steps": [
            {"action": "enrich_context"},
            {"action": "monitor"},
        ],
    },
    {
        "id": CORE_V1_PFSENSE_PORT_SCAN_INVESTIGATION_ID,
        "name": "pfSense Port Scan Investigation",
        "description": (
            "Investigate medium-severity pfSense firewall port scan activity "
            "with enriched context and no automatic blocking. Investigation-only "
            "outcome: visible on the alert dashboard and Detection Health, does "
            "not page Slack (reserved for containment-outcome playbooks)."
        ),
        "trigger_config": {
            "alert_type": "pfsense_firewall_port_scan",
            "min_severity": "medium",
        },
        "steps": [
            {"action": "enrich_context"},
            {"action": "monitor"},
        ],
    },
    {
        "id": CORE_V1_PFSENSE_PORT_SCAN_CONTAINMENT_ID,
        "name": "pfSense Port Scan Containment",
        "description": (
            "Contain high-confidence pfSense firewall port scan activity with "
            "enriched context and approval-gated IP blocking."
        ),
        "trigger_config": {
            "alert_type": "pfsense_firewall_port_scan",
            "min_severity": "high",
        },
        "steps": [
            {"action": "flag_high_priority"},
            {"action": "enrich_context"},
            {
                "action": "require_approval",
                "risk_level": "high",
                "expires_in_minutes": 30,
                "reason": "High-confidence pfSense port scan detected — approve IP block",
            },
            {"action": "block_ip", "params": {"source_ip": "{{alert.source_ip}}"}},
            {"action": "notify_slack", "params": {"message": "{{alert.message}}"}},
        ],
    },
    {
        "id": CORE_V1_PFSENSE_SUSPICIOUS_ALLOW_CONTAINMENT_ID,
        "name": "pfSense Suspicious Allow Containment",
        "description": (
            "Contain pfSense firewall allow events reaching sensitive destination "
            "ports with enriched context and approval-gated IP blocking."
        ),
        "trigger_config": {
            "alert_type": "pfsense_firewall_suspicious_allow",
            "min_severity": "high",
        },
        "steps": [
            {"action": "flag_high_priority"},
            {"action": "enrich_context"},
            {
                "action": "require_approval",
                "risk_level": "high",
                "expires_in_minutes": 30,
                "reason": "pfSense allowed inbound traffic to a sensitive port — approve IP block",
            },
            {"action": "block_ip", "params": {"source_ip": "{{alert.source_ip}}"}},
            {"action": "notify_slack", "params": {"message": "{{alert.message}}"}},
        ],
    },
)


def validate_core_playbook_pack_v1() -> list[str]:
    errors: list[str] = []
    for item in CORE_PLAYBOOK_PACK_V1:
        errors.extend(validate_playbook_steps(item["steps"]))
    return errors


def seed_core_playbook_pack_v1(conn, *, enabled: bool = True) -> list[str]:
    """
    Insert pack definitions that are not already present. Returns inserted playbook IDs.
    """
    inserted: list[str] = []
    for item in CORE_PLAYBOOK_PACK_V1:
        if get_playbook_definition(conn, item["id"]) is not None:
            continue
        create_playbook_definition(
            conn,
            item["id"],
            item["name"],
            steps=item["steps"],
            trigger_config=item["trigger_config"],
            enabled=enabled,
            description=item.get("description"),
        )
        inserted.append(item["id"])
    return inserted
