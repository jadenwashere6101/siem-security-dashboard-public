"""Focused tests for Version 3 Sigma subset import (Phases 1-4)."""
from __future__ import annotations

import os
from unittest.mock import patch

import psycopg2
from psycopg2 import sql
import pytest

import siem_backend
from engines.detection_simulator import (
    SIMULATION_MODE_SIGMA_SUBSET_IMPORT,
    SimulationValidationError,
    run_detection_simulation,
)
from engines.sigma_playground import (
    SIGMA_SUBSET_COMPATIBILITY_NOTE,
    compile_sigma_rule_to_temporary_rule,
    map_field_alias,
    map_logsource,
    parse_sigma_yaml,
)
from tests.test_detection_simulator import (
    RollbackOnlyConnection,
    count_rows,
    logged_in_role,
    run_sim,
    run_temp_sim,
)


VALID_BANK_APP_SIGMA = """
title: Bank failed login subset
id: 11111111-1111-1111-1111-111111111111
status: experimental
description: Strict subset example
author: playground
date: 2026/07/13
logsource:
  product: bank_app
level: high
tags:
  - attack.t1110
  - attack.t1110.001
  - credential_access
detection:
  selection_type:
    EventType: failed_login
  selection_user:
    UserName|contains: admin
  condition: selection_type and selection_user
"""

BANK_APP_EVENTS = [
    {
        "event_type": "failed_login",
        "severity": "high",
        "source_ip": "203.0.113.50",
        "message": "failed",
        "app_name": "bank",
        "environment": "prod",
        "username": "admin_user",
    },
    {
        "event_type": "failed_login",
        "severity": "high",
        "source_ip": "203.0.113.50",
        "message": "failed",
        "app_name": "bank",
        "environment": "prod",
        "username": "alice",
    },
]


def run_sigma_sim(*, sigma_yaml=VALID_BANK_APP_SIGMA, sample_events=None, **kwargs):
    if sample_events is None:
        sample_events = BANK_APP_EVENTS
    with siem_backend.app.app_context():
        return run_detection_simulation(
            simulation_mode=SIMULATION_MODE_SIGMA_SUBSET_IMPORT,
            sigma_yaml=sigma_yaml,
            sample_events=sample_events,
            **kwargs,
        )


# --- Phase 1 contract -------------------------------------------------------


def test_sigma_contract_rejects_temporary_rule_alongside_sigma_yaml():
    with pytest.raises(SimulationValidationError, match="temporary_rule is not allowed"):
        run_detection_simulation(
            simulation_mode="sigma_subset_import",
            sigma_yaml=VALID_BANK_APP_SIGMA,
            temporary_rule={"source": "bank_app"},
            sample_events=BANK_APP_EVENTS,
        )


def test_sigma_contract_rejects_rule_id_alongside_sigma_mode():
    with pytest.raises(SimulationValidationError, match="rule_id is not allowed"):
        run_detection_simulation(
            simulation_mode="sigma_subset_import",
            sigma_yaml=VALID_BANK_APP_SIGMA,
            rule_id="failed_login_threshold",
            sample_events=BANK_APP_EVENTS,
        )


def test_sigma_contract_rejects_missing_sigma_yaml():
    with pytest.raises(SimulationValidationError, match="sigma_yaml is required"):
        run_detection_simulation(
            simulation_mode="sigma_subset_import",
            sample_events=BANK_APP_EVENTS,
        )


def test_existing_production_mode_rejects_sigma_yaml():
    with pytest.raises(SimulationValidationError, match="sigma_yaml is only allowed"):
        run_detection_simulation(
            simulation_mode="existing_production_rule",
            source="bank_app",
            rule_id="failed_login_threshold",
            input_format="json",
            json_events=BANK_APP_EVENTS,
            sigma_yaml=VALID_BANK_APP_SIGMA,
        )


def test_temporary_mode_rejects_sigma_yaml():
    with pytest.raises(SimulationValidationError, match="sigma_yaml is not allowed"):
        run_detection_simulation(
            simulation_mode="temporary_playground_rule",
            temporary_rule={
                "source": "bank_app",
                "source_type": "custom",
                "input_format": "json_array",
                "condition": {"field": "event_type", "operator": "equals", "value": "failed_login"},
                "aggregation": {"type": "count", "group_by_field": "source_ip"},
                "threshold": 1,
                "window_minutes": 15,
                "severity": "high",
            },
            sample_events=BANK_APP_EVENTS,
            sigma_yaml=VALID_BANK_APP_SIGMA,
        )


