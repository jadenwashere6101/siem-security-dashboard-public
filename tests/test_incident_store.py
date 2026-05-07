import pytest
from psycopg2 import IntegrityError

from core.incident_store import (
    create_incident,
    find_open_incident_by_source_ip,
    get_incident_detail,
    link_alert_to_incident,
    list_incidents,
    maybe_create_or_link_incident,
    update_incident_status,
)


def _insert_alert(conn, cur, source_ip: str = "203.0.113.10") -> int:
    cur.execute(
        """
        INSERT INTO alerts (alert_type, severity, source_ip, message, status)
        VALUES ('test_alert', 'HIGH', %s::inet, 'test message', 'open')
        RETURNING id
        """,
        (source_ip,),
    )
    (aid,) = cur.fetchone()
    conn.commit()
    return aid


def _count_incidents(cur):
    cur.execute("SELECT COUNT(*) FROM incidents")
    return cur.fetchone()[0]


def _count_links(cur):
    cur.execute("SELECT COUNT(*) FROM incident_alerts")
    return cur.fetchone()[0]


def test_schema_tables_exist(postgres_db):
    conn, cur = postgres_db
    cur.execute(
        """
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = current_schema()
          AND table_name IN ('incidents', 'incident_alerts')
        ORDER BY table_name
        """
    )
    names = [r[0] for r in cur.fetchall()]
    assert names == ["incident_alerts", "incidents"]


def test_schema_status_check_rejects_unknown(postgres_db):
    conn, cur = postgres_db
    with pytest.raises(IntegrityError):
        cur.execute(
            """
            INSERT INTO incidents (title, severity, priority, status, source_ip)
            VALUES ('t', 'HIGH', 'P2', 'unknown', '198.51.100.1'::inet)
            """
        )


def test_schema_priority_check_rejects_p5(postgres_db):
    conn, cur = postgres_db
    with pytest.raises(IntegrityError):
        cur.execute(
            """
            INSERT INTO incidents (title, severity, priority, status, source_ip)
            VALUES ('t', 'HIGH', 'P5', 'open', '198.51.100.1'::inet)
            """
        )


def test_schema_duplicate_primary_incident_alerts_raises(postgres_db):
    conn, cur = postgres_db
    aid = _insert_alert(conn, cur)
    inc = create_incident(conn, "t", "HIGH", "203.0.113.1")
    conn.commit()
    iid = inc["id"]
    cur.execute(
        "INSERT INTO incident_alerts (incident_id, alert_id) VALUES (%s, %s)",
        (iid, aid),
    )
    with pytest.raises(IntegrityError):
        cur.execute(
            "INSERT INTO incident_alerts (incident_id, alert_id) VALUES (%s, %s)",
            (iid, aid),
        )


def test_create_incident_returns_expected_fields(postgres_db):
    conn, _cur = postgres_db
    row = create_incident(conn, "My title", "HIGH", "203.0.113.5")
    conn.commit()
    assert row["title"] == "My title"
    assert row["severity"] == "HIGH"
    assert row["priority"] == "P2"
    assert row["status"] == "open"
    assert row["source_ip"] == "203.0.113.5"
    assert row["assigned_to"] is None
    assert row["resolved_at"] is None
    assert isinstance(row["id"], int)
    assert row["created_at"]


def test_create_incident_critical_maps_priority_p1(postgres_db):
    conn, _cur = postgres_db
    row = create_incident(conn, "c", "CRITICAL", "203.0.113.6")
    conn.commit()
    assert row["priority"] == "P1"


def test_link_alert_to_incident_idempotent(postgres_db):
    conn, cur = postgres_db
    aid = _insert_alert(conn, cur)
    inc = create_incident(conn, "t", "HIGH", "203.0.113.7")
    conn.commit()
    iid = inc["id"]
    link_alert_to_incident(conn, iid, aid)
    conn.commit()
    link_alert_to_incident(conn, iid, aid)
    conn.commit()
    cur.execute(
        "SELECT COUNT(*) FROM incident_alerts WHERE incident_id = %s AND alert_id = %s",
        (iid, aid),
    )
    assert cur.fetchone()[0] == 1


