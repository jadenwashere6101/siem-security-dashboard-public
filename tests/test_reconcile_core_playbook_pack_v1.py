from core.core_playbook_pack_v1 import (
    CORE_V1_SPRAY_THEN_SUCCESS_CORRELATION_INVESTIGATION_ID,
    seed_core_playbook_pack_v1,
)
from core.playbook_store import get_playbook_definition, update_playbook_definition
from scripts.reconcile_core_playbook_pack_v1 import reconcile_core_playbook_pack_v1


def test_reconcile_core_playbook_pack_v1_updates_drift_and_is_idempotent(postgres_db):
    conn, _cur = postgres_db
    seed_core_playbook_pack_v1(conn)
    original = get_playbook_definition(conn, CORE_V1_SPRAY_THEN_SUCCESS_CORRELATION_INVESTIGATION_ID)

    update_playbook_definition(
        conn,
        CORE_V1_SPRAY_THEN_SUCCESS_CORRELATION_INVESTIGATION_ID,
        name=original["name"],
        description=original["description"],
        trigger_config={"alert_type": "spray_then_success_pattern", "min_severity": "critical"},
        steps=[
            {"action": "flag_high_priority"},
            {"action": "enrich_context"},
            {"action": "require_approval", "risk_level": "critical"},
            {"action": "block_ip", "params": {"source_ip": "{{alert.source_ip}}"}},
        ],
        enabled=True,
    )

    first = reconcile_core_playbook_pack_v1(conn)
    second = reconcile_core_playbook_pack_v1(conn)

    assert CORE_V1_SPRAY_THEN_SUCCESS_CORRELATION_INVESTIGATION_ID in first
    assert second == []
    reconciled = get_playbook_definition(conn, CORE_V1_SPRAY_THEN_SUCCESS_CORRELATION_INVESTIGATION_ID)
    assert reconciled["trigger_config"]["min_severity"] == "high"
    assert [step["action"] for step in reconciled["steps"]] == [
        "enrich_context",
        "monitor",
    ]
