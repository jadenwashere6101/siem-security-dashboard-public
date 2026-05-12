from __future__ import annotations

import ipaddress
import os
from typing import Mapping, Sequence

from engines.soar_errors import SkippedAction


class ProtectedTargetConfigError(ValueError):
    """Raised when SOAR protected-target configuration is invalid."""


def load_protected_targets(
    env: Mapping[str, str] | None = None,
) -> list[ipaddress._BaseNetwork]:
    # spec: SPEC-INTEG-002
    source = env if env is not None else os.environ
    raw_value = source.get("SOAR_PROTECTED_IPS", "")
    if raw_value is None:
        return []

    protected_networks: list[ipaddress._BaseNetwork] = []
    for raw_entry in str(raw_value).split(","):
        entry = raw_entry.strip()
        if not entry:
            continue
        protected_networks.append(_parse_entry_to_network(entry))
    return protected_networks


def is_protected_target(
    ip_address: str | None,
    protected_networks: Sequence[ipaddress._BaseNetwork] | None = None,
) -> bool:
    if ip_address is None:
        return False

    parsed_target = ipaddress.ip_address(str(ip_address))
    networks = (
        list(protected_networks)
        if protected_networks is not None
        else load_protected_targets()
    )
    return any(parsed_target in network for network in networks)


def require_unprotected_target(
    ip_address: str | None,
    protected_networks: Sequence[ipaddress._BaseNetwork] | None = None,
) -> None:
    if is_protected_target(ip_address, protected_networks=protected_networks):
        raise SkippedAction(
            f"Refusing to block protected target: {ip_address}",
            code="protected_target",
        )


def _parse_entry_to_network(entry: str) -> ipaddress._BaseNetwork:
    try:
        if "/" in entry:
            return ipaddress.ip_network(entry, strict=False)
        parsed_ip = ipaddress.ip_address(entry)
        prefix = 32 if parsed_ip.version == 4 else 128
        return ipaddress.ip_network(f"{parsed_ip}/{prefix}", strict=True)
    except ValueError as error:
        raise ProtectedTargetConfigError(
            f"Invalid SOAR_PROTECTED_IPS entry: {entry}"
        ) from error
