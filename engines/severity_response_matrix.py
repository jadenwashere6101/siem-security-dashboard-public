from __future__ import annotations

from typing import Any

from core.notification_policy_service import evaluate_notification_policy
from core.notification_policy_store import get_effective_notification_policy
from core.playbook_store import list_enabled_playbook_definitions
from engines.detection_config import get_all_effective_detection_rules


_RULE_METADATA: dict[str, dict[str, Any]] = {
    "failed_login_threshold": {
        "default_severity": "high",
        "maximum_severity": "high",
        "source": "bank_app",
        "source_type": "custom",
        "escalation_conditions": "Fixed High detector; repeated failed logins remain an investigation signal until correlated with stronger evidence.",
        "why": "Repeated failed authentication attempts are malicious, but they do not prove account compromise.",
    },
    "port_scan_threshold": {
        "default_severity": "medium",
        "maximum_severity": "high",
        "source": "bank_app",
        "source_type": "custom",
        "escalation_conditions": "Escalates through corroborating reputation or playbook context, but does not become Critical on scan activity alone.",
        "why": "Internet reconnaissance alone does not prove compromise.",
    },
    "password_spraying_threshold": {
        "default_severity": "high",
        "maximum_severity": "high",
        "source": "bank_app",
        "source_type": "custom",
        "escalation_conditions": "Threshold-based High detector; successful authentication evidence is handled by successful_login_after_spray instead of this rule.",
        "why": "Credential attack activity without a successful login is serious, but it is not a likely-compromise signal by itself.",
    },
    "http_error_threshold": {
        "default_severity": "medium",
        "maximum_severity": "high",
        "source": "nginx",
        "source_type": "web_log",
        "escalation_conditions": "Can contribute to higher-confidence correlation rules when paired with other telemetry from the same source IP.",
        "why": "Repeated application errors can indicate attack pressure, but errors alone do not prove a compromise path succeeded.",
    },
    "application_exception_threshold": {
        "default_severity": "medium",
        "maximum_severity": "high",
        "source": "azure_insights",
        "source_type": "cloud_api",
        "escalation_conditions": "Can contribute to higher-confidence correlation rules, but standalone exceptions remain investigation-only.",
        "why": "Application exceptions are useful attack evidence, but they do not by themselves prove successful compromise.",
    },
    "app_insights_unauthorized_access_threshold": {
        "default_severity": "high",
        "maximum_severity": "high",
        "source": "azure_insights",
        "source_type": "cloud_api",
        "escalation_conditions": "Threshold-based High detector for repeated 401/403 application responses; it does not bypass the platform's successful-authentication bar for Critical.",
        "why": "Application-tier authorization failures indicate probing or abuse, not confirmed access.",
    },
    "high_request_rate_threshold": {
        "default_severity": "medium",
        "maximum_severity": "high",
        "source": "nginx",
        "source_type": "web_log",
        "escalation_conditions": "Can contribute to correlation-driven High alerts when paired with matching application signals.",
        "why": "High request volume can be abusive or malicious, but traffic rate alone does not establish compromise.",
    },
    "successful_login_after_spray": {
        "default_severity": "critical",
        "maximum_severity": "critical",
        "source": "bank_app",
        "source_type": "custom",
        "escalation_conditions": "Requires at least 5 distinct failed-login usernames before a successful login within the configured correlation windows.",
        "why": "Successful authentication after coordinated credential attacks is a likely-compromise indicator requiring immediate human review.",
    },
    "honeypot_env_probe_threshold": {
        "default_severity": "high",
        "maximum_severity": "high",
        "source": "honeypot",
        "source_type": "honeypot",
        "escalation_conditions": "Threshold-based High detector; remains investigation and containment-eligible without becoming Critical.",
        "why": "Deliberate probing of sensitive honeypot paths is hostile, but it does not prove a production compromise occurred.",
    },
    "honeypot_admin_probe_threshold": {
        "default_severity": "medium",
        "maximum_severity": "medium",
        "source": "honeypot",
        "source_type": "honeypot",
        "escalation_conditions": "Fixed Medium detector; corroborating evidence must come from other rules.",
        "why": "Admin-path probing is suspicious, but a single probe is not enough to justify High or Critical severity on its own.",
    },
    "honeypot_scanner_detected": {
        "default_severity": "medium",
        "maximum_severity": "medium",
        "source": "honeypot",
        "source_type": "honeypot",
        "escalation_conditions": "Fixed Medium detector; supports analyst review and correlation, not containment by itself.",
        "why": "Commodity scanning is meaningful telemetry, but scanner activity alone does not imply compromise.",
    },
    "honeypot_credential_stuffing_threshold": {
        "default_severity": "high",
        "maximum_severity": "high",
        "source": "honeypot",
        "source_type": "honeypot",
        "escalation_conditions": "Threshold-based High detector; no standalone Critical path without successful-authentication evidence.",
        "why": "Credential-stuffing against the honeypot is high-confidence malicious behavior, but not a likely-compromise signal for production systems.",
    },
    "pfsense_firewall_repeated_deny": {
        "default_severity": "low",
        "maximum_severity": "high",
        "source": "pfsense",
        "source_type": "firewall",
        "escalation_conditions": "Starts Low, rises to Medium/High on volume, outbound context, or elevated reputation.",
        "why": "Blocked activity indicates malicious intent or scanning, but blocked traffic alone does not prove successful access.",
    },
    "pfsense_firewall_port_scan": {
        "default_severity": "medium",
        "maximum_severity": "high",
        "source": "pfsense",
        "source_type": "firewall",
        "escalation_conditions": "Escalates from Medium to High on breadth, repetition, or elevated reputation.",
        "why": "Port-scanning is strong reconnaissance evidence, but reconnaissance alone is not a likely-compromise signal.",
    },
    "pfsense_firewall_noisy_source": {
        "default_severity": "low",
        "maximum_severity": "low",
        "source": "pfsense",
        "source_type": "firewall",
        "escalation_conditions": "Suppression-focused detector; does not escalate beyond Low in the current design.",
        "why": "This rule exists to track noisy sources operationally, not to represent a compromise indicator.",
    },
    "pfsense_firewall_suspicious_allow": {
        "default_severity": "medium",
        "maximum_severity": "high",
        "source": "pfsense",
        "source_type": "firewall",
        "escalation_conditions": "Escalates to High on repetition, elevated reputation, or corroborating multi-port access.",
        "why": "Allowed traffic to sensitive ports is important, but it becomes High only when corroborating context suggests meaningful risk.",
    },
    "correlated_activity": {
        "default_severity": "high",
        "maximum_severity": "high",
        "source": "legacy",
        "source_type": "legacy",
        "escalation_conditions": "Multi-source correlation stays High; Critical is reserved for likely-compromise evidence.",
        "why": "Cross-source suspicious activity is high-confidence malicious behavior, but not proof that compromise succeeded.",
    },
    "web_to_app_attack_pattern": {
        "default_severity": "high",
        "maximum_severity": "high",
        "source": "nginx",
        "source_type": "web_log",
        "escalation_conditions": "Requires both nginx web pressure and bank_app authentication pressure from the same IP within 10 minutes.",
        "why": "Correlated attack-chain evidence without proof of successful compromise belongs at High, not Critical.",
    },
    "spray_then_success_pattern": {
        "default_severity": "high",
        "maximum_severity": "high",
        "source": "bank_app",
        "source_type": "custom",
        "escalation_conditions": "Requires both password_spraying_threshold and successful_login_after_spray to already exist for the same IP.",
        "why": "This rule corroborates an existing likely-compromise signal, but the canonical Critical decision belongs to successful_login_after_spray.",
    },
    "cloud_app_error_pattern": {
        "default_severity": "high",
        "maximum_severity": "high",
        "source": "azure_insights",
        "source_type": "cloud_api",
        "escalation_conditions": "Requires matching cloud and nginx error activity from the same IP within the rule window.",
        "why": "Cross-platform error correlations can be malicious, but they still require analyst validation before being treated as compromise evidence.",
    },
    "azure_auth_abuse_exception_correlation": {
        "default_severity": "high",
        "maximum_severity": "high",
        "source": "azure_insights",
        "source_type": "cloud_api",
        "escalation_conditions": "Requires both Azure authentication-abuse pressure and an Application Insights exception spike from the same IP within the rule window.",
        "why": "Correlated auth abuse and application instability is a stronger signal, but still not proof of a successful compromise.",
    },
}

