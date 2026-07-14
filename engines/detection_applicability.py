"""Immutable source applicability for base detection rules.

Source coverage is code-owned, read-only policy. Runtime threshold and window
overrides remain global per rule in ``detection_config``.
"""

from dataclasses import dataclass
from types import MappingProxyType


@dataclass(frozen=True, order=True)
class SourceIdentity:
    source: str
    source_type: str


HONEYPOT = SourceIdentity("honeypot", "honeypot")
BANK_APP = SourceIdentity("bank_app", "custom")
PFSENSE = SourceIdentity("pfsense", "firewall")
NGINX = SourceIdentity("nginx", "web_log")
AZURE_INSIGHTS = SourceIdentity("azure_insights", "cloud_api")
OPENTELEMETRY = SourceIdentity("opentelemetry", "telemetry")

CANONICAL_SOURCE_IDENTITIES = frozenset(
    {HONEYPOT, BANK_APP, PFSENSE, NGINX, AZURE_INSIGHTS, OPENTELEMETRY}
)


@dataclass(frozen=True)
class RuleApplicability:
    classification: str
    allowed_sources: frozenset[SourceIdentity]


RULE_APPLICABILITY = MappingProxyType(
    {
        "failed_login_threshold": RuleApplicability(
            "canonical_multi_source_authentication",
            frozenset({BANK_APP, AZURE_INSIGHTS, NGINX, OPENTELEMETRY}),
        ),
        "port_scan_threshold": RuleApplicability(
            "canonical_legacy_custom_telemetry", frozenset({BANK_APP})
        ),
        "password_spraying_threshold": RuleApplicability(
            "canonical_multi_source_authentication", frozenset({BANK_APP, AZURE_INSIGHTS})
        ),
        "http_error_threshold": RuleApplicability(
            "canonical_multi_source_application_web",
            frozenset({HONEYPOT, NGINX, AZURE_INSIGHTS, OPENTELEMETRY}),
        ),
        "application_exception_threshold": RuleApplicability(
            "canonical_multi_source_application", frozenset({AZURE_INSIGHTS, OPENTELEMETRY})
        ),
        "app_insights_unauthorized_access_threshold": RuleApplicability(
            "source_specific", frozenset({AZURE_INSIGHTS})
        ),
        "high_request_rate_threshold": RuleApplicability(
            "partially_source_aware_becoming_explicit", frozenset({NGINX, OPENTELEMETRY})
        ),
        "successful_login_after_spray": RuleApplicability(
            "canonical_multi_source_authentication_sequence", frozenset({BANK_APP, AZURE_INSIGHTS})
        ),
        "honeypot_env_probe_threshold": RuleApplicability("source_specific", frozenset({HONEYPOT})),
        "honeypot_admin_probe_threshold": RuleApplicability("source_specific", frozenset({HONEYPOT})),
        "honeypot_scanner_detected": RuleApplicability("source_specific", frozenset({HONEYPOT})),
        "honeypot_credential_stuffing_threshold": RuleApplicability(
            "source_specific", frozenset({HONEYPOT})
        ),
        "pfsense_firewall_repeated_deny": RuleApplicability("source_specific", frozenset({PFSENSE})),
        "pfsense_firewall_port_scan": RuleApplicability("source_specific", frozenset({PFSENSE})),
        "pfsense_firewall_noisy_source": RuleApplicability("source_specific", frozenset({PFSENSE})),
        "pfsense_firewall_suspicious_allow": RuleApplicability("source_specific", frozenset({PFSENSE})),
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
    """Serialize the authoritative registry for read-only API presentation."""
    applicability = RULE_APPLICABILITY.get(rule_id)
    if applicability is None:
        raise ValueError("Unknown detection rule applicability")
    return {
        "source_applicability_category": applicability.classification,
        "applicable_sources": [
            {"source": identity.source, "source_type": identity.source_type}
            for identity in sorted(applicability.allowed_sources)
        ],
    }


def validate_rule_inventory(rule_ids):
    configured = set(rule_ids)
    registered = set(RULE_APPLICABILITY)
    if configured != registered:
        missing = sorted(configured - registered)
        extra = sorted(registered - configured)
        raise ValueError(f"Detection applicability inventory mismatch: missing={missing}, extra={extra}")
    if any(not item.allowed_sources for item in RULE_APPLICABILITY.values()):
        raise ValueError("Every detection rule must have at least one applicable source")