def test_find_open_returns_none_when_empty(postgres_db):
    conn, _cur = postgres_db
    assert find_open_incident_by_source_ip(conn, "203.0.113.20") is None


def test_find_open_ignores_resolved_within_window(postgres_db):
    conn, cur = postgres_db
    inc = create_incident(conn, "t", "HIGH", "203.0.113.21")
    conn.commit()
    iid = inc["id"]
    cur.execute(
        "UPDATE incidents SET status = 'resolved' WHERE id = %s",
        (iid,),
    )
    conn.commit()
    assert find_open_incident_by_source_ip(conn, "203.0.113.21", 60) is None


def test_find_open_ignores_closed_within_window(postgres_db):
    conn, cur = postgres_db
    inc = create_incident(conn, "t", "HIGH", "203.0.113.22")
    conn.commit()
    iid = inc["id"]
    cur.execute(
        "UPDATE incidents SET status = 'closed' WHERE id = %s",
        (iid,),
    )
    conn.commit()
    assert find_open_incident_by_source_ip(conn, "203.0.113.22", 60) is None


def test_find_open_finds_open_within_window(postgres_db):
    conn, _cur = postgres_db
    inc = create_incident(conn, "t", "HIGH", "203.0.113.23")
    conn.commit()
    found = find_open_incident_by_source_ip(conn, "203.0.113.23", 60)
    assert found is not None
    assert found["id"] == inc["id"]


def test_find_open_finds_investigating_within_window(postgres_db):
    conn, cur = postgres_db
    inc = create_incident(conn, "t", "HIGH", "203.0.113.24")
    conn.commit()
    iid = inc["id"]
    cur.execute(
        "UPDATE incidents SET status = 'investigating' WHERE id = %s",
        (iid,),
    )
    conn.commit()
    found = find_open_incident_by_source_ip(conn, "203.0.113.24", 60)
    assert found is not None
    assert found["id"] == iid


def test_find_open_returns_none_outside_window(postgres_db):
    conn, cur = postgres_db
    inc = create_incident(conn, "old", "HIGH", "203.0.113.25")
    conn.commit()
    iid = inc["id"]
    cur.execute(
        "UPDATE incidents SET created_at = NOW() - INTERVAL '2 hours' WHERE id = %s",
        (iid,),
    )
    conn.commit()
    assert find_open_incident_by_source_ip(conn, "203.0.113.25", 60) is None


def test_find_open_most_recent_when_multiple_open_same_ip(postgres_db):
    conn, cur = postgres_db
    older = create_incident(conn, "a", "HIGH", "203.0.113.26")
    conn.commit()
    cur.execute(
        "UPDATE incidents SET created_at = NOW() - INTERVAL '30 minutes' WHERE id = %s",
        (older["id"],),
    )
    conn.commit()
    newer = create_incident(conn, "b", "HIGH", "203.0.113.26")
    conn.commit()
    found = find_open_incident_by_source_ip(conn, "203.0.113.26", 120)
    assert found is not None
    assert found["id"] == newer["id"]


def test_maybe_create_returns_none_for_medium_and_low(postgres_db):
    conn, cur = postgres_db
    aid_hi = _insert_alert(conn, cur, "203.0.113.30")
    assert maybe_create_or_link_incident(conn, aid_hi, "MEDIUM", "203.0.113.30") is None
    conn.commit()
    assert _count_incidents(cur) == 0

    aid_lo = _insert_alert(conn, cur, "203.0.113.31")
    assert maybe_create_or_link_incident(conn, aid_lo, "LOW", "203.0.113.31") is None
    conn.commit()
    assert _count_incidents(cur) == 0


def test_maybe_create_high_creates_and_links(postgres_db):
    conn, cur = postgres_db
    aid = _insert_alert(conn, cur, "203.0.113.32")
    inc = maybe_create_or_link_incident(conn, aid, "HIGH", "203.0.113.32")
    conn.commit()
    assert inc is not None
    assert inc["severity"] == "HIGH"
    assert _count_incidents(cur) == 1
    assert _count_links(cur) == 1
    cur.execute(
        "SELECT incident_id FROM incident_alerts WHERE alert_id = %s",
        (aid,),
    )
    assert cur.fetchone()[0] == inc["id"]