_CORRELATION_RULES: tuple[dict[str, Any], ...] = (
    {"rule_id": "correlated_activity", "display_name": "Correlated Activity", "active": True},
    {"rule_id": "web_to_app_attack_pattern", "display_name": "Web-to-App Attack Pattern", "active": True},
    {"rule_id": "spray_then_success_pattern", "display_name": "Spray-Then-Success Pattern", "active": True},
    {"rule_id": "cloud_app_error_pattern", "display_name": "Cloud/App Error Pattern", "active": True},
    {"rule_id": "azure_auth_abuse_exception_correlation", "display_name": "Azure Auth Abuse Exception Correlation", "active": True},
)

_SEVERITY_ORDER = ("low", "medium", "high", "critical")


def build_severity_response_matrix(conn) -> dict[str, Any]:
    policy = get_effective_notification_policy()
    playbooks = list_enabled_playbook_definitions(conn)
    effective_rules = list(get_all_effective_detection_rules()) + list(_CORRELATION_RULES)
    rows = [
        _build_rule_row(rule, playbooks=playbooks, policy=policy)
        for rule in effective_rules
        if rule.get("active", True)
    ]
    rows.sort(key=lambda item: (item["default_severity_rank"], item["display_name"].lower()))

    severity_definitions = [
        _build_severity_definition(severity, rows=rows, policy=policy)
        for severity in _SEVERITY_ORDER
    ]
    return {
        "page_statement": "This page explains how the SIEM behaves. It is not another configuration interface.",
        "links": {
            "detection_rules_section_id": "detection-rules",
            "notification_policy_section_id": "notification-policy",
        },
        "severity_definitions": severity_definitions,
        "rules": rows,
    }


