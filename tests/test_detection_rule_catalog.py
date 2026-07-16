from unittest.mock import patch

import pytest

import engines.detection_config as detection_config
import engines.severity_response_matrix as severity_response_matrix
import helpers.enrichment_helpers as enrichment_helpers
from engines.correlation_engine import IMPLEMENTED_CORRELATION_RULE_IDS
from engines.detection_rule_catalog import (
    BANK_APP,
    DetectionRuleCatalogRecord,
    MitreMapping,
    SourceApplicability,
    get_base_rule_catalog_records,
    get_correlation_rule_catalog_records,
    get_detection_rule_catalog_record,
    get_rule_mitre_mapping,
    validate_detection_rule_catalog,
)
from engines.ingest_engine import IMPLEMENTED_BASE_DETECTION_RULE_IDS


def _notification_policy():
    return {
        "slack_enabled": True,
        "alerts_enabled": True,
        "minimum_severity": "high",
        "pfsense_destination": "#soc-pfsense",
        "honeypot_destination": "#soc-honeypot",
        "critical_cross_source_destination": "#soc-critical",
    }


def _future_base_record():
    return DetectionRuleCatalogRecord(
        rule_id="future_detection_rule",
        display_name="Future Detection Rule",
        description="Future test detector.",
        family="future",
        rule_type="base",
        default_severity="medium",
        maximum_severity="high",
        escalation_conditions="Escalates when corroborated.",
        source_applicability=SourceApplicability("source_specific", (BANK_APP,)),
        mitre=MitreMapping("T0001", "Future Technique", "Impact"),
        supported_evidence=("future_event",),
        investigation_guidance="Review future test evidence.",
        why="Future test rule exists to prove automatic consumer inclusion.",
    )


def test_catalog_validates_current_runtime_inventories():
    validate_detection_rule_catalog(
        implemented_base_rule_ids=set(IMPLEMENTED_BASE_DETECTION_RULE_IDS),
        implemented_correlation_rule_ids=set(IMPLEMENTED_CORRELATION_RULE_IDS),
    )


def test_catalog_contains_allow_after_deny_and_reserved_legacy_mapping():
    assert "pfsense_firewall_allow_after_deny" in {
        record.rule_id for record in get_base_rule_catalog_records()
    }
    assert "azure_auth_abuse_exception_correlation" in {
        record.rule_id for record in get_correlation_rule_catalog_records()
    }

    legacy = get_detection_rule_catalog_record("suspicious_ip_reputation")
    assert legacy.implementation_state == "reserved"
    assert get_rule_mitre_mapping("suspicious_ip_reputation") == {
        "mitre_technique_id": "T1595",
        "mitre_technique_name": "Active Scanning",
        "mitre_tactic": "Reconnaissance",
    }


def test_catalog_validation_rejects_missing_implemented_correlation_inventory():
    with pytest.raises(ValueError, match="Catalog rule\\(s\\) marked implemented without runtime implementation"):
        validate_detection_rule_catalog(
            implemented_base_rule_ids=set(IMPLEMENTED_BASE_DETECTION_RULE_IDS),
            implemented_correlation_rule_ids=set(),
        )


def test_duplicate_consumer_registries_are_removed():
    assert not hasattr(severity_response_matrix, "_RULE_METADATA")
    assert not hasattr(severity_response_matrix, "_CORRELATION_RULES")
    assert not hasattr(enrichment_helpers, "MITRE_ATTACK_MAPPINGS")


def test_detection_rules_and_matrix_inventories_stay_catalog_synchronized():
    runtime_rules = list(detection_config.get_detection_rule_defaults().values())

    with patch.object(
        severity_response_matrix,
        "get_all_effective_detection_rules",
        return_value=runtime_rules,
    ), patch.object(
        severity_response_matrix,
        "get_effective_notification_policy",
        return_value=_notification_policy(),
    ), patch.object(
        severity_response_matrix,
        "list_enabled_playbook_definitions",
        return_value=[],
    ):
        payload = severity_response_matrix.build_severity_response_matrix(conn=None)

    row_ids = {row["rule_id"] for row in payload["rules"]}
    assert set(detection_config.get_detection_rule_defaults()) == set(IMPLEMENTED_BASE_DETECTION_RULE_IDS)
    assert row_ids == set(IMPLEMENTED_BASE_DETECTION_RULE_IDS) | set(IMPLEMENTED_CORRELATION_RULE_IDS)


def test_future_base_rule_reaches_detection_rules_defaults_without_local_inventory_edit():
    future_record = _future_base_record()
    existing_records = get_base_rule_catalog_records()
    original_get_rule_parameter_defaults = detection_config.get_rule_parameter_defaults

    with patch.object(
        detection_config,
        "get_base_rule_catalog_records",
        return_value=[*existing_records, future_record],
    ), patch.object(
        detection_config,
        "get_rule_parameter_defaults",
        side_effect=lambda rule_id: {"threshold": 9, "window_minutes": 15}
        if rule_id == future_record.rule_id
        else original_get_rule_parameter_defaults(rule_id),
    ):
        defaults = detection_config.get_detection_rule_defaults()

    assert defaults[future_record.rule_id]["display_name"] == "Future Detection Rule"
    assert defaults[future_record.rule_id]["parameters"] == {"threshold": 9, "window_minutes": 15}


def test_future_base_rule_reaches_severity_matrix_without_local_matrix_registry_edit():
    future_record = _future_base_record()
    runtime_rule = {
        "rule_id": future_record.rule_id,
        "display_name": future_record.display_name,
        "description": future_record.description,
        "parameters": {"threshold": 9, "window_minutes": 15},
        "active": True,
    }

    with patch.object(
        severity_response_matrix,
        "get_all_effective_detection_rules",
        return_value=[runtime_rule],
    ), patch.object(
        severity_response_matrix,
        "get_detection_rule_catalog_record",
        return_value=future_record,
    ), patch.object(
        severity_response_matrix,
        "get_correlation_rule_catalog_records",
        return_value=[],
    ), patch.object(
        severity_response_matrix,
        "get_effective_notification_policy",
        return_value=_notification_policy(),
    ), patch.object(
        severity_response_matrix,
        "list_enabled_playbook_definitions",
        return_value=[],
    ):
        payload = severity_response_matrix.build_severity_response_matrix(conn=None)

    rows = {row["rule_id"]: row for row in payload["rules"]}
    assert rows[future_record.rule_id]["display_name"] == "Future Detection Rule"
    assert rows[future_record.rule_id]["default_severity"] == "medium"
