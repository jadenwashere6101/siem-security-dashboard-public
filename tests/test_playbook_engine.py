import pytest

from core import playbook_store
from engines.playbook_engine import (
    CORRELATED_ALERT_TYPES,
    _evaluate_trigger,
    match_playbooks,
)


def _base_alert(**kwargs):
    row = {
        "alert_type": "password_spraying",
        "severity": "HIGH",
        "source_ip": "10.0.0.1",
        "source": "bank_app",
        "reputation_score": 50,
    }
    row.update(kwargs)
    return row


def test_correlated_alert_types_expected_set():
    assert CORRELATED_ALERT_TYPES == frozenset(
        {
            "correlated_activity",
            "web_to_app_attack_pattern",
            "spray_then_success_pattern",
            "cloud_app_error_pattern",
        }
    )


# --- alert_type ---


def test_trigger_alert_type_match():
    assert _evaluate_trigger(
        {"alert_type": "password_spraying"},
        _base_alert(alert_type="password_spraying"),
    )


def test_trigger_alert_type_mismatch():
    assert not _evaluate_trigger(
        {"alert_type": "password_spraying"},
        _base_alert(alert_type="failed_login"),
    )


def test_trigger_alert_type_absent_matches():
    assert _evaluate_trigger({}, _base_alert(alert_type="anything"))


def test_trigger_alert_type_alert_none():
    assert not _evaluate_trigger(
        {"alert_type": "password_spraying"},
        _base_alert(alert_type=None),
    )


def test_trigger_alert_type_case_insensitive():
    assert _evaluate_trigger(
        {"alert_type": "PASSWORD_SPRAYING"},
        _base_alert(alert_type="password_spraying"),
    )


# --- min_severity ---


def test_trigger_min_severity_equal():
    assert _evaluate_trigger({"min_severity": "HIGH"}, _base_alert(severity="HIGH"))


def test_trigger_min_severity_above():
    assert _evaluate_trigger({"min_severity": "LOW"}, _base_alert(severity="HIGH"))


def test_trigger_min_severity_below():
    assert not _evaluate_trigger({"min_severity": "HIGH"}, _base_alert(severity="LOW"))


def test_trigger_min_severity_absent():
    assert _evaluate_trigger({}, _base_alert(severity="LOW"))


def test_trigger_min_severity_alert_none():
    assert not _evaluate_trigger({"min_severity": "HIGH"}, _base_alert(severity=None))


def test_trigger_min_severity_case_insensitive():
    assert _evaluate_trigger({"min_severity": "HIGH"}, _base_alert(severity="high"))


# --- source ---


def test_trigger_source_match():
    assert _evaluate_trigger({"source": "bank_app"}, _base_alert(source="bank_app"))


def test_trigger_source_mismatch():
    assert not _evaluate_trigger({"source": "bank_app"}, _base_alert(source="nginx"))


def test_trigger_source_alert_none():
    assert not _evaluate_trigger({"source": "bank_app"}, _base_alert(source=None))


def test_trigger_source_absent():
    assert _evaluate_trigger({}, _base_alert(source=None))


# --- correlation_flag ---


def test_correlation_flag_true_on_correlated_type():
    assert _evaluate_trigger(
        {"correlation_flag": True},
        _base_alert(alert_type="correlated_activity"),
    )


def test_correlation_flag_true_on_detection_type():
    assert not _evaluate_trigger(
        {"correlation_flag": True},
        _base_alert(alert_type="password_spraying"),
    )


def test_correlation_flag_false_on_detection_type():
    assert _evaluate_trigger(
        {"correlation_flag": False},
        _base_alert(alert_type="password_spraying"),
    )


def test_correlation_flag_false_on_correlated_type():
    assert not _evaluate_trigger(
        {"correlation_flag": False},
        _base_alert(alert_type="correlated_activity"),
    )


def test_correlation_flag_absent():
    assert _evaluate_trigger({}, _base_alert(alert_type="correlated_activity"))


# --- reputation_score_min ---


def test_reputation_equal():
    assert _evaluate_trigger({"reputation_score_min": 50}, _base_alert(reputation_score=50))


def test_reputation_above():
    assert _evaluate_trigger({"reputation_score_min": 40}, _base_alert(reputation_score=50))


def test_reputation_below():
    assert not _evaluate_trigger({"reputation_score_min": 60}, _base_alert(reputation_score=50))


def test_reputation_none_vs_positive_threshold():
    assert not _evaluate_trigger({"reputation_score_min": 1}, _base_alert(reputation_score=None))