def _build_rule_row(rule: dict[str, Any], *, playbooks: list[dict[str, Any]], policy: dict[str, Any]) -> dict[str, Any]:
    rule_id = rule["rule_id"]
    metadata = _RULE_METADATA[rule_id]
    matched_playbooks = [
        playbook for playbook in playbooks if playbook.get("trigger_config", {}).get("alert_type") == rule_id
    ]
    notification_decision = evaluate_notification_policy(
        policy,
        event_kind="alert",
        severity=metadata["default_severity"],
        source=metadata["source"],
        source_type=metadata["source_type"],
    )
    creates_incident_text = _creates_incident_text(
        default_severity=metadata["default_severity"],
        maximum_severity=metadata["maximum_severity"],
    )
    return {
        "rule_id": rule_id,
        "display_name": rule.get("display_name") or rule_id,
        "default_severity": metadata["default_severity"],
        "default_severity_rank": _severity_rank(metadata["default_severity"]),
        "maximum_severity": metadata["maximum_severity"],
        "source": metadata["source"],
        "source_type": metadata["source_type"],
        "parameters": rule.get("parameters") or {},
        "description": rule.get("description"),
        "escalation_conditions": metadata["escalation_conditions"],
        "creates_incident": creates_incident_text,
        "notification_behavior": _notification_behavior_text(
            notification_decision,
            policy=policy,
            default_severity=metadata["default_severity"],
        ),
        "response_playbook_behavior": _playbook_behavior_text(matched_playbooks),
        "approval_required": any(
            step.get("action") == "require_approval"
            for playbook in matched_playbooks
            for step in playbook.get("steps") or []
        ),
        "why": metadata["why"],
        "playbooks": [
            {
                "id": playbook["id"],
                "name": playbook["name"],
                "min_severity": playbook.get("trigger_config", {}).get("min_severity"),
                "steps": [step.get("action") for step in playbook.get("steps") or []],
            }
            for playbook in matched_playbooks
        ],
    }


def _severity_rank(value: str) -> int:
    try:
        return _SEVERITY_ORDER.index(str(value or "").lower())
    except ValueError:
        return len(_SEVERITY_ORDER)


def _creates_incident_text(*, default_severity: str, maximum_severity: str) -> str:
    default_normalized = str(default_severity or "").lower()
    maximum_normalized = str(maximum_severity or "").lower()
    if default_normalized in {"high", "critical"}:
        return "Yes — alerts at this default severity create or link incidents."
    if maximum_normalized in {"high", "critical"}:
        return "Only after escalation to High or Critical."
    return "No — incident creation is not expected for this rule."


def _notification_behavior_text(
    decision: dict[str, Any],
    *,
    policy: dict[str, Any],
    default_severity: str,
) -> str:
    if decision.get("should_notify"):
        destination = decision.get("destination") or "configured destination"
        route_key = decision.get("route_key") or "route"
        if str(default_severity).lower() == "critical":
            return (
                f"Immediate Slack alert attempt to {destination} via {route_key} when policy gates pass; "
                "attempted before any approval step."
            )
        return f"Slack-eligible via {route_key} to {destination} when current policy gates pass."

    reason = decision.get("reason") or "blocked"
    if reason == "source_not_routed":
        return "Not currently Slack-routed by notification policy at this severity."
    if reason == "below_minimum_severity":
        return (
            f"Currently suppressed by the notification policy minimum severity "
            f"({policy.get('minimum_severity') or 'unknown'})."
        )
    if reason == "slack_disabled":
        return "Slack delivery is globally disabled by the current notification policy."
    if reason == "alerts_disabled":
        return "Alert notifications are disabled by the current notification policy."
    return f"Currently suppressed by notification policy: {reason}."


