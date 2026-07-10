"""Regression coverage for legacy Response Registry blocklist backfill actors."""

from datetime import datetime, timezone

from scripts import backfill_indicator_response_registry as backfill_script


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self._rows = []

    def execute(self, sql, params=None):
        normalized = " ".join(sql.split())
        params = params or ()
        if normalized.startswith("SELECT id, ip_address"):
            self._rows = list(self.conn.blocked_rows)
        elif normalized == "SELECT id FROM users WHERE id = %s":
            user_id = int(params[0])
            self._rows = [(user_id,)] if user_id in self.conn.users_by_id else []
        elif normalized == "SELECT id FROM users WHERE username = %s":
            user_id = self.conn.users_by_name.get(params[0])
            self._rows = [(user_id,)] if user_id is not None else []
        elif normalized.startswith("UPDATE indicator_response_events SET created_at"):
            created_at, event_id = params
            self.conn.event_timestamps[event_id] = created_at
            self._rows = []
        else:
            raise AssertionError(f"Unexpected SQL: {normalized}")

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None


class FakeConnection:
    def __init__(self, blocked_rows, *, users):
        self.blocked_rows = blocked_rows
        self.users_by_name = dict(users)
        self.users_by_id = set(users.values())
        self.event_timestamps = {}
        self.commits = 0
        self.closed = False

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1

    def close(self):
        self.closed = True


def _row(block_id, created_by, *, created_at=None):
    return (
        block_id,
        f"8.8.8.{block_id}",
        "historical block",
        created_by,
        100 + block_id,
        created_at or datetime(2025, 1, block_id, tzinfo=timezone.utc),
        "active",
    )


def _install_registry_fakes(monkeypatch):
    identities = {}
    events = {}
    event_calls = []

    def upsert(_conn, *, indicator_type, indicator_value):
        key = (indicator_type, indicator_value)
        identities.setdefault(key, {"id": len(identities) + 1})
        return identities[key]

    def append(_conn, **kwargs):
        key = kwargs["idempotency_key"]
        events.setdefault(key, {"id": len(events) + 1})
        event_calls.append(kwargs)
        return events[key]

    monkeypatch.setattr(backfill_script, "upsert_indicator_identity", upsert)
    monkeypatch.setattr(backfill_script, "append_registry_event", append)
    return identities, events, event_calls


def test_backfill_accepts_integer_actor_id_and_preserves_timestamp(monkeypatch):
    identities, events, calls = _install_registry_fakes(monkeypatch)
    historical_time = datetime(2024, 5, 6, 7, 8, tzinfo=timezone.utc)
    conn = FakeConnection([_row(1, 7, created_at=historical_time)], users={"admin": 7})

    stats = backfill_script.backfill(conn)

    assert stats["unresolved_actor_count"] == 0
    assert calls[0]["actor_user_id"] == 7
    assert conn.event_timestamps[events["backfill-blocked-ip-1"]["id"]] == historical_time
    assert len(identities) == 1


def test_backfill_resolves_legacy_username_to_user_id(monkeypatch):
    _identities, _events, calls = _install_registry_fakes(monkeypatch)
    conn = FakeConnection([_row(2, "admin")], users={"admin": 42})

    stats = backfill_script.backfill(conn)

    assert stats["skipped"] == 0
    assert calls[0]["actor_user_id"] == 42
    assert calls[0]["provenance"] == "recorded"


def test_backfill_skips_unknown_username_warns_and_succeeds(monkeypatch, capsys):
    identities, events, calls = _install_registry_fakes(monkeypatch)
    conn = FakeConnection([_row(3, "missing-user")], users={"admin": 42})

    stats = backfill_script.backfill(conn)

    assert stats["skipped"] == 1
    assert stats["unresolved_actor_count"] == 1
    assert stats["unresolved_actors"] == [
        {
            "blocked_ip_id": 3,
            "created_by": "missing-user",
            "reason": "actor could not be resolved to users.id",
        }
    ]
    assert "WARNING: skipping blocked_ips id=3" in capsys.readouterr().err
    assert identities == {}
    assert events == {}
    assert calls == []
    assert conn.commits == 1


def test_main_exits_successfully_with_unresolved_legacy_actor(monkeypatch, capsys):
    _install_registry_fakes(monkeypatch)
    conn = FakeConnection([_row(5, "deleted-user")], users={"admin": 42})
    monkeypatch.setattr(backfill_script, "get_db_connection", lambda: conn)

    result = backfill_script.main([])

    captured = capsys.readouterr()
    assert result == 0
    assert '"unresolved_actor_count": 1' in captured.out
    assert "created_by='deleted-user' could not be resolved" in captured.err
    assert conn.closed is True


def test_backfill_rerun_reuses_identity_and_idempotency_key(monkeypatch):
    identities, events, calls = _install_registry_fakes(monkeypatch)
    conn = FakeConnection([_row(4, "admin")], users={"admin": 9})

    first = backfill_script.backfill(conn)
    second = backfill_script.backfill(conn)

    assert first["skipped"] == second["skipped"] == 0
    assert len(identities) == 1
    assert len(events) == 1
    assert [call["idempotency_key"] for call in calls] == [
        "backfill-blocked-ip-4",
        "backfill-blocked-ip-4",
    ]
    assert conn.commits == 2
