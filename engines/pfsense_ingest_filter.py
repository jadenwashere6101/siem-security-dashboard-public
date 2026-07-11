import json
import logging
import threading
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone

from psycopg2.extras import Json


logger = logging.getLogger(__name__)

MAX_SENSITIVE_PORTS = 64
DEFAULT_SENSITIVE_PORTS = (21, 22, 23, 25, 135, 445, 1433, 3306, 3389, 5432, 5900, 6379, 27017)

DEFAULT_PFSENSE_INGEST_CONFIG = {
    "block_events": {"enabled": True, "parameters": {}},
    "inbound_sensitive_port_allows": {
        "enabled": True,
        "parameters": {"sensitive_ports": list(DEFAULT_SENSITIVE_PORTS)},
    },
    "all_allow_events": {"enabled": False, "parameters": {}},
    "dns_traffic": {"enabled": False, "parameters": {}},
    "icmp_traffic": {"enabled": False, "parameters": {}},
}

PFSENSE_INGEST_CONFIG_DESCRIPTIONS = {
    "block_events": "Retain all supported traffic blocked by pfSense.",
    "inbound_sensitive_port_allows": "Retain inbound TCP/UDP allows to canonical sensitive destination ports.",
    "all_allow_events": "Retain every supported allowed firewall event.",
    "dns_traffic": "Retain allowed TCP/UDP traffic whose destination port is 53; this is not DNS query content.",
    "icmp_traffic": "Retain allowed IPv4 ICMP traffic; blocked ICMP is covered by block retention.",
}


@dataclass(frozen=True)
class FilterDecision:
    retain: bool
    category: str
    reason: str


_counter_lock = threading.Lock()
_counter_started_at = datetime.now(timezone.utc)
_decision_counts = Counter()


def validate_sensitive_ports(value):
    if not isinstance(value, list) or not value or len(value) > MAX_SENSITIVE_PORTS:
        raise ValueError("sensitive_ports must be a non-empty bounded list")
    ports = []
    for value_item in value:
        if isinstance(value_item, bool) or not isinstance(value_item, int):
            raise ValueError("sensitive_ports must contain integers")
        if value_item < 1 or value_item > 65535:
            raise ValueError("sensitive_ports must be between 1 and 65535")
        ports.append(value_item)
    if len(set(ports)) != len(ports):
        raise ValueError("sensitive_ports must not contain duplicates")
    return sorted(ports)


def validate_config_entry(category, enabled, parameters):
    if category not in DEFAULT_PFSENSE_INGEST_CONFIG:
        raise ValueError("Unknown pfSense ingest filter category")
    if not isinstance(enabled, bool):
        raise ValueError("enabled must be a boolean")
    if isinstance(parameters, str):
        try:
            parameters = json.loads(parameters)
        except json.JSONDecodeError as error:
            raise ValueError("parameters must be valid JSON") from error
    if not isinstance(parameters, dict):
        raise ValueError("parameters must be an object")
    allowed = {"sensitive_ports"} if category == "inbound_sensitive_port_allows" else set()
    if set(parameters) - allowed:
        raise ValueError("Unknown pfSense ingest filter parameter")
    normalized = {}
    if category == "inbound_sensitive_port_allows":
        normalized["sensitive_ports"] = validate_sensitive_ports(
            parameters.get("sensitive_ports", list(DEFAULT_SENSITIVE_PORTS))
        )
    return {"enabled": enabled, "parameters": normalized}


def default_effective_policy(status="default"):
    return {
        "status": status,
        "categories": {
            key: {
                **validate_config_entry(key, value["enabled"], value["parameters"]),
                "description": PFSENSE_INGEST_CONFIG_DESCRIPTIONS[key],
                "has_override": False,
                "override_status": "default",
                "updated_by": None,
                "updated_at": None,
            }
            for key, value in DEFAULT_PFSENSE_INGEST_CONFIG.items()
        },
    }


