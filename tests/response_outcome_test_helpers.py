from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import patch


class RouteSafeConnection:
    def __init__(self, conn):
        self._conn = conn

    def cursor(self):
        return self._conn.cursor()

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def close(self):
        return None


@contextmanager
def patched_route_db(conn, *route_modules):
    wrapper = RouteSafeConnection(conn)
    patches = [
        patch(f"{module}.get_db_connection", return_value=wrapper)
        for module in route_modules
    ]
    patches.append(patch("core.audit_helpers.get_db_connection", return_value=wrapper))
    with patch("routes.alerts_events_routes.get_ip_reputation", return_value={
        "reputation_score": 0,
        "reputation_label": "Normal",
        "reputation_summary": "test",
        "contributing_signals": [],
    }):
        for item in patches:
            item.start()
        try:
            yield
        finally:
            for item in reversed(patches):
                item.stop()
