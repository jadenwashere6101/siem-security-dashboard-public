from __future__ import annotations

from core.canonical_action_vocabulary import (
    CanonicalActionValidationError,
    PLAYBOOK_ACTIONS,
    resolve_action_for_playbook,
)

CORE_ACTIONS: frozenset[str] = frozenset(
    {
        "monitor",
        "flag_high_priority",
        "require_approval",
        "branch",
        "trigger_playbook",
        "enrich_context",
    }
)

# spec: SPEC-PLAYBOOK-001 / SPEC-INTEG-002
ADAPTER_ACTIONS = {
    "notify_slack": ("slack", "send_message"),
    "notify_teams": ("teams", "send_message"),
    "notify_email": ("email", "send_email"),
    "block_ip": ("firewall", "block_ip"),
    "notify_webhook": ("webhook", "post_event"),
}

KNOWN_PLAYBOOK_ACTIONS: frozenset[str] = frozenset(PLAYBOOK_ACTIONS)
SUPPORTED_ACTIONS = KNOWN_PLAYBOOK_ACTIONS

APPROVAL_RISK_LEVELS: frozenset[str] = frozenset({"medium", "high", "critical"})
APPROVAL_TERMINAL_BEHAVIORS: frozenset[str] = frozenset({"fail", "branch"})
MIN_APPROVAL_TTL_MINUTES = 1
MAX_APPROVAL_TTL_MINUTES = 10080


def validate_playbook_steps(steps: list[dict], *, playbook_id: str | None = None) -> list[str]:
    """
    Return a list of validation error strings. Empty list means valid.

    Validates dynamic parameter binding syntax for string params; param shapes are
    action-specific and belong at execution time.
    """
    errors: list[str] = []
    if not isinstance(steps, list):
        return ["steps must be a list"]

    label_map = build_label_index_map(steps)
    label_counts: dict[str, int] = {}
    for step in steps:
        if isinstance(step, dict) and isinstance(step.get("label"), str) and step.get("label"):
            label = step["label"]
            label_counts[label] = label_counts.get(label, 0) + 1
    duplicate_labels = sorted(label for label, count in label_counts.items() if count > 1)
    if duplicate_labels:
        errors = [
            f"duplicate label {label!r} appears more than once in steps"
            for label in duplicate_labels
        ]
    else:
        errors = []

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
        try:
            action = resolve_action_for_playbook(action)
        except CanonicalActionValidationError as error:
            errors.append(f"{prefix}: {error}")
            continue
        if action not in KNOWN_PLAYBOOK_ACTIONS:
            errors.append(f"{prefix}: unsupported action {action!r}")
            continue

        errors.extend(validate_step_label(step, prefix=prefix))

        if action == "branch":
            errors.extend(
                validate_branch_step(step, step_index=index, label_map=label_map)
            )

        if action == "trigger_playbook":
            errors.extend(
                _validate_trigger_playbook_step(
                    step,
                    prefix=prefix,
                    playbook_id=playbook_id,
                )
            )

        if action == "enrich_context":
            errors.extend(_validate_enrich_context_step(step, prefix=prefix))

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

        errors.extend(validate_step_param_bindings(step, prefix=prefix))

    return errors


def _validate_enrich_context_step(step: dict, *, prefix: str) -> list[str]:
    params = step.get("params", {})
    if params is None:
        return []
    if not isinstance(params, dict):
        return [f"{prefix}: enrich_context params must be an object"]
    if "limit" in params:
        limit = params["limit"]
        if not isinstance(limit, int) or isinstance(limit, bool):
            return [f"{prefix}: enrich_context params.limit must be an integer"]
        if limit < 1 or limit > 25:
            return [f"{prefix}: enrich_context params.limit must be between 1 and 25"]
    return []


def _validate_trigger_playbook_step(
    step: dict,
    *,
    prefix: str,
    playbook_id: str | None,
) -> list[str]:
    params = step.get("params")
    if not isinstance(params, dict):
        return [f"{prefix}: trigger_playbook requires params object"]
    target = params.get("playbook_id")
    if not isinstance(target, str) or not target.strip():
        return [f"{prefix}: trigger_playbook requires params.playbook_id"]
    if playbook_id is not None and target.strip() == playbook_id:
        return [f"{prefix}: trigger_playbook cannot reference its own playbook id"]
    return []


# Imported here (after validate_playbook_steps and its validation helpers are
# defined) rather than at module top, to break a circular import:
# playbook_branch_conditions -> playbook_engine -> core.playbook_store ->
# playbook_registry.validate_playbook_steps. Importing these at the top would
# make Python reach core.playbook_store before validate_playbook_steps exists
# in this module's namespace, whenever playbook_registry is imported directly.
from engines.playbook_branch_conditions import (  # noqa: E402
    build_label_index_map,
    validate_branch_step,
    validate_step_label,
)
from engines.playbook_param_binding import validate_step_param_bindings  # noqa: E402