def _playbook_behavior_text(playbooks: list[dict[str, Any]]) -> str:
    if not playbooks:
        return "No enabled response playbook currently matches this rule."
    parts = []
    for playbook in playbooks:
        actions = " -> ".join(step.get("action") or "unknown" for step in playbook.get("steps") or [])
        min_severity = playbook.get("trigger_config", {}).get("min_severity") or "any"
        parts.append(f"{playbook['name']} (min {min_severity}): {actions}")
    return " | ".join(parts)


def _build_severity_definition(
    severity: str,
    *,
    rows: list[dict[str, Any]],
    policy: dict[str, Any],
) -> dict[str, Any]:
    supported = [
        row["rule_id"]
        for row in rows
        if row["default_severity"] == severity or row["maximum_severity"] == severity
    ]
    if severity == "low":
        return {
            "severity": "low",
            "definition": "Expected or background activity with dashboard visibility only.",
            "analyst_expectation": "Monitor for trends and corroboration; no urgent response expected.",
            "incident_behavior": "Does not create incidents by default.",
            "slack_eligibility_timing": _severity_policy_summary(severity, policy),
            "approval_requirement": "No approval-gated containment expected at Low.",
            "containment_behavior": "No automatic containment.",
            "supported_detection_ids": supported,
        }
    if severity == "medium":
        return {
            "severity": "medium",
            "definition": "Credible activity requiring analyst review.",
            "analyst_expectation": "Investigate context and watch for corroborating escalation signals.",
            "incident_behavior": "Does not create incidents unless another rule escalates the evidence to High or Critical.",
            "slack_eligibility_timing": _severity_policy_summary(severity, policy),
            "approval_requirement": "Approval is not expected at Medium in the current pack.",
            "containment_behavior": "Investigation-only unless another rule escalates the same source.",
            "supported_detection_ids": supported,
        }
    if severity == "high":
        return {
            "severity": "high",
            "definition": "High-confidence malicious activity requiring prompt investigation.",
            "analyst_expectation": "Review quickly, validate scope, and expect incident creation or linkage.",
            "incident_behavior": "Creates or links incidents at priority P2.",
            "slack_eligibility_timing": _severity_policy_summary(severity, policy),
            "approval_requirement": "Containment requires an explicit require_approval step where a playbook defines one.",
            "containment_behavior": "Containment can be approval-gated; investigation-only playbooks remain possible.",
            "supported_detection_ids": supported,
        }
    return {
        "severity": "critical",
        "definition": "Highest-confidence attack-chain or likely-compromise signal requiring immediate human review.",
        "analyst_expectation": "Treat as urgent, validate quickly, and expect immediate notification before any approval gate.",
        "incident_behavior": "Creates or links incidents at priority P1, and upgrades linked lower open incidents to Critical/P1.",
        "slack_eligibility_timing": _severity_policy_summary(severity, policy),
        "approval_requirement": "Containment remains approval-gated where a playbook requires approval; Critical does not imply automatic blocking.",
        "containment_behavior": "Immediate human review with approval-gated containment for supported playbooks.",
        "supported_detection_ids": supported,
    }


def _severity_policy_summary(severity: str, policy: dict[str, Any]) -> str:
    if not policy.get("slack_enabled"):
        return "Slack is currently disabled globally by notification policy."
    threshold = str(policy.get("minimum_severity") or "high").lower()
    destination_summary = (
        f"pfSense → {policy.get('pfsense_destination')}; "
        f"Honeypot → {policy.get('honeypot_destination')}; "
        f"Critical cross-source → {policy.get('critical_cross_source_destination')}"
    )
    if severity == "critical":
        return (
            f"Eligible immediately when alert or incident notifications are enabled. "
            f"Current minimum severity: {threshold}. Destinations: {destination_summary}."
        )
    return (
        f"Eligible only when current policy gates pass (minimum severity {threshold}, "
        f"event notifications enabled, and a configured source route exists). Destinations: {destination_summary}."
    )