def test_maybe_create_links_existing_open_in_window(postgres_db):
    conn, cur = postgres_db
    aid1 = _insert_alert(conn, cur, "203.0.113.33")
    first = maybe_create_or_link_incident(conn, aid1, "HIGH", "203.0.113.33")
    conn.commit()
    aid2 = _insert_alert(conn, cur, "203.0.113.33")
    second = maybe_create_or_link_incident(conn, aid2, "HIGH", "203.0.113.33")
    conn.commit()
    assert second["id"] == first["id"]
    assert _count_incidents(cur) == 1
    assert _count_links(cur) == 2


def test_maybe_create_new_when_outside_dedup_window(postgres_db):
    conn, cur = postgres_db
    aid1 = _insert_alert(conn, cur, "203.0.113.34")
    first = maybe_create_or_link_incident(conn, aid1, "HIGH", "203.0.113.34")
    conn.commit()
    cur.execute(
        "UPDATE incidents SET created_at = NOW() - INTERVAL '3 hours' WHERE id = %s",
        (first["id"],),
    )
    conn.commit()
    aid2 = _insert_alert(conn, cur, "203.0.113.34")
    second = maybe_create_or_link_incident(conn, aid2, "HIGH", "203.0.113.34")
    conn.commit()
    assert second["id"] != first["id"]
    assert _count_incidents(cur) == 2


def test_maybe_create_new_when_existing_resolved(postgres_db):
    conn, cur = postgres_db
    aid1 = _insert_alert(conn, cur, "203.0.113.35")
    prev = maybe_create_or_link_incident(conn, aid1, "HIGH", "203.0.113.35")
    conn.commit()
    update_incident_status(conn, prev["id"], "resolved", "u1")
    conn.commit()
    aid2 = _insert_alert(conn, cur, "203.0.113.35")
    nxt = maybe_create_or_link_incident(conn, aid2, "HIGH", "203.0.113.35")
    conn.commit()
    assert nxt["id"] != prev["id"]
    assert _count_incidents(cur) == 2


def test_maybe_create_critical_dedup_same_as_high(postgres_db):
    conn, cur = postgres_db
    aid1 = _insert_alert(conn, cur, "203.0.113.36")
    one = maybe_create_or_link_incident(conn, aid1, "CRITICAL", "203.0.113.36")
    conn.commit()
    aid2 = _insert_alert(conn, cur, "203.0.113.36")
    two = maybe_create_or_link_incident(conn, aid2, "CRITICAL", "203.0.113.36")
    conn.commit()
    assert two["id"] == one["id"]


def test_list_incidents_ordered_and_filters(postgres_db):
    conn, cur = postgres_db
    cur.execute(
        """
        INSERT INTO incidents (title, severity, priority, status, source_ip, created_at)
        VALUES
          ('a', 'MEDIUM', 'P2', 'open', '198.51.100.1'::inet, NOW() - INTERVAL '3 hours'),
          ('b', 'CRITICAL', 'P1', 'resolved', '198.51.100.2'::inet, NOW() - INTERVAL '2 hours'),
          ('c', 'CRITICAL', 'P1', 'open', '198.51.100.3'::inet, NOW() - INTERVAL '1 hour')
        """
    )
    conn.commit()
    rows = list_incidents(conn)
    titles = [r["title"] for r in rows]
    assert titles == ["c", "b", "a"]
    open_only = list_incidents(conn, status="open")
    assert len(open_only) == 2
    crit = list_incidents(conn, severity="CRITICAL")
    assert len(crit) == 2


def test_list_incidents_limit_clamped(postgres_db):
    conn, cur = postgres_db
    for n in range(110):
        cur.execute(
            """
            INSERT INTO incidents (title, severity, priority, status, source_ip)
            VALUES (%s, 'LOW', 'P2', 'closed', '198.51.100.10'::inet)
            """,
            (f"bulk-{n}",),
        )
    conn.commit()
    assert len(list_incidents(conn, status="closed", limit=200)) == 100


def test_list_incidents_empty(postgres_db):
    conn, _cur = postgres_db
    assert list_incidents(conn) == []


