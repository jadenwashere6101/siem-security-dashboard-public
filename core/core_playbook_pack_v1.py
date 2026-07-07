"""
Core Playbook Pack v1 definitions.

Five production playbooks authored as data for `playbook_definitions`. Notification
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

CORE_PLAYBOOK_PACK_V1: tuple[dict[str, Any], ...] = (
    {
        "id": CORE_V1_BRUTE_FORCE_CONTAINMENT_ID,
        "name": "Brute Force Containment",
        "description": (
            "Escalate sustained failed-login patterns with approval-gated IP containment."
        ),
        "trigger_config": {
            "alert_type": "failed_login_threshold",
            "min_severity": "high",
        },
        "steps": [
            {"action": "flag_high_priority"},
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
            "Investigate password-spray activity without automatic blocking."
        ),
        "trigger_config": {"alert_type": "password_spraying_threshold"},
        "steps": [
            {"action": "monitor"},
            {
                "action": "notify_slack",
                "params": {"message": "{{alert.reputation_summary}}"},
            },
        ],
    },
    {
        "id": CORE_V1_SPRAY_SUCCESS_RESPONSE_ID,
        "name": "Successful Login After Spray Response",
        "description": (
            "Fastest approval-gated containment for post-spray successful login signals."
        ),
        "trigger_config": {
            "alert_type": "successful_login_after_spray",
            "min_severity": "critical",
        },
        "steps": [
            {"action": "flag_high_priority"},
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
            "Approval-gated containment for alerts from known-malicious source IPs."
        ),
        "trigger_config": {
            "reputation_score_min": 80,
            "min_severity": "medium",
        },
        "steps": [
            {"action": "flag_high_priority"},
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
        "name": "Reputation-Only Investigation",
        "description": (
            "Low-bar reputation nudge for alerts worth reviewing without escalation."
        ),
        "trigger_config": {
            "reputation_score_min": 40,
            "min_severity": "low",
        },
        "steps": [
            {"action": "monitor"},
            {
                "action": "notify_slack",
                "params": {"message": "{{alert.reputation_summary}}"},
            },
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
