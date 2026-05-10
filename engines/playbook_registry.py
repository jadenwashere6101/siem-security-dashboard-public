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
        "require_approval",
    }
)

APPROVAL_RISK_LEVELS: frozenset[str] = frozenset({"medium", "high", "critical"})
APPROVAL_TERMINAL_BEHAVIORS: frozenset[str] = frozenset({"fail"})
MIN_APPROVAL_TTL_MINUTES = 1
MAX_APPROVAL_TTL_MINUTES = 10080


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
            continue

        if action == "require_approval":
            risk_level = step.get("risk_level", "high")
            if risk_level not in APPROVAL_RISK_LEVELS:
                errors.append(
                    f"{prefix}: invalid risk_level {risk_level!r}; "
                    f"must be one of {sorted(APPROVAL_RISK_LEVELS)}"
                )

            if "expires_in_minutes" in step:
                ttl = step["expires_in_minutes"]
                if not isinstance(ttl, int) or isinstance(ttl, bool):
                    errors.append(f"{prefix}: expires_in_minutes must be an integer")
                elif ttl < MIN_APPROVAL_TTL_MINUTES or ttl > MAX_APPROVAL_TTL_MINUTES:
                    errors.append(
                        f"{prefix}: expires_in_minutes must be between "
                        f"{MIN_APPROVAL_TTL_MINUTES} and {MAX_APPROVAL_TTL_MINUTES}"
                    )

            if "reason" in step and not isinstance(step["reason"], str):
                errors.append(f"{prefix}: reason must be a string")

            for key in ("on_denied", "on_expired"):
                if key in step and step[key] not in APPROVAL_TERMINAL_BEHAVIORS:
                    errors.append(
                        f"{prefix}: invalid {key} {step[key]!r}; "
                        f"must be one of {sorted(APPROVAL_TERMINAL_BEHAVIORS)}"
                    )

        if "on_failure" in step:
            allowed = frozenset({"abort", "continue"})
            if step["on_failure"] not in allowed:
                errors.append(
                    f"{prefix}: invalid on_failure {step['on_failure']!r}; "
                    f"must be one of {sorted(allowed)}"
                )

    return errors