def test_unsupported_simulation_mode_is_rejected():
    with pytest.raises(SimulationValidationError, match="Unsupported simulation_mode"):
        run_detection_simulation(simulation_mode="custom_dsl_engine")


def test_predicate_tree_is_accepted_on_temporary_rule_model(postgres_db):
    conn, _cur = postgres_db
    with patch("engines.detection_simulator.get_db_connection", return_value=RollbackOnlyConnection(conn)):
        result = run_temp_sim(
            temporary_rule={
                "threshold": 1,
                "condition": {
                    "all": [
                        {"field": "event_type", "operator": "equals", "value": "failed_login"},
                        {"field": "username", "operator": "contains", "value": "admin"},
                    ]
                },
            },
            sample_events=BANK_APP_EVENTS,
        )
    assert result["simulation_mode"] == "temporary_playground_rule"
    assert result["stages"]["detection_evaluation"]["matching_event_count"] == 1
    assert result["stages"]["alert_preview"]["alert"] is not None


# --- Phase 2 YAML + validation ----------------------------------------------


def test_valid_sigma_rule_compiles():
    compiled = compile_sigma_rule_to_temporary_rule(VALID_BANK_APP_SIGMA)
    assert compiled["source"] == "bank_app"
    assert compiled["source_type"] == "custom"
    assert compiled["severity"] == "high"
    assert compiled["sigma_subset"] is True
    assert compiled["rule_provenance"] == "sigma_subset_import"
    assert compiled["attack_tags"] == ["T1110", "T1110.001"]
    assert "credential_access" in compiled["tags"]
    assert compiled["condition"]["all"]


def test_malformed_yaml_is_rejected():
    with pytest.raises(SimulationValidationError) as exc:
        parse_sigma_yaml("title: [\n  - broken")
    assert exc.value.details["class"] == "malformed_yaml"


def test_oversized_yaml_is_rejected():
    huge = "title: " + ("x" * (65 * 1024))
    with pytest.raises(SimulationValidationError) as exc:
        parse_sigma_yaml(huge)
    assert exc.value.details["class"] == "oversized_yaml"


def test_unsupported_modifier_is_rejected():
    yaml_text = """
title: Bad modifier
logsource:
  product: bank_app
detection:
  selection:
    UserName|re: admin.*
  condition: selection
"""
    with pytest.raises(SimulationValidationError) as exc:
        compile_sigma_rule_to_temporary_rule(yaml_text)
    assert exc.value.details["class"] == "unsupported_modifier"
    assert "re" in str(exc.value)


def test_wildcard_condition_is_rejected():
    yaml_text = """
title: Wildcard condition
logsource:
  product: bank_app
detection:
  selection:
    EventType: failed_login
  condition: 1 of selection*
"""
    with pytest.raises(SimulationValidationError) as exc:
        compile_sigma_rule_to_temporary_rule(yaml_text)
    assert exc.value.details["class"] == "unsupported_condition"


def test_correlation_construct_is_rejected():
    yaml_text = """
title: Correlation
correlation: something
logsource:
  product: bank_app
detection:
  selection:
    EventType: failed_login
  condition: selection
"""
    with pytest.raises(SimulationValidationError) as exc:
        compile_sigma_rule_to_temporary_rule(yaml_text)
    assert exc.value.details["class"] == "unsupported_construct"


def test_timeframe_syntax_is_rejected():
    yaml_text = """
title: Timeframe
logsource:
  product: bank_app
detection:
  timeframe: 5m
  selection:
    EventType: failed_login
  condition: selection
"""
    with pytest.raises(SimulationValidationError) as exc:
        compile_sigma_rule_to_temporary_rule(yaml_text)
    assert exc.value.details["class"] == "unsupported_construct"


