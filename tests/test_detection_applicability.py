from types import MappingProxyType
from unittest.mock import MagicMock

import pytest

from engines.detection_applicability import (
    CANONICAL_SOURCE_IDENTITIES,
    RULE_APPLICABILITY,
    SourceIdentity,
    rule_applies_to_source,
    source_identity,
    validate_rule_inventory,
)
from engines.detection_config import get_detection_rule_defaults
import engines.detection_engine as detection_engine


def test_registry_is_immutable_complete_and_nonempty():
    assert isinstance(RULE_APPLICABILITY, MappingProxyType)
    validate_rule_inventory(get_detection_rule_defaults())
    assert len(RULE_APPLICABILITY) == 15
    assert all(item.allowed_sources for item in RULE_APPLICABILITY.values())


@pytest.mark.parametrize("identity", sorted(CANONICAL_SOURCE_IDENTITIES))
def test_exact_canonical_source_pairs_are_recognized(identity):
    assert source_identity(identity.source, identity.source_type) == identity


@pytest.mark.parametrize(
    ("source", "source_type"),
    [
        (None, None),
        ("", ""),
        ("unknown", "custom"),
        ("BANK_APP", "custom"),
        ("bank_app", "CUSTOM"),
        ("bank_app", "web_log"),
        ("nginx", "custom"),
        ("pfsense", "telemetry"),
    ],
)
def test_unknown_case_variant_and_mismatched_pairs_fail_closed(source, source_type):
    assert source_identity(source, source_type) is None
    assert all(not rule_applies_to_source(rule_id, source, source_type) for rule_id in RULE_APPLICABILITY)


def test_every_rule_accepts_exactly_its_registered_sources():
    for rule_id, applicability in RULE_APPLICABILITY.items():
        for identity in CANONICAL_SOURCE_IDENTITIES:
            assert rule_applies_to_source(rule_id, identity.source, identity.source_type) is (
                identity in applicability.allowed_sources
            )


def test_inactive_direct_detector_returns_before_sql():
    cur = MagicMock()
    result = detection_engine._generate_failed_login_alerts_core(
        cur,
        MagicMock(),
        source_ip="198.51.100.200",
        source="bank_app",
        source_type="custom",
        rule_config={"active": False, "parameters": {"threshold": 1, "window_minutes": 15}},
    )
    assert result == []
    cur.execute.assert_not_called()


def test_unsupported_direct_detector_returns_before_config_or_sql():
    cur = MagicMock()
    result = detection_engine._generate_port_scan_alerts_core(
        cur,
        MagicMock(),
        source_ip="198.51.100.201",
        source="nginx",
        source_type="web_log",
    )
    assert result == []
    cur.execute.assert_not_called()
