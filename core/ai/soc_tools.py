from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import ipaddress
from typing import Any

TOOL_STATUS_SUCCESS = "success"
TOOL_STATUS_VALIDATION_ERROR = "validation_error"
TOOL_STATUS_FORBIDDEN = "forbidden"
TOOL_STATUS_UNSUPPORTED = "unsupported_tool"
TOOL_STATUS_NOT_FOUND = "not_found"
TOOL_STATUS_FAILED = "failed"
TOOL_STATUS_TRUNCATED = "truncated"

ROLE_ANALYST = "analyst"
ROLE_SUPER_ADMIN = "super_admin"

DEFAULT_MAX_TOOL_CALLS = 5
DEFAULT_TOOL_LIMIT = 25
MAX_TOOL_LIMIT = 25
DEFAULT_TIME_WINDOW_HOURS = 24
MAX_TIME_WINDOW_HOURS = 168

SENSITIVE_KEY_FRAGMENTS = frozenset(
    {
        "authorization",
        "cookie",
        "credential",
        "database_url",
        "dsn",
        "password",
        "private_key",
        "secret",
        "token",
        "api_key",
    }
)

MUTATION_TOOL_FRAGMENTS = frozenset(
    {
        "update",
        "delete",
        "insert",
        "create",
        "execute",
        "approve",
        "deny",
        "block",
        "unblock",
        "retry",
        "resume",
        "abandon",
        "migrate",
        "shell",
        "file",
        "write",
        "commit",
        "push",
        "deploy",
    }
)


@dataclass(frozen=True)
class SocToolDefinition:
    name: str
    description: str
    required_args: tuple[str, ...] = ()
    optional_args: tuple[str, ...] = ()
    minimum_role: str = ROLE_ANALYST
    max_results: int = DEFAULT_TOOL_LIMIT
    source_path: str = ""
    source_helper: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SocToolSource:
    tool_name: str
    source_type: str
    source_path: str
    source_helper: str
    record_ids: list[int | str] = field(default_factory=list)
    generated_at: str | None = None
    status: str = TOOL_STATUS_SUCCESS
    truncated: bool = False
    omitted_count: int = 0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SocToolResult:
    tool_name: str
    status: str
    data: Any = None
    sources: list[SocToolSource] = field(default_factory=list)
    truncated: bool = False
    omitted_count: int = 0
    latency_ms: int = 0
    error_code: str | None = None
    error: str | None = None
    read_only: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "status": self.status,
            "data": redact_sensitive_values(self.data),
            "sources": [source.as_dict() for source in self.sources],
            "truncated": self.truncated,
            "omitted_count": self.omitted_count,
            "latency_ms": self.latency_ms,
            "error_code": self.error_code,
            "error": self.error,
            "read_only": self.read_only,
        }


@dataclass(frozen=True)
class SocToolExecutionSummary:
    used: bool
    calls: list[SocToolResult] = field(default_factory=list)
    sources: list[SocToolSource] = field(default_factory=list)
    truncated: bool = False
    omitted_count: int = 0
    read_only: bool = True
    error_code: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "used": self.used,
            "calls": [call.as_dict() for call in self.calls],
            "sources": [source.as_dict() for source in self.sources],
            "truncated": self.truncated,
            "omitted_count": self.omitted_count,
            "read_only": self.read_only,
            "error_code": self.error_code,
        }