def test_reputation_none_vs_zero_threshold():
    assert _evaluate_trigger({"reputation_score_min": 0}, _base_alert(reputation_score=None))


def test_reputation_absent():
    assert _evaluate_trigger({}, _base_alert(reputation_score=None))


# --- multi-field AND ---


def test_multi_field_all_match():
    assert _evaluate_trigger(
        {
            "alert_type": "password_spraying",
            "min_severity": "HIGH",
            "source": "bank_app",
            "reputation_score_min": 10,
        },
        _base_alert(),
    )


def test_multi_field_one_fails():
    assert not _evaluate_trigger(
        {"alert_type": "password_spraying", "source": "nginx"},
        _base_alert(),
    )


def test_empty_trigger_matches_any():
    assert _evaluate_trigger({}, _base_alert())


def test_unrecognized_trigger_key_ignored():
    assert _evaluate_trigger(
        {"unknown_future_key": "x", "alert_type": "password_spraying"},
        _base_alert(alert_type="password_spraying"),
    )


def test_unrecognized_key_does_not_force_match():
    assert not _evaluate_trigger(
        {"unknown_future_key": "x", "alert_type": "wrong"},
        _base_alert(alert_type="password_spraying"),
    )


# --- match_playbooks (DB) ---


def _steps():
    return [{"action": "monitor", "params": {}}]


def _insert_alert_row(cur, **kwargs):
    alert_type = kwargs.get("alert_type", "password_spraying")
    severity = kwargs.get("severity", "HIGH")
    source_ip = kwargs.get("source_ip", "10.0.0.2")
    message = kwargs.get("message", "m")
    source = kwargs.get("source", "bank_app")
    reputation_score = kwargs.get("reputation_score", 90)
    cur.execute(
        """
        INSERT INTO alerts (alert_type, severity, source_ip, message, source, reputation_score)
        VALUES (%s, %s, %s::inet, %s, %s, %s)
        RETURNING id
        """,
        (alert_type, severity, source_ip, message, source, reputation_score),
    )
    return cur.fetchone()[0]


@pytest.mark.usefixtures("postgres_db")
def test_match_playbooks_no_definitions(postgres_db):
    conn, cur = postgres_db
    aid = _insert_alert_row(cur)
    assert match_playbooks(conn, aid) == []


@pytest.mark.usefixtures("postgres_db")
def test_match_playbooks_one_match(postgres_db):
    conn, cur = postgres_db
    aid = _insert_alert_row(cur)
    playbook_store.create_playbook_definition(
        conn,
        "pb_m1",
        "M1",
        steps=_steps(),
        trigger_config={"alert_type": "password_spraying"},
    )
    matched = match_playbooks(conn, aid)
    assert len(matched) == 1
    assert matched[0]["id"] == "pb_m1"


@pytest.mark.usefixtures("postgres_db")
def test_match_playbooks_no_match(postgres_db):
    conn, cur = postgres_db
    aid = _insert_alert_row(cur, alert_type="failed_login")
    playbook_store.create_playbook_definition(
        conn,
        "pb_nomatch",
        "N",
        steps=_steps(),
        trigger_config={"alert_type": "password_spraying"},
    )
    assert match_playbooks(conn, aid) == []


@pytest.mark.usefixtures("postgres_db")
def test_match_playbooks_partial_subset(postgres_db):
    conn, cur = postgres_db
    aid = _insert_alert_row(cur)
    playbook_store.create_playbook_definition(
        conn,
        "pb_hit",
        "H",
        steps=_steps(),
        trigger_config={"alert_type": "password_spraying"},
    )
    playbook_store.create_playbook_definition(
        conn,
        "pb_miss",
        "M",
        steps=_steps(),
        trigger_config={"alert_type": "failed_login"},
    )
    matched = match_playbooks(conn, aid)
    assert [m["id"] for m in matched] == ["pb_hit"]


@pytest.mark.usefixtures("postgres_db")
def test_match_playbooks_disabled_excluded(postgres_db):
    conn, cur = postgres_db
    aid = _insert_alert_row(cur)
    playbook_store.create_playbook_definition(
        conn,
        "pb_dis",
        "D",
        steps=_steps(),
        trigger_config={"alert_type": "password_spraying"},
        enabled=False,
    )
    assert match_playbooks(conn, aid) == []


@pytest.mark.usefixtures("postgres_db")
def test_match_playbooks_unknown_alert(postgres_db):
    conn, _cur = postgres_db
    assert match_playbooks(conn, 9_999_999) == []
