from psycopg2.extras import Json

from scripts import backfill_honeypot_locations


def test_honeypot_location_backfill_dry_run_and_apply(postgres_db, monkeypatch):
    conn, cur = postgres_db
    source_ip = "8.8.8.8"
    location = {
        "country": "United States",
        "city": "Mountain View",
        "lat": 37.4056,
        "lon": -122.0775,
    }

    monkeypatch.setattr(
        backfill_honeypot_locations,
        "lookup_ip_location",
        lambda _ip: location,
    )

    cur.execute(
        """
        INSERT INTO events (
            event_type, severity, source_ip, source, source_type,
            message, app_name, environment, raw_payload
        )
        VALUES (
            'scanner_detected', 'medium', %s::inet, 'honeypot', 'honeypot',
            'scanner', 'flask_honeypot', 'prod', %s::jsonb
        )
        """,
        (source_ip, Json({"path": "/"})),
    )
    cur.execute(
        """
        INSERT INTO alerts (
            alert_type, severity, source_ip, source, source_type, message
        )
        VALUES (
            'honeypot_scanner_detected', 'medium', %s::inet,
            'honeypot', 'honeypot', 'scanner'
        )
        """,
        (source_ip,),
    )
    conn.commit()

    dry_run = backfill_honeypot_locations.run_backfill(conn, apply=False)

    assert dry_run["events_to_update"] == 1
    assert dry_run["alerts_to_update"] == 1
    assert dry_run["events_updated"] == 0
    assert dry_run["alerts_updated"] == 0

    cur.execute("SELECT raw_payload->'location' FROM events WHERE source_ip = %s::inet", (source_ip,))
    assert cur.fetchone()[0] is None

    applied = backfill_honeypot_locations.run_backfill(conn, apply=True)

    assert applied["events_updated"] == 1
    assert applied["alerts_updated"] == 1

    cur.execute(
        """
        SELECT raw_payload->'location'
        FROM events
        WHERE source_ip = %s::inet
        """,
        (source_ip,),
    )
    assert cur.fetchone()[0] == location

    cur.execute(
        """
        SELECT country, city, latitude, longitude
        FROM alerts
        WHERE source_ip = %s::inet
        """,
        (source_ip,),
    )
    assert cur.fetchone() == (
        "United States",
        "Mountain View",
        37.4056,
        -122.0775,
    )