def load_effective_policy(cur):
    """Load and validate all overrides as one unit; any fault uses safe defaults."""
    try:
        cur.execute("SAVEPOINT pfsense_ingest_config_read")
        cur.execute(
            """
            SELECT category, enabled, parameters, updated_by, updated_at
            FROM pfsense_ingest_config
            ORDER BY category
            """
        )
        rows = cur.fetchall()
        policy = default_effective_policy(status="applied")
        seen = set()
        for row in rows:
            category, enabled, parameters = row[:3]
            updated_by = row[3] if len(row) > 3 else None
            updated_at = row[4] if len(row) > 4 else None
            if category in seen:
                raise ValueError("duplicate pfSense ingest filter category")
            seen.add(category)
            policy["categories"][category] = {
                **validate_config_entry(category, enabled, parameters),
                "description": PFSENSE_INGEST_CONFIG_DESCRIPTIONS[category],
                "has_override": True,
                "override_status": "applied",
                "updated_by": updated_by,
                "updated_at": str(updated_at) if updated_at is not None else None,
            }
        cur.execute("RELEASE SAVEPOINT pfsense_ingest_config_read")
        return policy
    except Exception as error:
        try:
            cur.execute("ROLLBACK TO SAVEPOINT pfsense_ingest_config_read")
            cur.execute("RELEASE SAVEPOINT pfsense_ingest_config_read")
        except Exception:
            pass
        status = "invalid" if isinstance(error, ValueError) else "unavailable"
        logger.warning(
            "pfsense_ingest_filter_config fallback=safe_defaults status=%s reason=%s",
            status,
            type(error).__name__,
        )
        return default_effective_policy(status=status)


def evaluate_event(normalized_event, policy):
    raw = normalized_event.get("raw_payload") or {}
    categories = policy["categories"]
    action = str(raw.get("action") or "").lower()
    protocol = str(raw.get("protocol") or "").lower()
    direction = str(raw.get("direction") or "").lower()
    destination_port = raw.get("destination_port")

    if action == "block" and categories["block_events"]["enabled"]:
        return FilterDecision(True, "block_events", "blocked_traffic")
    if action == "pass" and categories["all_allow_events"]["enabled"]:
        return FilterDecision(True, "all_allow_events", "all_allowed_traffic")
    if action == "pass" and protocol == "icmp" and categories["icmp_traffic"]["enabled"]:
        return FilterDecision(True, "icmp_traffic", "allowed_icmp")
    if (
        action == "pass"
        and protocol in {"tcp", "udp"}
        and direction == "in"
        and destination_port in categories["inbound_sensitive_port_allows"]["parameters"]["sensitive_ports"]
        and categories["inbound_sensitive_port_allows"]["enabled"]
    ):
        return FilterDecision(True, "inbound_sensitive_port_allows", "inbound_sensitive_port")
    if (
        action == "pass"
        and protocol in {"tcp", "udp"}
        and destination_port == 53
        and categories["dns_traffic"]["enabled"]
    ):
        return FilterDecision(True, "dns_traffic", "allowed_port_53")
    return FilterDecision(False, "routine_allow", "no_enabled_retention_category")


def record_filter_decision(decision):
    key = f"{'retained' if decision.retain else 'filtered'}:{decision.reason}"
    with _counter_lock:
        _decision_counts[key] += 1


def get_filter_metrics():
    with _counter_lock:
        return {
            "started_at": _counter_started_at.isoformat(),
            "reset_on_process_restart": True,
            "counts": dict(_decision_counts),
            "listener_outcome_contract": [
                "forwarded",
                "filtered",
                "ingested",
                "rejected",
                "backend_failed",
            ],
            "listener_metrics_source": "pfsense listener process statistics",
        }


def get_all_effective_config():
    from core.db import get_db_connection

    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        return load_effective_policy(cur)
    except Exception as error:
        logger.warning(
            "pfsense_ingest_filter_config fallback=safe_defaults status=unavailable reason=%s",
            type(error).__name__,
        )
        return default_effective_policy(status="unavailable")
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def get_effective_sensitive_ports(cur):
    return tuple(load_effective_policy(cur)["categories"]["inbound_sensitive_port_allows"]["parameters"]["sensitive_ports"])


def upsert_config_override(cur, category, enabled, parameters, updated_by):
    """Validate then stage one atomic override; the owning API controls commit/audit."""
    validated = validate_config_entry(category, enabled, parameters)
    cur.execute(
        """
        INSERT INTO pfsense_ingest_config (category, enabled, parameters, updated_by, updated_at)
        VALUES (%s, %s, %s, %s, NOW())
        ON CONFLICT (category) DO UPDATE
        SET enabled = EXCLUDED.enabled,
            parameters = EXCLUDED.parameters,
            updated_by = EXCLUDED.updated_by,
            updated_at = NOW()
        """,
        (category, validated["enabled"], Json(validated["parameters"]), updated_by),
    )
    return validated