def test_list_incidents_offset(postgres_db):
    conn, cur = postgres_db
    cur.execute(
        """
        INSERT INTO incidents (title, severity, priority, status, source_ip, created_at)
        VALUES
          ('x1', 'HIGH', 'P2', 'open', '198.51.100.20'::inet, NOW() - INTERVAL '20 minutes'),
          ('x2', 'HIGH', 'P2', 'open', '198.51.100.21'::inet, NOW() - INTERVAL '10 minutes'),
          ('x3', 'HIGH', 'P2', 'open', '198.51.100.22'::inet, NOW())
        """
    )
    conn.commit()
    page = list_incidents(conn, limit=1, offset=1)
    assert len(page) == 1
    assert page[0]["title"] == "x2"


def test_get_incident_unknown_returns_none(postgres_db):
    conn, _cur = postgres_db
    assert get_incident_detail(conn, 999999) is None


def test_get_incident_detail_with_alerts(postgres_db):
    conn, cur = postgres_db
    inc = create_incident(conn, "detail", "HIGH", "203.0.113.40")
    conn.commit()
    aid = _insert_alert(conn, cur, "203.0.113.40")
    link_alert_to_incident(conn, inc["id"], aid)
    conn.commit()
    detail = get_incident_detail(conn, inc["id"])
    assert detail["id"] == inc["id"]
    assert len(detail["alerts"]) == 1
    a0 = detail["alerts"][0]
    assert a0["alert_id"] == aid
    assert a0["alert_type"] == "test_alert"
    assert a0["linked_at"]


def test_get_incident_no_links_empty_alerts(postgres_db):
    conn, _cur = postgres_db
    inc = create_incident(conn, "solo", "HIGH", "203.0.113.41")
    conn.commit()
    detail = get_incident_detail(conn, inc["id"])
    assert detail["alerts"] == []


def test_update_open_to_investigating(postgres_db):
    conn, _cur = postgres_db
    inc = create_incident(conn, "st", "HIGH", "203.0.113.50")
    conn.commit()
    out = update_incident_status(conn, inc["id"], "investigating", "alice")
    conn.commit()
    assert out["status"] == "investigating"
    assert out["resolved_at"] is None


def test_update_open_to_resolved_sets_resolved_at(postgres_db):
    conn, _cur = postgres_db
    inc = create_incident(conn, "st", "HIGH", "203.0.113.51")
    conn.commit()
    out = update_incident_status(conn, inc["id"], "resolved", "alice")
    conn.commit()
    assert out["status"] == "resolved"
    assert out["resolved_at"] is not None


def test_update_resolved_to_open_keeps_resolved_at(postgres_db):
    conn, _cur = postgres_db
    inc = create_incident(conn, "st", "HIGH", "203.0.113.52")
    conn.commit()
    r1 = update_incident_status(conn, inc["id"], "resolved", "alice")
    conn.commit()
    ts = r1["resolved_at"]
    r2 = update_incident_status(conn, inc["id"], "open", "alice")
    conn.commit()
    assert r2["status"] == "open"
    assert r2["resolved_at"] == ts


def test_update_closed_to_open_raises(postgres_db):
    conn, _cur = postgres_db
    inc = create_incident(conn, "st", "HIGH", "203.0.113.53")
    conn.commit()
    update_incident_status(conn, inc["id"], "resolved", "alice")
    conn.commit()
    update_incident_status(conn, inc["id"], "closed", "alice")
    conn.commit()
    with pytest.raises(ValueError, match="invalid status transition"):
        update_incident_status(conn, inc["id"], "open", "alice")


def test_update_unknown_status_raises(postgres_db):
    conn, _cur = postgres_db
    inc = create_incident(conn, "st", "HIGH", "203.0.113.54")
    conn.commit()
    with pytest.raises(ValueError, match="invalid status transition"):
        update_incident_status(conn, inc["id"], "bogus", "alice")


def test_update_unknown_incident_raises(postgres_db):
    conn, _cur = postgres_db
    with pytest.raises(ValueError, match="incident not found"):
        update_incident_status(conn, 999999, "investigating", "alice")
