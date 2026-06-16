from test_blocklist_api_contracts import (
    VALID_BLOCKABLE_IP,
    _insert_blocked_ip,
    _login_super_admin,
    _patched_app_db,
)


def test_get_blocked_ips_normalizes_expired_active_entry_as_expired(client, postgres_db):
    conn, cur = postgres_db
    block_id = _insert_blocked_ip(
        cur,
        ip_address=VALID_BLOCKABLE_IP,
        status="active",
        expires_interval="-1 hour",
    )
    conn.commit()

    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get("/blocked-ips")

    assert resp.status_code == 200
    data = resp.get_json()
    entry = next(item for item in data if item["id"] == block_id)
    assert entry["status"] == "expired"

    cur.execute("SELECT status FROM blocked_ips WHERE id = %s", (block_id,))
    assert cur.fetchone()[0] == "active"
