"""
Dynamic playbook step parameter binding.

Resolves whole-value {{alert.<field>}} and {{execution.<field>}} expressions at
execution time against the triggering alert and execution metadata.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any

BINDING_EXPRESSION_RE = re.compile(r"^\{\{(alert|execution)\.([a-z][a-z0-9_]*)\}\}$")

ALERT_BINDING_FIELDS: frozenset[str] = frozenset(
    {
        "id",
        "alert_type",
        "severity",
        "source_ip",
        "source",
        "source_type",
        "message",
        "status",
        "country",
        "city",
        "latitude",
        "longitude",
        "reputation_score",
        "reputation_label",
        "reputation_source",
        "reputation_summary",
        "response_action",
        "response_status",
        "created_at",
    }
)

EXECUTION_BINDING_FIELDS: frozenset[str] = frozenset(
    {
        "id",
        "playbook_id",
        "alert_id",
    }
)

ALLOWED_BINDING_FIELDS: dict[str, frozenset[str]] = {
    "alert": ALERT_BINDING_FIELDS,
    "execution": EXECUTION_BINDING_FIELDS,
}


class PlaybookParamBindingError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def parse_binding_expression(value: Any) -> tuple[str, str] | None:
    if not isinstance(value, str) or "{{" not in value:
        return None
    match = BINDING_EXPRESSION_RE.match(value)
    if match is None:
        return None
    return match.group(1), match.group(2)


def validate_param_binding_value(value: Any, *, prefix: str) -> list[str]:
    if not isinstance(value, str) or "{{" not in value:
        return []

    parsed = parse_binding_expression(value)
    if parsed is None:
        return [
            f"{prefix}: invalid binding expression {value!r}; "
            "expected whole-value form {{alert.<field>}} or {{execution.<field>}}"
        ]

    namespace, field = parsed
    allowed = ALLOWED_BINDING_FIELDS.get(namespace)
    if allowed is None or field not in allowed:
        return [f"{prefix}: unsupported {namespace} binding field {field!r}"]

    return []


def validate_step_param_bindings(step: dict[str, Any], *, prefix: str) -> list[str]:
    params = step.get("params")
    if not isinstance(params, dict):
        return []

    errors: list[str] = []
    for key, value in params.items():
        errors.extend(
            validate_param_binding_value(value, prefix=f"{prefix}.params.{key}")
        )
    return errors


def resolve_step_params(
    conn,
    params: dict[str, Any],
    *,
    execution: dict[str, Any],
    alert_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not params:
        return {}

    needs_alert = False
    for value in params.values():
        parsed = parse_binding_expression(value)
        if parsed is not None and parsed[0] == "alert":
            needs_alert = True
            break

    alert = alert_snapshot
    if needs_alert and alert is None:
        alert_id = execution.get("alert_id")
        if alert_id is None:
            raise PlaybookParamBindingError(
                "binding_alert_context_missing",
                "Dynamic alert binding requires an alert_id on the execution.",
            )
        # Import lazily to avoid a standalone import cycle through
        # playbook_engine -> playbook_store -> playbook_registry.
        from engines.playbook_engine import _fetch_alert

        alert = _fetch_alert(conn, alert_id)
        if alert is None:
            raise PlaybookParamBindingError(
                "binding_alert_not_found",
                f"Alert {alert_id} was not found for parameter binding.",
            )

    resolved: dict[str, Any] = {}
    for key, value in params.items():
        parsed = parse_binding_expression(value)
        if parsed is None:
            resolved[key] = value
            continue

        namespace, field = parsed
        if namespace == "alert":
            if alert is None:
                raise PlaybookParamBindingError(
                    "binding_alert_context_missing",
                    "Dynamic alert binding requires an alert_id on the execution.",
                )
            raw = alert.get(field)
        else:
            raw = _execution_binding_value(execution, field)

        if raw is None:
            raise PlaybookParamBindingError(
                "binding_field_missing",
                f"Binding field {namespace}.{field} is missing or null.",
            )

        resolved[key] = _coerce_binding_value(raw)

    return resolved


def _execution_binding_value(execution: dict[str, Any], field: str) -> Any:
    if field == "id":
        return execution.get("id")
    if field == "playbook_id":
        return execution.get("playbook_id")
    if field == "alert_id":
        return execution.get("alert_id")
    return None


def _coerce_binding_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    return value