def test_list_values_compile_to_in_list():
    yaml_text = """
title: List values
logsource:
  product: bank_app
detection:
  selection:
    EventType:
      - failed_login
      - login_failure
  condition: selection
"""
    compiled = compile_sigma_rule_to_temporary_rule(yaml_text)
    assert compiled["condition"] == {
        "field": "event_type",
        "operator": "in_list",
        "value": ["failed_login", "login_failure"],
    }


# --- Phase 3 mapping + compilation ------------------------------------------


def test_logsource_maps_unambiguously():
    mapped = map_logsource({"product": "nginx"})
    assert mapped["source"] == "nginx"
    assert mapped["source_type"] == "web_log"


def test_ambiguous_or_unknown_logsource_is_rejected():
    with pytest.raises(SimulationValidationError) as exc:
        map_logsource({"product": "windows", "service": "security"})
    assert exc.value.details["class"] == "ambiguous_logsource"


def test_field_alias_maps_for_source():
    assert map_field_alias("bank_app", "UserName") == "username"
    assert map_field_alias("pfsense", "dst_port") == "destination_port"


def test_unsupported_field_is_rejected():
    with pytest.raises(SimulationValidationError) as exc:
        map_field_alias("bank_app", "CommandLine")
    assert exc.value.details["class"] == "unsupported_field"


def test_boolean_condition_compiles_to_predicate_tree():
    yaml_text = """
title: Boolean
logsource:
  product: pfsense
detection:
  sel_block:
    Action: block
  sel_port:
    destination_port:
      - 22
      - 3389
  condition: sel_block and not sel_port
"""
    compiled = compile_sigma_rule_to_temporary_rule(yaml_text)
    assert compiled["source"] == "pfsense"
    assert compiled["condition"] == {
        "all": [
            {"field": "action", "operator": "equals", "value": "block"},
            {
                "not": {
                    "field": "destination_port",
                    "operator": "in_list",
                    "value": [22, 3389],
                }
            },
        ]
    }


def test_attack_tags_parsed_without_setting_mitre_execution_field():
    compiled = compile_sigma_rule_to_temporary_rule(VALID_BANK_APP_SIGMA)
    assert compiled["attack_tags"] == ["T1110", "T1110.001"]
    assert compiled["mitre_technique_id"] is None


# --- Phase 4 simulation reuse + safety --------------------------------------


def test_sigma_simulation_reuses_temporary_evaluator_and_stages(postgres_db):
    conn, _cur = postgres_db
    with patch("engines.detection_simulator.get_db_connection", return_value=RollbackOnlyConnection(conn)):
        result = run_sigma_sim()
    assert result["simulation_mode"] == "sigma_subset_import"
    assert result["sigma_subset_compatibility"] == SIGMA_SUBSET_COMPATIBILITY_NOTE
    assert result["normalized_internal_rule_preview"]["source"] == "bank_app"
    assert result["normalized_internal_rule_preview"]["evaluator"] == "temporary_playground_rule"
    assert result["normalized_internal_rule_preview"]["sigma_subset"] is True
    assert "not full Sigma" in result["sigma_subset_compatibility"]
    assert result["stages"]["parser"]["status"] == "succeeded"
    assert result["stages"]["detection_evaluation"]["matching_event_count"] == 1
    assert result["stages"]["alert_preview"]["status"] == "succeeded"
    assert result["stages"]["alert_preview"]["alert"] is not None
    assert result["stages"]["mitre_mapping"]["status"] == "succeeded"
    assert result["stages"]["soar_preview"]["status"] == "succeeded"
    assert result["stages"]["threshold_window_evaluation"]["pasted_event_only"] is True
    assert result["stages"]["threshold_window_evaluation"]["nothing_persisted"] is True


def test_sigma_simulation_zero_writes_and_no_external_calls(postgres_db):
    conn, cur = postgres_db
    guarded_tables = (
        "events",
        "alerts",
        "playbook_executions",
        "soar_response_decisions",
        "response_actions_queue",
        "incidents",
        "incident_alerts",
        "audit_log",
    )
    before_counts = {table: count_rows(cur, table) for table in guarded_tables}

    with patch("engines.detection_simulator.get_db_connection", return_value=RollbackOnlyConnection(conn)), patch(
        "core.ip_helpers.requests.get"
    ) as mock_get, patch("integrations.slack_adapter._post_slack_webhook") as mock_slack:
        result = run_sigma_sim()

    assert result["stages"]["alert_preview"]["alert"] is not None
    mock_get.assert_not_called()
    mock_slack.assert_not_called()
    after_counts = {table: count_rows(cur, table) for table in guarded_tables}
    assert after_counts == before_counts


