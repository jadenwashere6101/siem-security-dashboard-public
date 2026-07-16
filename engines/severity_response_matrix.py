from __future__ import annotations

from typing import Any

from core.notification_policy_service import evaluate_notification_policy
from core.notification_policy_store import get_effective_notification_policy
from core.playbook_store import list_enabled_playbook_definitions
from engines.detection_config import get_all_effective_detection_rules
from engines.detection_rule_catalog import (
    DetectionRuleCatalogRecord,
    VALID_SEVERITIES,
    get_correlation_rule_catalog_records,
    get_detection_rule_catalog_record,
)


_SEVERITY_ORDER = VALID_SEVERITIES


def build_severity_response_matrix(conn) -> dict[str, Any]:
    policy = get_effective_notification_policy()
    playbooks = list_enabled_playbook_definitions(conn)
    effective_base_rules = {
        rule["rule_id"]: rule
        for rule in get_all_effective_detection_rules()
        if rule.get("active", True)
    }

    records: list[DetectionRuleCatalogRecord] = [
        get_detection_rule_catalog_record(rule_id)
        for rule_id in effective_base_rules.keys()
    ] + get_correlation_rule_catalog_records()

    rows = [
        _build_rule_row(
            record,
            runtime_rule=effective_base_rules.get(record.rule_id),
            playbooks=playbooks,
            policy=policy,
        )
        for record in records
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


def _build_rule_row(
    record: DetectionRuleCatalogRecord,
    *,
    runtime_rule: dict[str, Any] | None,
    playbooks: list[dict[str, Any]],
    policy: dict[str, Any],
) -> dict[str, Any]:
    matched_playbooks = [
        playbook for playbook in playbooks if playbook.get("trigger_config", {}).get("alert_type") == record.rule_id
    ]
    primary_source = record.matrix_source or (
        record.source_applicability.allowed_sources[0].source,
        record.source_applicability.allowed_sources[0].source_type,
    )
    notification_decision = evaluate_notification_policy(
        policy,
        event_kind="alert",
        severity=record.default_severity,
        source=primary_source[0],
        source_type=primary_source[1],
    )
    creates_incident_text = _creates_incident_text(
        default_severity=record.default_severity,
        maximum_severity=record.maximum_severity,
    )
    return {
        "rule_id": record.rule_id,
        "display_name": record.display_name,
        "default_severity": record.default_severity,
        "default_severity_rank": _severity_rank(record.default_severity),
        "maximum_severity": record.maximum_severity,
        "source": primary_source[0],
        "source_type": primary_source[1],
        "parameters": (runtime_rule or {}).get("parameters") or {},
        "description": runtime_rule.get("description") if runtime_rule else record.description,
        "escalation_conditions": record.escalation_conditions,
        "creates_incident": creates_incident_text,
        "notification_behavior": _notification_behavior_text(
            notification_decision,
            policy=policy,
            default_severity=record.default_severity,
        ),
        "response_playbook_behavior": _playbook_behavior_text(matched_playbooks),
        "approval_required": any(
            step.get("action") == "require_approval"
            for playbook in matched_playbooks
            for step in playbook.get("steps") or []
        ),
        "why": record.why,
        "investigation_guidance": record.investigation_guidance,
        "supported_evidence": list(record.supported_evidence),
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
