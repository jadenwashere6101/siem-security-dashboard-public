import os

import requests
from flask import current_app

from core.db import create_blocked_ip_record, get_db_connection


geo_cache = {}
REPUTATION_CACHE = {}
ABUSEIPDB_API_KEY = os.getenv("SIEM_ABUSEIPDB_API_KEY") or os.getenv("ABUSEIPDB_API_KEY")


def _get_reputation_label(score):
    if score <= 0:
        return "Normal"
    if score <= 4:
        return "Low Suspicion"
    if score <= 9:
        return "Suspicious"
    if score <= 14:
        return "High Risk"
    return "Critical"


def _build_reputation_summary(signals):
    if not signals:
        return "No elevated behavioral signals observed in SIEM history."

    phrases = [signal["summary_phrase"] for signal in signals[:2] if signal.get("summary_phrase")]
    if not phrases:
        return "Behavioral signals observed in SIEM history."
    if len(phrases) == 1:
        return phrases[0]
    return f"{phrases[0]} and {phrases[1]}"


def get_ip_reputation(source_ip, cur=None):
    if source_ip is None:
        return {
            "reputation_score": 0,
            "reputation_label": "Normal",
            "reputation_summary": "No elevated behavioral signals observed in SIEM history.",
            "contributing_signals": [],
        }

    owns_connection = cur is None
    conn = None

    try:
        if owns_connection:
            conn = get_db_connection()
            cur = conn.cursor()

        cur.execute(
            """
            SELECT alert_type, COUNT(*)
            FROM alerts
            WHERE source_ip = %s
              AND alert_type IN (
                  'failed_login_threshold',
                  'password_spraying_threshold',
                  'successful_login_after_spray',
                  'port_scan_threshold',
                  'http_error_threshold',
                  'high_request_rate_threshold'
              )
            GROUP BY alert_type
            """,
            (source_ip,),
        )
        alert_counts = {row[0]: row[1] for row in cur.fetchall()}

        cur.execute(
            """
            SELECT COUNT(*)
            FROM blocked_ips
            WHERE ip_address = %s
              AND status = 'active'
            """,
            (source_ip,),
        )
        active_block_count = cur.fetchone()[0]

        signal_config = {
            "failed_login_threshold": {
                "weight": 3,
                "label": "Failed Login Threshold",
                "summary_phrase": "Multiple failed login attempts",
            },
            "password_spraying_threshold": {
                "weight": 5,
                "label": "Password Spraying",
                "summary_phrase": "Password spraying activity",
            },
            "successful_login_after_spray": {
                "weight": 6,
                "label": "Successful Login After Spray",
                "summary_phrase": "Successful login after spraying",
            },
            "port_scan_threshold": {
                "weight": 4,
                "label": "Port Scan Threshold",
                "summary_phrase": "Port scan activity",
            },
            "http_error_threshold": {
                "weight": 2,
                "label": "HTTP Error Threshold",
                "summary_phrase": "Repeated HTTP errors",
            },
            "high_request_rate_threshold": {
                "weight": 3,
                "label": "High Request Rate Threshold",
                "summary_phrase": "High request rate",
            },
        }

        contributing_signals = []
        reputation_score = 0

        for signal_key, config in signal_config.items():
            count = int(alert_counts.get(signal_key, 0) or 0)
            if count <= 0:
                continue

            total_weight = count * config["weight"]
            reputation_score += total_weight
            contributing_signals.append(
                {
                    "signal": signal_key,
                    "label": config["label"],
                    "count": count,
                    "weight": config["weight"],
                    "total": total_weight,
                    "summary_phrase": config["summary_phrase"],
                }
            )

        if active_block_count > 0:
            total_weight = active_block_count * 6
            reputation_score += total_weight
            contributing_signals.append(
                {
                    "signal": "blocked_ips",
                    "label": "Active Blocklist Entry",
                    "count": active_block_count,
                    "weight": 6,
                    "total": total_weight,
                    "summary_phrase": "Prior blocklist entry",
                }
            )

        contributing_signals.sort(key=lambda item: (-item["total"], item["label"]))

        return {
            "reputation_score": reputation_score,
            "reputation_label": _get_reputation_label(reputation_score),
            "reputation_summary": _build_reputation_summary(contributing_signals),
            "contributing_signals": [
                {key: value for key, value in signal.items() if key != "summary_phrase"}
                for signal in contributing_signals
            ],
        }
    finally:
        if owns_connection:
            if cur:
                cur.close()
            if conn:
                conn.close()