TOOL_DEFINITIONS: dict[str, SocToolDefinition] = {
    "search_alerts": SocToolDefinition(
        name="search_alerts",
        description="Search alert list using canonical alert filters.",
        optional_args=("search", "source_ip", "severity", "status", "source", "limit", "offset", "sort"),
        source_path="/alerts",
        source_helper="routes.alerts_events_routes alert list helpers",
    ),
    "get_alert_detail": SocToolDefinition(
        name="get_alert_detail",
        description="Read canonical alert detail and related evidence.",
        required_args=("alert_id",),
        source_path="/alerts/<id>",
        source_helper="core.ai.context_builder alert context",
    ),
    "get_related_events": SocToolDefinition(
        name="get_related_events",
        description="Read bounded related events for an alert, recon activity, or source IP.",
        optional_args=("alert_id", "activity_id", "source_ip", "source", "event_type", "limit"),
        source_path="/events/search",
        source_helper="routes.alerts_events_routes related event helpers",
    ),
    "get_source_ip_context": SocToolDefinition(
        name="get_source_ip_context",
        description="Read canonical aggregated source IP context.",
        required_args=("source_ip",),
        source_path="/source-ip-context",
        source_helper="core.ai.context_builder source_ip context",
    ),
    "search_incidents": SocToolDefinition(
        name="search_incidents",
        description="Search incident list using canonical incident filters.",
        optional_args=("status", "severity", "operational_scope", "limit", "offset"),
        source_path="/incidents",
        source_helper="core.incident_store.list_incidents",
    ),
    "get_incident_timeline": SocToolDefinition(
        name="get_incident_timeline",
        description="Read canonical incident detail and read-only timeline.",
        required_args=("incident_id",),
        source_path="/incidents/<id>/timeline",
        source_helper="routes.incident_routes.build_readonly_incident_timeline",
    ),
    "list_playbook_executions": SocToolDefinition(
        name="list_playbook_executions",
        description="List bounded playbook executions with outcome metadata.",
        optional_args=("playbook_id", "status", "limit"),
        source_path="/playbook-executions",
        source_helper="core.playbook_store.list_playbook_executions",
    ),
    "read_audit_log": SocToolDefinition(
        name="read_audit_log",
        description="Read bounded audit metadata.",
        optional_args=("limit",),
        minimum_role=ROLE_SUPER_ADMIN,
        source_path="/admin/audit-log",
        source_helper="routes.admin_routes audit-log read semantics",
    ),
    "get_response_registry_context": SocToolDefinition(
        name="get_response_registry_context",
        description="Read response registry detail context.",
        optional_args=("registry_id", "source_ip", "limit"),
        source_path="/response-registry/<id>",
        source_helper="core.indicator_response_registry.get_registry_detail",
    ),
}

SUPPORTED_TOOL_NAMES = frozenset(TOOL_DEFINITIONS)


class SocToolValidationError(ValueError):
    def __init__(self, message: str, *, error_code: str = TOOL_STATUS_VALIDATION_ERROR):
        super().__init__(message)
        self.error_code = error_code


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def redact_sensitive_values(value: Any) -> Any:
    if isinstance(value, dict):
        redacted = {}
        for key, child in value.items():
            key_text = str(key)
            normalized_key = key_text.lower().replace("-", "_")
            if any(fragment in normalized_key for fragment in SENSITIVE_KEY_FRAGMENTS):
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = redact_sensitive_values(child)
        return redacted
    if isinstance(value, list):
        return [redact_sensitive_values(item) for item in value]
    return value


def has_mutation_intent(tool_name: str) -> bool:
    normalized = str(tool_name or "").lower().replace("-", "_")
    return any(fragment in normalized for fragment in MUTATION_TOOL_FRAGMENTS)


