"""
Playbook step action registry (scaffold).

Handler wiring and step execution are Phase 2D — this module only validates
that step definitions reference known action names before definitions are persisted.
"""

from __future__ import annotations

SUPPORTED_ACTIONS: frozenset[str] = frozenset(
    {
        "block_ip",
        "monitor",
        "flag_high_priority",
    }
)


def validate_playbook_steps(steps: list[dict]) -> list[str]:
    """
    Return a list of validation error strings. Empty list means valid.

    Does not validate params — param shapes are action-specific and belong at execution time.
    """
    errors: list[str] = []
    if not isinstance(steps, list):
        return ["steps must be a list"]

    for index, step in enumerate(steps):
        prefix = f"step[{index}]"
        if not isinstance(step, dict):
            errors.append(f"{prefix}: must be a dict")
            continue
        if "action" not in step:
            errors.append(f"{prefix}: missing required key 'action'")
            continue
        action = step["action"]
        if not isinstance(action, str):
            errors.append(f"{prefix}: 'action' must be a string")
            continue
        if action not in SUPPORTED_ACTIONS:
            errors.append(f"{prefix}: unsupported action {action!r}")

        if "on_failure" in step:
            allowed = frozenset({"abort", "continue"})
            if step["on_failure"] not in allowed:
                errors.append(
                    f"{prefix}: invalid on_failure {step['on_failure']!r}; "
                    f"must be one of {sorted(allowed)}"
                )

    return errors
