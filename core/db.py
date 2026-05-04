import ipaddress
import os

import psycopg2


def get_db_connection():
    return psycopg2.connect(
        dbname=os.getenv("SIEM_DB_NAME") or os.getenv("DB_NAME"),
        user=os.getenv("SIEM_DB_USER") or os.getenv("DB_USER"),
        host=os.getenv("SIEM_DB_HOST") or os.getenv("DB_HOST"),
        password=os.getenv("SIEM_DB_PASSWORD") or os.getenv("DB_PASSWORD")
    )


def validate_blocked_ip(ip_address):
    if ip_address is None or not str(ip_address).strip():
        raise ValueError("IP address is required")

    try:
        parsed_ip = ipaddress.ip_address(str(ip_address).strip())
    except ValueError as error:
        raise ValueError("Invalid IP address") from error

    if (
        parsed_ip.is_loopback
        or parsed_ip.is_private
        or parsed_ip.is_link_local
        or parsed_ip.is_multicast
        or parsed_ip.is_reserved
        or parsed_ip.is_unspecified
    ):
        raise ValueError("Private, loopback, and internal IPs cannot be blocked")

    return str(parsed_ip)


def create_blocked_ip_record(cur, ip_address, created_by=None, reason=None, source_alert_id=None, expires_at=None):
    normalized_ip = validate_blocked_ip(ip_address)

    if source_alert_id is not None:
        cur.execute(
            """
            SELECT 1
            FROM alerts
            WHERE id = %s
            """,
            (source_alert_id,),
        )
        if not cur.fetchone():
            raise ValueError("Source alert not found")

    cur.execute(
        """
        SELECT 1
        FROM blocked_ips
        WHERE ip_address = %s
          AND status = 'active'
        """,
        (normalized_ip,),
    )
    if cur.fetchone():
        raise ValueError("An active block already exists for this IP")

    cur.execute(
        """
        INSERT INTO blocked_ips (
            ip_address,
            reason,
            status,
            created_by,
            expires_at,
            source_alert_id
        )
        VALUES (%s, %s, 'active', %s, %s, %s)
        RETURNING id
        """,
        (
            normalized_ip,
            reason,
            created_by,
            expires_at,
            source_alert_id,
        ),
    )
    return cur.fetchone()[0]
