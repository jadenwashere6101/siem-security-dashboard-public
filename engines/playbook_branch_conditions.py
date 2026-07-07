"""
Playbook branch condition evaluation and validation helpers.

Reuses ALERT_BINDING_FIELDS from playbook_param_binding. The alert fetch helper
is imported lazily to keep this module importable standalone.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

from engines.playbook_param_binding import ALERT_BINDING_FIELDS

LABEL_RE = re.compile(r"^[a-z][a-z0-9_]*$")

BRANCH_CONDITION_SOURCES: frozenset[str] = frozenset(
    {"alert", "previous_step", "approval"}
)

EQUALITY_OPS: frozenset[str] = frozenset({"==", "!="})
ORDINAL_OPS: frozenset[str] = frozenset({">=", ">", "<=", "<"})
NUMERIC_ALERT_FIELDS: frozenset[str] = frozenset(
    {"id", "reputation_score", "latitude", "longitude"}
)
STRING_ALERT_FIELDS: frozenset[str] = ALERT_BINDING_FIELDS - NUMERIC_ALERT_FIELDS - frozenset(
    {"severity"}
)

PREVIOUS_STEP_STATUS_VALUES: frozenset[str] = frozenset({"success", "failed", "skipped"})
APPROVAL_STATUS_VALUES: frozenset[str] = frozenset({"approved", "denied", "expired"})

SEVERITY_RANK: dict[str, int] = {
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}


class PlaybookBranchConditionError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def build_label_index_map(steps: list[dict[str, Any]]) -> dict[str, int]:
    label_map: dict[str, int] = {}
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        label = step.get("label")
        if not isinstance(label, str) or not label:
            continue
        label_map[label] = index
    return label_map


def validate_step_label(step: dict[str, Any], *, prefix: str) -> list[str]:
    label = step.get("label")
    if label is None:
        return []
    if not isinstance(label, str) or not label:
        return [f"{prefix}: label must be a non-empty string"]
    if not LABEL_RE.fullmatch(label):
        return [
            f"{prefix}: invalid label {label!r}; "
            "expected form matching ^[a-z][a-z0-9_]*$"
        ]
    return []


def validate_branch_condition(condition: Any, *, prefix: str) -> list[str]:
    if not isinstance(condition, dict):
        return [f"{prefix}: condition must be an object"]

    source = condition.get("source")
    field = condition.get("field")
    op = condition.get("op")
    value = condition.get("value")

    if source not in BRANCH_CONDITION_SOURCES:
        return [
            f"{prefix}: invalid condition.source {source!r}; "
            f"must be one of {sorted(BRANCH_CONDITION_SOURCES)}"
        ]
    if not isinstance(field, str) or not field:
        return [f"{prefix}: condition.field must be a non-empty string"]
    if not isinstance(op, str) or op not in (EQUALITY_OPS | ORDINAL_OPS):
        return [f"{prefix}: invalid condition.op {op!r}"]

    if source == "alert":
        if field not in ALERT_BINDING_FIELDS:
            return [f"{prefix}: unsupported alert condition field {field!r}"]
        allowed_ops = _allowed_ops_for_alert_field(field)
        if op not in allowed_ops:
            return [
                f"{prefix}: operator {op!r} is not valid for alert field {field!r}"
            ]
        return _validate_condition_value_type(field, value, prefix=prefix)

    if source == "previous_step":
        if field != "status":
            return [f"{prefix}: previous_step conditions must use field 'status'"]
        if op not in EQUALITY_OPS:
            return [f"{prefix}: previous_step conditions support only == and !="]
        if value not in PREVIOUS_STEP_STATUS_VALUES:
            return [
                f"{prefix}: previous_step condition value must be one of "
                f"{sorted(PREVIOUS_STEP_STATUS_VALUES)}"
            ]
        return []

    if field != "status":
        return [f"{prefix}: approval conditions must use field 'status'"]
    if op not in EQUALITY_OPS:
        return [f"{prefix}: approval conditions support only == and !="]
    if value not in APPROVAL_STATUS_VALUES:
        return [
            f"{prefix}: approval condition value must be one of "
            f"{sorted(APPROVAL_STATUS_VALUES)}"
        ]
    return []


def validate_branch_step(
    step: dict[str, Any],
    *,
    step_index: int,
    label_map: dict[str, int],
) -> list[str]:
    prefix = f"step[{step_index}]"
    errors: list[str] = []

    condition = step.get("condition")
    goto_true = step.get("goto_true")
    goto_false = step.get("goto_false")

    if not isinstance(condition, dict):
        errors.append(f"{prefix}: branch step requires condition object")
    else:
        errors.extend(validate_branch_condition(condition, prefix=f"{prefix}.condition"))

    if not isinstance(goto_true, str) or not goto_true:
        errors.append(f"{prefix}: branch step requires non-empty goto_true")
    else:
        errors.extend(
            _validate_branch_target(
                goto_true,
                branch_index=step_index,
                label_map=label_map,
                prefix=f"{prefix}.goto_true",
            )
        )

    if goto_false is not None:
        if not isinstance(goto_false, str) or not goto_false:
            errors.append(f"{prefix}: goto_false must be a non-empty string when set")
        else:
            errors.extend(
                _validate_branch_target(
                    goto_false,
                    branch_index=step_index,
                    label_map=label_map,
                    prefix=f"{prefix}.goto_false",
                )
            )

    return errors


def evaluate_branch_condition(
    conn,
    condition: dict[str, Any],
    *,
    execution: dict[str, Any],
    steps_log: list[dict[str, Any]],
) -> bool:
    source = condition["source"]
    field = condition["field"]
    op = condition["op"]
    expected = condition["value"]

    if source == "alert":
        actual = _resolve_alert_field(conn, execution, field)
        return _compare_values(actual, op, expected, field=field)

    if source == "previous_step":
        actual = _latest_previous_step_status(steps_log)
        if actual is None:
            raise PlaybookBranchConditionError(
                "branch_context_missing",
                "No previous step outcome is available for branch evaluation.",
            )
        return _compare_equality(actual, op, expected)

    actual = _latest_approval_decision_status(steps_log)
    if actual is None:
        raise PlaybookBranchConditionError(
            "branch_context_missing",
            "No approval gate decision is available for branch evaluation.",
        )
    return _compare_equality(actual, op, expected)


def resolve_label_target_index(
    steps: list[dict[str, Any]],
    label: str,
    *,
    branch_index: int,
) -> int | None:
    label_map = build_label_index_map(steps)
    target = label_map.get(label)
    if target is None or target <= branch_index:
        return None
    return target


def _validate_branch_target(
    label: str,
    *,
    branch_index: int,
    label_map: dict[str, int],
    prefix: str,
) -> list[str]:
    if label not in label_map:
        return [f"{prefix}: unknown label {label!r}"]
    target_index = label_map[label]
    if target_index <= branch_index:
        return [
            f"{prefix}: label {label!r} resolves to step[{target_index}], "
            f"which is not forward of branch step[{branch_index}]"
        ]
    return []


def _allowed_ops_for_alert_field(field: str) -> frozenset[str]:
    if field == "severity" or field in NUMERIC_ALERT_FIELDS:
        return EQUALITY_OPS | ORDINAL_OPS
    return EQUALITY_OPS


def _validate_condition_value_type(field: str, value: Any, *, prefix: str) -> list[str]:
    if field in NUMERIC_ALERT_FIELDS:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return [f"{prefix}: condition.value must be a number for field {field!r}"]
        return []
    if not isinstance(value, str):
        return [f"{prefix}: condition.value must be a string for field {field!r}"]
    return []


def _resolve_alert_field(conn, execution: dict[str, Any], field: str) -> Any:
    alert_id = execution.get("alert_id")
    if alert_id is None:
        raise PlaybookBranchConditionError(
            "binding_alert_context_missing",
            "Alert-sourced branch condition requires an alert_id on the execution.",
        )
    # Import lazily to avoid a standalone import cycle through
    # playbook_engine -> playbook_store -> playbook_registry.
    from engines.playbook_engine import _fetch_alert

    alert = _fetch_alert(conn, alert_id)
    if alert is None:
        raise PlaybookBranchConditionError(
            "binding_alert_not_found",
            f"Alert {alert_id} was not found for branch evaluation.",
        )
    value = alert.get(field)
    if value is None:
        raise PlaybookBranchConditionError(
            "binding_field_missing",
            f"Branch condition field alert.{field} is missing or null.",
        )
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    return value


def _latest_previous_step_status(steps_log: list[dict[str, Any]]) -> str | None:
    for entry in reversed(steps_log):
        if not isinstance(entry, dict):
            continue
        status = entry.get("status")
        if status in PREVIOUS_STEP_STATUS_VALUES and isinstance(entry.get("step_index"), int):
            return str(status)
    return None


def _latest_approval_decision_status(steps_log: list[dict[str, Any]]) -> str | None:
    for entry in reversed(steps_log):
        if not isinstance(entry, dict) or entry.get("action") != "require_approval":
            continue
        event = entry.get("event")
        if event == "approval_approved":
            return "approved"
        if event == "approval_denied":
            return "denied"
        if event == "approval_expired":
            return "expired"
    return None


def _compare_values(actual: Any, op: str, expected: Any, *, field: str) -> bool:
    if field == "severity":
        return _compare_severity(str(actual), op, str(expected))
    if field in NUMERIC_ALERT_FIELDS:
        return _compare_numeric(actual, op, expected)
    return _compare_equality(str(actual), op, str(expected))


def _compare_severity(actual: str, op: str, expected: str) -> bool:
    actual_rank = SEVERITY_RANK.get(actual.strip().lower())
    expected_rank = SEVERITY_RANK.get(expected.strip().lower())
    if actual_rank is None or expected_rank is None:
        raise PlaybookBranchConditionError(
            "branch_condition_invalid",
            f"Unsupported severity value in branch comparison: {actual!r} vs {expected!r}",
        )
    return _compare_numeric(actual_rank, op, expected_rank)


def _compare_numeric(actual: Any, op: str, expected: Any) -> bool:
    left = float(actual)
    right = float(expected)
    if op == "==":
        return left == right
    if op == "!=":
        return left != right
    if op == ">=":
        return left >= right
    if op == ">":
        return left > right
    if op == "<=":
        return left <= right
    if op == "<":
        return left < right
    raise PlaybookBranchConditionError(
        "branch_condition_invalid",
        f"Unsupported numeric comparison operator: {op!r}",
    )


def _compare_equality(actual: str, op: str, expected: Any) -> bool:
    left = str(actual)
    right = str(expected)
    if op == "==":
        return left == right
    if op == "!=":
        return left != right
    raise PlaybookBranchConditionError(
        "branch_condition_invalid",
        f"Unsupported equality comparison operator: {op!r}",
    )
