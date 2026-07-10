"""Phase 1 contract tests for canonical action vocabulary and routing."""

import pytest

from core.canonical_action_vocabulary import (
    CanonicalActionValidationError,
    validate_action_for_response_queue,
    resolve_action_for_playbook,
)
from core.ip_helpers import enqueue_response_action
from engines.playbook_registry import validate_playbook_steps


def test_bare_notify_rejected_before_queue_enqueue(postgres_db):
    conn, cur = postgres_db
    cur.execute(
        """
        INSERT INTO alerts (alert_type, severity, source_ip, message)
        VALUES ('test', 'high', '203.0.113.50', 'notify routing test')
        RETURNING id
        """
    )
    alert_id = cur.fetchone()[0]
    conn.commit()

    with pytest.raises(CanonicalActionValidationError) as exc:
        enqueue_response_action(cur, alert_id, "203.0.113.50", "notify")
    assert exc.value.code == "ambiguous_notify"

    cur.execute("SELECT COUNT(*) FROM response_actions_queue WHERE alert_id = %s", (alert_id,))
    assert cur.fetchone()[0] == 0


def test_enrich_context_cannot_enter_response_action_queue(postgres_db):
    conn, cur = postgres_db
    cur.execute(
        """
        INSERT INTO alerts (alert_type, severity, source_ip, message)
        VALUES ('test', 'medium', '203.0.113.51', 'enrich routing test')
        RETURNING id
        """
    )
    alert_id = cur.fetchone()[0]
    conn.commit()

    with pytest.raises(CanonicalActionValidationError) as exc:
        enqueue_response_action(cur, alert_id, "203.0.113.51", "enrich_context")
    assert exc.value.code == "misrouted_enrich_context"

    cur.execute("SELECT COUNT(*) FROM response_actions_queue WHERE alert_id = %s", (alert_id,))
    assert cur.fetchone()[0] == 0


def test_validate_action_for_response_queue_allows_block_monitor_escalate():
    assert validate_action_for_response_queue("block_ip") == "block_ip"
    assert validate_action_for_response_queue("monitor") == "monitor"
    assert validate_action_for_response_queue("flag_high_priority") == "flag_high_priority"
    assert validate_action_for_response_queue("escalate") == "flag_high_priority"


def test_playbook_rejects_bare_notify():
    errors = validate_playbook_steps([{"action": "notify"}])
    assert errors
    assert any("notify" in err for err in errors)


def test_playbook_allows_enrich_context_and_provider_notify():
    assert resolve_action_for_playbook("enrich_context") == "enrich_context"
    assert resolve_action_for_playbook("notify_slack") == "notify_slack"
    errors = validate_playbook_steps(
        [{"action": "enrich_context"}, {"action": "notify_slack"}]
    )
    assert errors == []