def parse_positive_int(value: Any, field_name: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise SocToolValidationError(f"{field_name} must be an integer") from error
    if parsed <= 0:
        raise SocToolValidationError(f"{field_name} must be positive")
    return parsed


def parse_limit(value: Any, *, default: int = DEFAULT_TOOL_LIMIT, maximum: int = MAX_TOOL_LIMIT) -> int:
    if value in (None, ""):
        return min(default, maximum)
    return min(parse_positive_int(value, "limit"), maximum)


def parse_source_ip(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise SocToolValidationError("source_ip is required")
    try:
        return str(ipaddress.ip_address(text))
    except ValueError as error:
        raise SocToolValidationError("source_ip is invalid") from error


def normalize_text(value: Any, *, field_name: str, max_len: int = 200) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) > max_len:
        raise SocToolValidationError(f"{field_name} is too long")
    if any(fragment in field_name.lower() for fragment in SENSITIVE_KEY_FRAGMENTS):
        raise SocToolValidationError(f"{field_name} is not allowed")
    return text


def validate_tool_name(name: Any) -> str:
    normalized = str(name or "").strip().lower()
    if not normalized:
        raise SocToolValidationError("tool name is required")
    if normalized not in SUPPORTED_TOOL_NAMES:
        code = "mutation_tool_rejected" if has_mutation_intent(normalized) else TOOL_STATUS_UNSUPPORTED
        raise SocToolValidationError(f"Unsupported SOC read tool: {normalized}", error_code=code)
    return normalized


def validate_tool_args(tool_name: str, raw_args: Any) -> dict[str, Any]:
    definition = TOOL_DEFINITIONS[tool_name]
    args = raw_args if isinstance(raw_args, dict) else {}
    for required in definition.required_args:
        if args.get(required) in (None, ""):
            raise SocToolValidationError(f"{required} is required")

    if tool_name == "search_alerts":
        return {
            "search": normalize_text(args.get("search"), field_name="search"),
            "source_ip": parse_source_ip(args.get("source_ip")) if args.get("source_ip") else None,
            "severity": normalize_text(args.get("severity"), field_name="severity", max_len=20),
            "status": normalize_text(args.get("status"), field_name="status", max_len=40),
            "source": normalize_text(args.get("source"), field_name="source", max_len=80),
            "limit": parse_limit(args.get("limit")),
            "offset": parse_non_negative_int(args.get("offset"), "offset"),
            "sort": normalize_text(args.get("sort"), field_name="sort", max_len=20) or "newest",
        }
    if tool_name == "get_alert_detail":
        return {"alert_id": parse_positive_int(args.get("alert_id"), "alert_id")}
    if tool_name == "get_related_events":
        if not any(args.get(name) for name in ("alert_id", "activity_id", "source_ip")):
            raise SocToolValidationError("alert_id, activity_id, or source_ip is required")
        return {
            "alert_id": parse_positive_int(args.get("alert_id"), "alert_id") if args.get("alert_id") else None,
            "activity_id": parse_positive_int(args.get("activity_id"), "activity_id") if args.get("activity_id") else None,
            "source_ip": parse_source_ip(args.get("source_ip")) if args.get("source_ip") else None,
            "source": normalize_text(args.get("source"), field_name="source", max_len=80),
            "event_type": normalize_text(args.get("event_type"), field_name="event_type", max_len=80),
            "limit": parse_limit(args.get("limit")),
        }
    if tool_name == "get_source_ip_context":
        return {"source_ip": parse_source_ip(args.get("source_ip"))}
    if tool_name == "search_incidents":
        severity = normalize_text(args.get("severity"), field_name="severity", max_len=20)
        return {
            "status": normalize_text(args.get("status"), field_name="status", max_len=40),
            "severity": severity.upper() if severity else None,
            "operational_scope": normalize_text(args.get("operational_scope"), field_name="operational_scope", max_len=80),
            "limit": parse_limit(args.get("limit")),
            "offset": parse_non_negative_int(args.get("offset"), "offset"),
        }
    if tool_name == "get_incident_timeline":
        return {"incident_id": parse_positive_int(args.get("incident_id"), "incident_id")}
    if tool_name == "list_playbook_executions":
        return {
            "playbook_id": normalize_text(args.get("playbook_id"), field_name="playbook_id", max_len=80),
            "status": normalize_text(args.get("status"), field_name="status", max_len=40),
            "limit": parse_limit(args.get("limit")),
        }
    if tool_name == "read_audit_log":
        return {"limit": parse_limit(args.get("limit"))}
    if tool_name == "get_response_registry_context":
        if not args.get("registry_id") and not args.get("source_ip"):
            raise SocToolValidationError("registry_id or source_ip is required")
        return {
            "registry_id": parse_positive_int(args.get("registry_id"), "registry_id") if args.get("registry_id") else None,
            "source_ip": parse_source_ip(args.get("source_ip")) if args.get("source_ip") else None,
            "limit": parse_limit(args.get("limit")),
        }

    raise SocToolValidationError(f"Unsupported SOC read tool: {tool_name}", error_code=TOOL_STATUS_UNSUPPORTED)


def role_can_use_tool(role: str | None, tool_name: str) -> bool:
    definition = TOOL_DEFINITIONS[tool_name]
    if definition.minimum_role == ROLE_SUPER_ADMIN:
        return role == ROLE_SUPER_ADMIN
    return role in {ROLE_ANALYST, ROLE_SUPER_ADMIN}


def parse_non_negative_int(value: Any, field_name: str) -> int:
    if value in (None, ""):
        return 0
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise SocToolValidationError(f"{field_name} must be an integer") from error
    if parsed < 0:
        raise SocToolValidationError(f"{field_name} must be non-negative")
    return parsed


__all__ = [
    "DEFAULT_MAX_TOOL_CALLS",
    "DEFAULT_TIME_WINDOW_HOURS",
    "DEFAULT_TOOL_LIMIT",
    "MAX_TIME_WINDOW_HOURS",
    "MAX_TOOL_LIMIT",
    "SUPPORTED_TOOL_NAMES",
    "TOOL_DEFINITIONS",
    "TOOL_STATUS_FAILED",
    "TOOL_STATUS_FORBIDDEN",
    "TOOL_STATUS_NOT_FOUND",
    "TOOL_STATUS_SUCCESS",
    "TOOL_STATUS_TRUNCATED",
    "TOOL_STATUS_UNSUPPORTED",
    "TOOL_STATUS_VALIDATION_ERROR",
    "SocToolDefinition",
    "SocToolExecutionSummary",
    "SocToolResult",
    "SocToolSource",
    "SocToolValidationError",
    "redact_sensitive_values",
    "role_can_use_tool",
    "utc_now",
    "validate_tool_args",
    "validate_tool_name",
]
