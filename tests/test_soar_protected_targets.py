import pytest

from core.soar_protected_targets import (
    ProtectedTargetConfigError,
    is_protected_target,
    load_protected_targets,
    require_unprotected_target,
)
from engines.soar_errors import SkippedAction


def test_load_protected_targets_exact_ip_matching():
    networks = load_protected_targets({"SOAR_PROTECTED_IPS": "8.8.8.8"})

    assert is_protected_target("8.8.8.8", protected_networks=networks) is True
    assert is_protected_target("1.1.1.1", protected_networks=networks) is False


def test_load_protected_targets_cidr_matching():
    networks = load_protected_targets({"SOAR_PROTECTED_IPS": "8.8.8.0/24"})

    assert is_protected_target("8.8.8.9", protected_networks=networks) is True
    assert is_protected_target("8.8.9.9", protected_networks=networks) is False


def test_load_protected_targets_normalizes_whitespace_and_blank_entries():
    networks = load_protected_targets(
        {"SOAR_PROTECTED_IPS": " 8.8.8.8 , , 1.1.1.0/24 ,, "}
    )

    assert len(networks) == 2
    assert str(networks[0]) == "8.8.8.8/32"
    assert str(networks[1]) == "1.1.1.0/24"


def test_load_protected_targets_invalid_entry_fails_closed():
    with pytest.raises(ProtectedTargetConfigError):
        load_protected_targets({"SOAR_PROTECTED_IPS": "8.8.8.8,not-a-cidr"})


def test_require_unprotected_target_allows_non_protected_public_ip():
    networks = load_protected_targets({"SOAR_PROTECTED_IPS": "1.1.1.1,9.9.9.0/24"})
    require_unprotected_target("8.8.8.8", protected_networks=networks)


def test_require_unprotected_target_rejects_protected_target():
    networks = load_protected_targets({"SOAR_PROTECTED_IPS": "8.8.8.8"})
    with pytest.raises(SkippedAction) as exc_info:
        require_unprotected_target("8.8.8.8", protected_networks=networks)
    assert exc_info.value.code == "protected_target"
