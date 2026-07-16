"""Catalog-derived source applicability for implemented base detection rules."""

from types import MappingProxyType

from engines.detection_rule_catalog import (
    AZURE_INSIGHTS,
    BANK_APP,
    CANONICAL_SOURCE_IDENTITIES,
    HONEYPOT,
    NGINX,
    OPENTELEMETRY,
    PFSENSE,
    SourceApplicability as RuleApplicability,
    SourceIdentity,
    get_base_rule_catalog_records,
    get_detection_rule_catalog_record,
    serialize_source_applicability,
)


RULE_APPLICABILITY = MappingProxyType(
    {
        record.rule_id: RuleApplicability(
            classification=record.source_applicability.classification,
            allowed_sources=frozenset(record.source_applicability.allowed_sources),
        )
        for record in get_base_rule_catalog_records()
        if record.implementation_state == "implemented"
    }
)


def source_identity(source, source_type):
    """Return an exact canonical identity, or ``None`` without coercion."""
    candidate = SourceIdentity(source, source_type)
    return candidate if candidate in CANONICAL_SOURCE_IDENTITIES else None


def rule_applies_to_source(rule_id, source, source_type):
    identity = source_identity(source, source_type)
    applicability = RULE_APPLICABILITY.get(rule_id)
    return bool(identity and applicability and identity in applicability.allowed_sources)


def get_rule_applicability_metadata(rule_id):
    """Serialize the catalog-derived applicability for read-only API presentation."""
    return serialize_source_applicability(get_detection_rule_catalog_record(rule_id))


def validate_rule_inventory(rule_ids):
    configured = set(rule_ids)
    registered = set(RULE_APPLICABILITY)
    if configured != registered:
        missing = sorted(configured - registered)
        extra = sorted(registered - configured)
        raise ValueError(f"Detection applicability inventory mismatch: missing={missing}, extra={extra}")
    if any(not item.allowed_sources for item in RULE_APPLICABILITY.values()):
        raise ValueError("Every detection rule must have at least one applicable source")