def test_sigma_simulation_no_pending_row_visible_to_separate_connection(postgres_db):
    conn, cur = postgres_db
    cur.execute("SELECT current_schema()")
    schema_name = cur.fetchone()[0]

    with patch("engines.detection_simulator.get_db_connection", return_value=RollbackOnlyConnection(conn)):
        result = run_sigma_sim()

    assert result["stages"]["alert_preview"]["alert"] is not None
    dsn = os.getenv("SIEM_TEST_DATABASE_URL") or os.getenv("TEST_DATABASE_URL") or "dbname=postgres"
    worker_conn = psycopg2.connect(dsn)
    try:
        worker_cur = worker_conn.cursor()
        worker_cur.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema_name)))
        worker_cur.execute("SELECT COUNT(*) FROM playbook_executions WHERE status = 'pending'")
        assert worker_cur.fetchone()[0] == 0
        worker_cur.execute("SELECT COUNT(*) FROM response_actions_queue WHERE status = 'pending'")
        assert worker_cur.fetchone()[0] == 0
        worker_cur.execute(
            "SELECT COUNT(*) FROM alerts WHERE alert_type = %s",
            ("temporary_playground_rule",),
        )
        assert worker_cur.fetchone()[0] == 0
    finally:
        worker_conn.close()


def test_sigma_route_rejects_save_rule_key(client):
    with logged_in_role(client, "analyst"):
        response = client.post(
            "/detection-simulator/run",
            json={
                "simulation_mode": "sigma_subset_import",
                "sigma_yaml": VALID_BANK_APP_SIGMA,
                "sample_events": BANK_APP_EVENTS,
                "save_rule": True,
            },
        )
    assert response.status_code == 400
    payload = response.get_json()
    assert "save_rule" in payload["error"]


def test_sigma_route_returns_validation_details_for_bad_yaml(client):
    with logged_in_role(client, "analyst"):
        response = client.post(
            "/detection-simulator/run",
            json={
                "simulation_mode": "sigma_subset_import",
                "sigma_yaml": "title: [\nbroken",
                "sample_events": BANK_APP_EVENTS,
            },
        )
    assert response.status_code == 400
    payload = response.get_json()
    assert "validation" in payload
    assert payload["validation"]["class"] == "malformed_yaml"


def test_v1_production_rule_mode_unchanged(postgres_db):
    conn, _cur = postgres_db
    with patch("engines.detection_simulator.get_db_connection", return_value=RollbackOnlyConnection(conn)):
        result = run_sim(
            source="bank_app",
            rule_id="failed_login_threshold",
            input_format="json",
            json_events=BANK_APP_EVENTS,
        )
    assert result["simulation_mode"] == "existing_production_rule"
    assert "normalized_internal_rule_preview" not in result
    assert "sigma_subset_compatibility" not in result
    assert set(result["stages"]) >= {
        "raw_input",
        "parser",
        "normalized_event",
        "detection_applicability",
        "detection_evaluation",
        "threshold_window_evaluation",
        "alert_preview",
        "mitre_mapping",
        "soar_preview",
    }


def test_v2_temporary_rule_mode_unchanged(postgres_db):
    conn, _cur = postgres_db
    with patch("engines.detection_simulator.get_db_connection", return_value=RollbackOnlyConnection(conn)):
        result = run_temp_sim(
            temporary_rule={"threshold": 1},
            sample_events=BANK_APP_EVENTS[:1],
        )
    assert result["simulation_mode"] == "temporary_playground_rule"
    assert "normalized_internal_rule_preview" not in result
    assert result["temporary_rule"]["condition"] == {
        "field": "event_type",
        "operator": "equals",
        "value": "failed_login",
    }
    assert "sigma_subset" not in result["temporary_rule"]
    assert "rule_provenance" not in result["temporary_rule"]
