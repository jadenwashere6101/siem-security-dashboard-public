import ipaddress
from dataclasses import dataclass
from typing import Any, Dict, Optional, Set

from engines.soar_errors import RetryableActionError, SkippedAction


@dataclass(frozen=True)
class AdapterExecutionResult:
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None

    def as_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details is not None:
            payload["details"] = self.details
        return payload


class AdapterTerminalError(Exception):
    """Non-retryable adapter execution failure."""


class BaseSoarActionAdapter:
    adapter_name = "base"
    supported_actions: Set[str] = set()

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}

    def can_handle(self, action: Optional[str]) -> bool:
        return action in self.supported_actions

    def execute(self, row: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        raise NotImplementedError("Adapters must implement execute(row, context=None)")

    def test_connection(self) -> Dict[str, Any]:
        return {
            "code": "not_implemented",
            "message": f"{self.adapter_name} connection test is not implemented",
        }


def validate_public_ip_target(source_ip: Optional[str]) -> Any:
    if source_ip is None:
        raise SkippedAction(
            "Cannot execute IP-targeted action without source_ip",
            code="validation_null_source_ip",
        )
    try:
        parsed_ip = ipaddress.ip_address(str(source_ip))
    except ValueError as error:
        raise SkippedAction(
            f"Invalid source_ip for action: {source_ip}",
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
            f"Refusing to execute action against non-public source_ip: {source_ip}",
            code="validation_private_ip",
        )

    return parsed_ip


def classify_adapter_error(error: Exception) -> str:
    if isinstance(error, RetryableActionError):
        return "retryable"
    if isinstance(error, SkippedAction):
        return "skipped"
    return "terminal_failure"

