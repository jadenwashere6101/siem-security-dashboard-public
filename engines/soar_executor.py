import ipaddress
import logging

from engines.soar_errors import RetryableActionError, SkippedAction


logger = logging.getLogger(__name__)

SUPPORTED_ACTIONS = {"block_ip", "flag_high_priority", "monitor"}


class AdapterBackedExecutor:
    def __init__(self, registry, context=None):
        self.registry = registry
        self.context = context or {}

    def __call__(self, row):
        action = row.get("action")
        adapter = self.registry.get_adapter_for_action(action)
        return adapter.execute(row, context=self.context)


class SimulationExecutor:
    def __call__(self, row):
        _validate_action(row)

        action = row["action"]
        if action == "block_ip":
            return self._simulate_block_ip(row)
        if action == "flag_high_priority":
            return self._simulate_flag_high_priority(row)
        if action == "monitor":
            return self._simulate_monitor(row)

        raise SkippedAction(
            f"Unsupported response action: {action}",
            code="unsupported_action",
        )

    def _simulate_block_ip(self, row):
        logger.info(
            "[SIMULATED BLOCK] queue_id=%s source_ip=%s alert_id=%s",
            row["id"],
            row["source_ip"],
            row["alert_id"],
        )
        return {
            "code": "simulated_block_ip",
            "message": f"Simulated IP block for {row['source_ip']}",
            "details": {
                "source_ip": row["source_ip"],
                "alert_id": row["alert_id"],
            },
        }

    def _simulate_flag_high_priority(self, row):
        logger.info(
            "[SIMULATED ESCALATION] queue_id=%s alert_id=%s source_ip=%s",
            row["id"],
            row["alert_id"],
            row["source_ip"],
        )
        return {
            "code": "simulated_flag_high_priority",
            "message": f"Simulated escalation for alert {row['alert_id']}",
            "details": {
                "alert_id": row["alert_id"],
                "source_ip": row["source_ip"],
            },
        }

    def _simulate_monitor(self, row):
        logger.info(
            "[SIMULATED MONITOR] queue_id=%s source_ip=%s alert_id=%s",
            row["id"],
            row["source_ip"],
            row["alert_id"],
        )
        return {
            "code": "simulated_monitor",
            "message": f"Monitoring only - no action taken for queue_id={row['id']}",
            "details": {
                "source_ip": row["source_ip"],
                "alert_id": row["alert_id"],
            },
        }


def _validate_action(row):
    action = row.get("action")
    if action not in SUPPORTED_ACTIONS:
        raise SkippedAction(
            f"Unsupported response action: {action}",
            code="unsupported_action",
        )

    if action == "block_ip":
        _validate_block_ip(row.get("source_ip"))
    elif action == "flag_high_priority" and row.get("alert_id") is None:
        raise SkippedAction(
            "Cannot flag high priority without an alert_id",
            code="validation_missing_alert_id",
        )
    elif action == "monitor" and row.get("source_ip") is None and row.get("alert_id") is None:
        raise SkippedAction(
            "Cannot monitor without a source_ip or alert_id",
            code="validation_no_target",
        )


def _validate_block_ip(source_ip):
    if source_ip is None:
        raise SkippedAction(
            "Cannot block IP without a source_ip",
            code="validation_null_source_ip",
        )

    try:
        parsed_ip = ipaddress.ip_address(str(source_ip))
    except ValueError as error:
        raise SkippedAction(
            f"Invalid source_ip for block_ip: {source_ip}",
            code="validation_invalid_ip_format",
        ) from error

    if (
        parsed_ip.is_private
        or parsed_ip.is_loopback
        or parsed_ip.is_link_local
        or parsed_ip.is_reserved
        or parsed_ip.is_unspecified
        or parsed_ip.is_multicast
    ):
        raise SkippedAction(
            f"Refusing to block non-public source_ip: {source_ip}",
            code="validation_private_ip",
        )