def lookup_ip_location(ip_address):
    try:
        if ip_address in geo_cache:
            return geo_cache[ip_address]

        response = requests.get(f"http://ip-api.com/json/{ip_address}", timeout=2)
        data = response.json()

        if data.get("status") != "success":
            return {
                "country": None,
                "city": None,
                "lat": None,
                "lon": None,
            }

        location = {
            "country": data.get("country"),
            "city": data.get("city"),
            "lat": data.get("lat"),
            "lon": data.get("lon"),
        }
        geo_cache[ip_address] = location
        if len(geo_cache) > 5000:
            geo_cache.clear()
        return location

    except Exception as e:
        current_app.logger.error("Error looking up IP location for %s: %s", ip_address, e)
        return {
            "country": None,
            "city": None,
            "lat": None,
            "lon": None,
        }


def lookup_ip_reputation(ip_address):
    ip_address = str(ip_address)

    if ip_address in REPUTATION_CACHE:
        return REPUTATION_CACHE[ip_address]

    # If no API key -> fallback to mock
    if not ABUSEIPDB_API_KEY:
        current_app.logger.warning("ABUSEIPDB_API_KEY is missing; using mock reputation fallback for ip=%s", ip_address)
        result = {
            "reputation_score": 50,
            "reputation_label": "unknown",
            "reputation_source": "mock",
            "reputation_summary": "No API key configured"
        }

        REPUTATION_CACHE[ip_address] = result
        if len(REPUTATION_CACHE) > 5000:
            REPUTATION_CACHE.clear()
        return result

    try:
        url = "https://api.abuseipdb.com/api/v2/check"

        headers = {
            "Key": ABUSEIPDB_API_KEY,
            "Accept": "application/json"
        }

        params = {
            "ipAddress": ip_address,
            "maxAgeInDays": 90
        }

        response = requests.get(url, headers=headers, params=params, timeout=10)

        # Safety check
        if response.status_code != 200:
            current_app.logger.error(
                "AbuseIPDB API returned non-200 for ip=%s status=%s body=%s",
                ip_address,
                response.status_code,
                response.text[:300],
            )
            raise Exception("API request failed")

        data = response.json()["data"]

        score = data.get("abuseConfidenceScore", 0)

        # Map score -> label
        if score >= 70:
            label = "high-risk"
        elif score >= 30:
            label = "medium-risk"
        else:
            label = "low-risk"

        summary = f"{data.get('totalReports', 0)} reports. ISP: {data.get('isp', 'unknown')}"

        result = {
            "reputation_score": score,
            "reputation_label": label,
            "reputation_source": "abuseipdb",
            "reputation_summary": summary
        }

        REPUTATION_CACHE[ip_address] = result
        if len(REPUTATION_CACHE) > 5000:
            REPUTATION_CACHE.clear()
        return result

    except Exception as e:
        current_app.logger.error("AbuseIPDB lookup failed for ip=%s: %s", ip_address, e)
        # fallback if API fails
        result = {
            "reputation_score": 50,
            "reputation_label": "unknown",
            "reputation_source": "fallback",
            "reputation_summary": "API lookup failed"
        }

        REPUTATION_CACHE[ip_address] = result
        if len(REPUTATION_CACHE) > 5000:
            REPUTATION_CACHE.clear()
        return result


def determine_response_action(reputation_score):
    if reputation_score >= 80:
        return "block_ip"
    elif reputation_score >= 60:
        return "flag_high_priority"
    else:
        return "monitor"


def execute_response_action(
    cur,
    alert_id,
    source_ip,
    response_action,
    *,
    create_blocklist_record=False,
    created_by=None,
    reason=None,
    source_alert_id=None,
):
    status = "executed"
    details = None

    if response_action == "block_ip":
        if create_blocklist_record:
            create_blocked_ip_record(
                cur,
                source_ip,
                created_by=created_by,
                reason=reason,
                source_alert_id=source_alert_id,
            )
            current_app.logger.info("[BLOCKLIST TRACKING] alert_id=%s ip=%s", alert_id, source_ip)
            details = "Recorded in SIEM blocklist (tracking only)"
        else:
            current_app.logger.info("[SIMULATED BLOCK] alert_id=%s ip=%s", alert_id, source_ip)
            details = "Simulated IP block"

    elif response_action == "flag_high_priority":
        current_app.logger.info("[SIMULATED ESCALATION] alert_id=%s ip=%s", alert_id, source_ip)
        details = "Simulated escalation to SOC"

    else:
        current_app.logger.info("[SIMULATED MONITOR] alert_id=%s ip=%s", alert_id, source_ip)
        details = "Monitoring only"

    cur.execute(
        """
        INSERT INTO response_actions_log (alert_id, source_ip, action, status, details)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (alert_id, source_ip, response_action, status, details)
    )

    return status
