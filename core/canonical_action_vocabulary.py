"""Canonical SOAR/analyst response action vocabulary.

One source of truth for producers, validators, queues, playbook definitions,
executors, and API serializers. Owning executor identifies which runtime path
may durable-enqueue or execute each action.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


class CanonicalActionValidationError(ValueError):
    """Raised when an action fails vocabulary or routing validation."""

    def __init__(self, message: str, *, code: str = "invalid_action"):
        super().__init__(message)
        self.code = code


# Owning execution paths
OWNER_RESPONSE_COMMAND = "response_command"
OWNER_RESPONSE_QUEUE = "response_queue"
OWNER_PLAYBOOK = "playbook"
OWNER_PLAYBOOK_READ_ONLY = "playbook_read_only"
OWNER_NOTIFICATION_ADAPTER = "notification_adapter"

MODE_TRACKING_ONLY = "tracking_only"
MODE_SIMULATION = "simulation"
MODE_REAL = "real"
MODE_READ_ONLY = "read_only"
MODE_INTERNAL = "internal"


@dataclass(frozen=True)
class CanonicalActionSpec:
    name: str
    owning_executor: str
    supported_modes: frozenset[str]
    aliases: frozenset[str] = frozenset()
    deprecated: bool = False
    description: str = ""
    validation_hint: str = ""


_CANONICAL_SPECS: tuple[CanonicalActionSpec, ...] = (
    CanonicalActionSpec(
        name="block_ip",
        owning_executor=OWNER_RESPONSE_COMMAND,
        supported_modes=frozenset({MODE_TRACKING_ONLY, MODE_SIMULATION}),
        description="SIEM Blocklist tracking only; no firewall enforcement.",
        validation_hint="Provide a public source_ip; protected/private targets are rejected.",
    ),
    CanonicalActionSpec(
        name="monitor",
        owning_executor=OWNER_RESPONSE_COMMAND,
        supported_modes=frozenset({MODE_INTERNAL, MODE_SIMULATION}),
        description="Durable internal watch disposition with optional expiry.",
        validation_hint="Provide source_ip and/or alert_id.",
    ),
    CanonicalActionSpec(
        name="flag_high_priority",
        owning_executor=OWNER_RESPONSE_COMMAND,
        supported_modes=frozenset({MODE_INTERNAL, MODE_SIMULATION}),
        aliases=frozenset({"escalate"}),
        description="Internal escalation via priority/incident handoff.",
        validation_hint="Provide alert_id (preferred) or source_ip for escalation context.",
    ),
    CanonicalActionSpec(
        name="stop_monitor",
        owning_executor=OWNER_RESPONSE_COMMAND,
        supported_modes=frozenset({MODE_INTERNAL}),
        description="Stop an active monitor/watch disposition without firewall changes.",
        validation_hint="Provide source_ip for the monitored indicator.",
    ),
    CanonicalActionSpec(
        name="remove_tracking",
        owning_executor=OWNER_RESPONSE_COMMAND,
        supported_modes=frozenset({MODE_TRACKING_ONLY}),
        aliases=frozenset({"unblock"}),
        description="Remove active Blocklist tracking; no firewall change.",
        validation_hint="Provide source_ip or an active blocked_ip context.",
    ),
    CanonicalActionSpec(
        name="add_note",
        owning_executor=OWNER_RESPONSE_COMMAND,
        supported_modes=frozenset({MODE_INTERNAL}),
        description="Append an analyst note to registry history without changing disposition.",
        validation_hint="Provide source_ip and a non-empty reason/note.",
    ),
    CanonicalActionSpec(
        name="enrich_context",
        owning_executor=OWNER_PLAYBOOK_READ_ONLY,
        supported_modes=frozenset({MODE_READ_ONLY}),
        description="Read-only playbook enrichment; never legacy response-action queue.",
        validation_hint="Use only as a playbook step; do not enqueue to response_actions_queue.",
    ),
    CanonicalActionSpec(
        name="notify_slack",
        owning_executor=OWNER_NOTIFICATION_ADAPTER,
        supported_modes=frozenset({MODE_SIMULATION, MODE_REAL}),
        description="Provider-specific Slack notification.",
    ),
    CanonicalActionSpec(
        name="notify_teams",
        owning_executor=OWNER_NOTIFICATION_ADAPTER,
        supported_modes=frozenset({MODE_SIMULATION, MODE_REAL}),
        description="Provider-specific Teams notification.",
    ),
    CanonicalActionSpec(
        name="notify_email",
        owning_executor=OWNER_NOTIFICATION_ADAPTER,
        supported_modes=frozenset({MODE_SIMULATION, MODE_REAL}),
        description="Provider-specific Email notification.",
    ),
    CanonicalActionSpec(
        name="notify_webhook",
        owning_executor=OWNER_NOTIFICATION_ADAPTER,
        supported_modes=frozenset({MODE_SIMULATION, MODE_REAL}),
        description="Provider-specific Webhook notification.",
    ),
    CanonicalActionSpec(
        name="require_approval",
        owning_executor=OWNER_PLAYBOOK,
        supported_modes=frozenset({MODE_INTERNAL}),
        description="Playbook approval gate.",
    ),
    CanonicalActionSpec(
        name="branch",
        owning_executor=OWNER_PLAYBOOK,
        supported_modes=frozenset({MODE_INTERNAL}),
        description="Playbook conditional branch.",
    ),
    CanonicalActionSpec(
        name="trigger_playbook",
        owning_executor=OWNER_PLAYBOOK,
        supported_modes=frozenset({MODE_INTERNAL}),
        description="Playbook chaining trigger.",
    ),
    # Deprecated ambiguous bare notify — never enqueue.
    CanonicalActionSpec(
        name="notify",
        owning_executor=OWNER_NOTIFICATION_ADAPTER,
        supported_modes=frozenset(),
        deprecated=True,
        description="Ambiguous bare notify; rejected unless a deterministic provider alias applies.",
        validation_hint=(
            "Replace bare 'notify' with notify_slack, notify_email, notify_webhook, or notify_teams."
        ),
    ),
)

CANONICAL_ACTIONS: Mapping[str, CanonicalActionSpec] = {
    spec.name: spec for spec in _CANONICAL_SPECS
}

# Alias → canonical name
ACTION_ALIASES: Mapping[str, str] = {
    alias: spec.name
    for spec in _CANONICAL_SPECS
    for alias in spec.aliases
}

# Actions the legacy response-action queue worker may still process.
RESPONSE_QUEUE_ACTIONS: frozenset[str] = frozenset(
    {"block_ip", "monitor", "flag_high_priority"}
)

# Analyst response commands (shared command service).
RESPONSE_COMMAND_ACTIONS: frozenset[str] = frozenset(
    {
        "block_ip",
        "monitor",
        "flag_high_priority",
        "stop_monitor",
        "remove_tracking",
        "add_note",
    }
)

# block_ip is both a response command and a playbook adapter action.
PLAYBOOK_ACTIONS: frozenset[str] = frozenset(
    {
        "monitor",
        "flag_high_priority",
        "require_approval",
        "branch",
        "trigger_playbook",
        "enrich_context",
        "notify_slack",
        "notify_teams",
        "notify_email",
        "notify_webhook",
        "block_ip",
    }
)


def normalize_action_name(action: str | None) -> str:
    raw = str(action or "").strip()
    if not raw:
        raise CanonicalActionValidationError("Action is required", code="missing_action")
    if raw in ACTION_ALIASES:
        return ACTION_ALIASES[raw]
    return raw


def get_action_spec(action: str | None) -> CanonicalActionSpec:
    name = normalize_action_name(action)
    spec = CANONICAL_ACTIONS.get(name)
    if spec is None:
        raise CanonicalActionValidationError(
            f"Unsupported action {name!r}",
            code="unsupported_action",
        )
    return spec


def resolve_action_for_playbook(action: str | None) -> str:
    """Validate and return canonical action name for playbook definition/execution."""
    spec = get_action_spec(action)
    if spec.name == "notify" or spec.deprecated and spec.name == "notify":
        raise CanonicalActionValidationError(
            "Ambiguous action 'notify' is not allowed. "
            "Use notify_slack, notify_email, notify_webhook, or notify_teams.",
            code="ambiguous_notify",
        )
    if spec.name not in PLAYBOOK_ACTIONS:
        raise CanonicalActionValidationError(
            f"Action {spec.name!r} is not a supported playbook action. "
            f"{spec.validation_hint}".strip(),
            code="unsupported_action",
        )
    return spec.name


def validate_action_for_response_queue(action: str | None) -> str:
    """Reject actions that must not enter response_actions_queue."""
    try:
        spec = get_action_spec(action)
    except CanonicalActionValidationError:
        raise

    if spec.name == "notify" or (spec.deprecated and not spec.supported_modes):
        raise CanonicalActionValidationError(
            "Ambiguous action 'notify' cannot be enqueued. "
            "Use notify_slack, notify_email, notify_webhook, or notify_teams before enqueueing.",
            code="ambiguous_notify",
        )
    if spec.name == "enrich_context":
        raise CanonicalActionValidationError(
            "Action 'enrich_context' is owned by the playbook read-only executor and "
            "cannot be enqueued to the legacy response-action queue.",
            code="misrouted_enrich_context",
        )
    if spec.name not in RESPONSE_QUEUE_ACTIONS:
        raise CanonicalActionValidationError(
            f"Action {spec.name!r} cannot be enqueued to the response-action queue. "
            f"{spec.validation_hint}".strip(),
            code="unsupported_action",
        )
    return spec.name


def validate_response_command_action(action: str | None) -> str:
    spec = get_action_spec(action)
    # Accept escalate/unblock aliases via normalize
    if spec.name not in RESPONSE_COMMAND_ACTIONS:
        raise CanonicalActionValidationError(
            f"Action {spec.name!r} is not a canonical response command "
            f"(block_ip, monitor, flag_high_priority, stop_monitor, "
            f"remove_tracking, add_note).",
            code="unsupported_action",
        )
    return spec.name
