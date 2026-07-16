from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Literal


Severity = Literal["low", "medium", "high", "critical"]
RuleType = Literal["base", "correlation"]
ImplementationState = Literal["implemented", "reserved"]

VALID_SEVERITIES: tuple[Severity, ...] = ("low", "medium", "high", "critical")


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
class SourceApplicability:
    classification: str
    allowed_sources: tuple[SourceIdentity, ...]


@dataclass(frozen=True)
class MitreMapping:
    technique_id: str
    technique_name: str
    tactic: str


@dataclass(frozen=True)
class ParameterDefinition:
    name: str
    default_value: int


@dataclass(frozen=True)
class DetectionRuleCatalogRecord:
    rule_id: str
    display_name: str
    description: str
    family: str
    rule_type: RuleType
    default_severity: Severity
    maximum_severity: Severity
    escalation_conditions: str
    source_applicability: SourceApplicability
    mitre: MitreMapping | None
    supported_evidence: tuple[str, ...]
    investigation_guidance: str
    why: str
    parameter_definitions: tuple[ParameterDefinition, ...] = ()
    implementation_state: ImplementationState = "implemented"
    matrix_source: tuple[str, str] | None = None


FAILED_LOGIN_THRESHOLD = 3
FAILED_LOGIN_WINDOW_MINUTES = 15

PORT_SCAN_THRESHOLD = 2
PORT_SCAN_WINDOW_MINUTES = 15

PASSWORD_SPRAY_THRESHOLD = 5
PASSWORD_SPRAY_WINDOW_MINUTES = 15

HTTP_ERROR_THRESHOLD = 5
HTTP_ERROR_WINDOW_MINUTES = 15
APPLICATION_EXCEPTION_THRESHOLD = 3
APPLICATION_EXCEPTION_WINDOW_MINUTES = 10
APP_INSIGHTS_UNAUTHORIZED_ACCESS_THRESHOLD = 5
APP_INSIGHTS_UNAUTHORIZED_ACCESS_WINDOW_MINUTES = 10

HIGH_REQUEST_RATE_THRESHOLD = 20
HIGH_REQUEST_RATE_WINDOW_MINUTES = 5
CORRELATION_WINDOW_MINUTES = 10

SUCCESS_AFTER_SPRAY_SUCCESS_WINDOW_MINUTES = 15
SUCCESS_AFTER_SPRAY_FAILED_LOOKBACK_MINUTES = 30
SUCCESS_AFTER_SPRAY_CORRELATION_WINDOW_MINUTES = 15
SUCCESS_AFTER_SPRAY_THRESHOLD = 5

HONEYPOT_ENV_PROBE_THRESHOLD = 3
HONEYPOT_ENV_PROBE_WINDOW_MINUTES = 10

HONEYPOT_ADMIN_PROBE_THRESHOLD = 3
HONEYPOT_ADMIN_PROBE_WINDOW_MINUTES = 10

HONEYPOT_SCANNER_DETECTED_THRESHOLD = 1
HONEYPOT_SCANNER_DETECTED_WINDOW_MINUTES = 10

HONEYPOT_CREDENTIAL_STUFFING_THRESHOLD = 5
HONEYPOT_CREDENTIAL_STUFFING_WINDOW_MINUTES = 15

PFSENSE_REPEATED_DENY_THRESHOLD = 5
PFSENSE_REPEATED_DENY_WINDOW_MINUTES = 15

PFSENSE_PORT_SCAN_THRESHOLD = 2
PFSENSE_PORT_SCAN_WINDOW_MINUTES = 15
PFSENSE_PORT_SCAN_HOST_THRESHOLD = 5

PFSENSE_NOISY_SOURCE_THRESHOLD = 20
PFSENSE_NOISY_SOURCE_WINDOW_MINUTES = 15

PFSENSE_SUSPICIOUS_ALLOW_THRESHOLD = 1
PFSENSE_SUSPICIOUS_ALLOW_WINDOW_MINUTES = 15
PFSENSE_SUSPICIOUS_ALLOW_HIGH_CONFIDENCE_REPEAT_THRESHOLD = 3
PFSENSE_SUSPICIOUS_ALLOW_DISTINCT_PORT_ESCALATION_THRESHOLD = 2
PFSENSE_ALLOW_AFTER_DENY_MIN_DENY_THRESHOLD = 3
PFSENSE_ALLOW_AFTER_DENY_WINDOW_MINUTES = 30


def _params(*definitions: ParameterDefinition) -> tuple[ParameterDefinition, ...]:
    return definitions


_CATALOG_RECORDS: tuple[DetectionRuleCatalogRecord, ...] = (
    DetectionRuleCatalogRecord(
        rule_id="failed_login_threshold",
        display_name="Failed Login Threshold",
        description="Triggers when multiple failed login attempts occur within a time window.",
        family="authentication",
        rule_type="base",
        default_severity="high",
        maximum_severity="high",
        escalation_conditions="Fixed High detector; repeated failed logins remain an investigation signal until correlated with stronger evidence.",
        source_applicability=SourceApplicability(
            "canonical_multi_source_authentication",
            (BANK_APP, AZURE_INSIGHTS, NGINX, OPENTELEMETRY),
        ),
        mitre=MitreMapping("T1110", "Brute Force", "Credential Access"),
        supported_evidence=("failed_login", "source_ip", "username"),
        investigation_guidance="Review repeated authentication failures, compare affected usernames, and look for corroborating success or broader source activity.",
        why="Repeated failed authentication attempts are malicious, but they do not prove account compromise.",
        parameter_definitions=_params(
            ParameterDefinition("threshold", FAILED_LOGIN_THRESHOLD),
            ParameterDefinition("window_minutes", FAILED_LOGIN_WINDOW_MINUTES),
        ),
    ),
    DetectionRuleCatalogRecord(
        rule_id="port_scan_threshold",
        display_name="Port Scan Threshold",
        description="Triggers when repeated port scan events occur from the same source within a time window.",
        family="network_reconnaissance",
        rule_type="base",
        default_severity="medium",
        maximum_severity="high",
        escalation_conditions="Escalates through corroborating reputation or playbook context, but does not become Critical on scan activity alone.",
        source_applicability=SourceApplicability(
            "canonical_legacy_custom_telemetry",
            (BANK_APP,),
        ),
        mitre=MitreMapping("T1046", "Network Service Discovery", "Discovery"),
        supported_evidence=("port_scan", "source_ip", "destination_port"),
        investigation_guidance="Review the scanned ports and surrounding source activity before treating the event as more than reconnaissance.",
        why="Internet reconnaissance alone does not prove compromise.",
        parameter_definitions=_params(
            ParameterDefinition("threshold", PORT_SCAN_THRESHOLD),
            ParameterDefinition("window_minutes", PORT_SCAN_WINDOW_MINUTES),
        ),
    ),
    DetectionRuleCatalogRecord(
        rule_id="password_spraying_threshold",
        display_name="Password Spraying Threshold",
        description="Triggers when failed logins target multiple distinct usernames from the same source within a time window.",
        family="authentication",
        rule_type="base",
        default_severity="high",
        maximum_severity="high",
        escalation_conditions="Threshold-based High detector; successful authentication evidence is handled by successful_login_after_spray instead of this rule.",
        source_applicability=SourceApplicability(
            "canonical_multi_source_authentication",
            (BANK_APP, AZURE_INSIGHTS),
        ),
        mitre=MitreMapping("T1110.003", "Password Spraying", "Credential Access"),
        supported_evidence=("failed_login", "source_ip", "distinct_usernames"),
        investigation_guidance="Review targeted usernames and nearby successful authentication events from the same source before escalating.",
        why="Credential attack activity without a successful login is serious, but it is not a likely-compromise signal by itself.",
        parameter_definitions=_params(
            ParameterDefinition("threshold", PASSWORD_SPRAY_THRESHOLD),
            ParameterDefinition("window_minutes", PASSWORD_SPRAY_WINDOW_MINUTES),
        ),
    ),
    DetectionRuleCatalogRecord(
        rule_id="http_error_threshold",
        display_name="HTTP Error Threshold",
        description="Triggers when repeated HTTP error events occur from the same source within a time window.",
        family="application_pressure",
        rule_type="base",
        default_severity="medium",
        maximum_severity="high",
        escalation_conditions="Can contribute to higher-confidence correlation rules when paired with other telemetry from the same source IP.",
        source_applicability=SourceApplicability(
            "canonical_multi_source_application_web",
            (HONEYPOT, NGINX, AZURE_INSIGHTS, OPENTELEMETRY),
        ),
        mitre=None,
        supported_evidence=("http_error", "source_ip", "status_code"),
        investigation_guidance="Use error spikes as application pressure evidence and correlate them with authentication or cloud signals before escalating.",
        why="Repeated application errors can indicate attack pressure, but errors alone do not prove a compromise path succeeded.",
        parameter_definitions=_params(
            ParameterDefinition("threshold", HTTP_ERROR_THRESHOLD),
            ParameterDefinition("window_minutes", HTTP_ERROR_WINDOW_MINUTES),
        ),
    ),
    DetectionRuleCatalogRecord(
        rule_id="application_exception_threshold",
        display_name="Application Exception Threshold",
        description="Triggers when repeated application exception events occur from the same source within a time window.",
        family="application_pressure",
        rule_type="base",
        default_severity="medium",
        maximum_severity="high",
        escalation_conditions="Can contribute to higher-confidence correlation rules, but standalone exceptions remain investigation-only.",
        source_applicability=SourceApplicability(
            "canonical_multi_source_application",
            (AZURE_INSIGHTS, OPENTELEMETRY),
        ),
        mitre=None,
        supported_evidence=("application_exception", "source_ip", "exception_type"),
        investigation_guidance="Inspect exception patterns and correlate them with surrounding web or authentication activity before escalating.",
        why="Application exceptions are useful attack evidence, but they do not by themselves prove successful compromise.",
        parameter_definitions=_params(
            ParameterDefinition("threshold", APPLICATION_EXCEPTION_THRESHOLD),
            ParameterDefinition("window_minutes", APPLICATION_EXCEPTION_WINDOW_MINUTES),
        ),
    ),
    DetectionRuleCatalogRecord(
        rule_id="app_insights_unauthorized_access_threshold",
        display_name="App Insights Unauthorized Access Threshold",
        description="Triggers when repeated Application Insights 401/403 events occur from the same source within a time window.",
        family="cloud_authentication",
        rule_type="base",
        default_severity="high",
        maximum_severity="high",
        escalation_conditions="Threshold-based High detector for repeated 401/403 application responses; it does not bypass the platform's successful-authentication bar for Critical.",
        source_applicability=SourceApplicability("source_specific", (AZURE_INSIGHTS,)),
        mitre=None,
        supported_evidence=("unauthorized_access", "source_ip", "status_code"),
        investigation_guidance="Review repeated authorization failures in the context of application exceptions and other Azure authentication-abuse telemetry.",
        why="Application-tier authorization failures indicate probing or abuse, not confirmed access.",
        parameter_definitions=_params(
            ParameterDefinition("threshold", APP_INSIGHTS_UNAUTHORIZED_ACCESS_THRESHOLD),
            ParameterDefinition("window_minutes", APP_INSIGHTS_UNAUTHORIZED_ACCESS_WINDOW_MINUTES),
        ),
    ),
    DetectionRuleCatalogRecord(
        rule_id="high_request_rate_threshold",
        display_name="High Request Rate Threshold",
        description="Triggers when high request volume occurs from the same source within a time window.",
        family="application_pressure",
        rule_type="base",
        default_severity="medium",
        maximum_severity="high",
        escalation_conditions="Can contribute to correlation-driven High alerts when paired with matching application signals.",
        source_applicability=SourceApplicability(
            "partially_source_aware_becoming_explicit",
            (NGINX, OPENTELEMETRY),
        ),
        mitre=None,
        supported_evidence=("normal_activity", "source_ip", "request_volume"),
        investigation_guidance="Treat high request volume as pressure telemetry and correlate it with errors or authentication behavior before escalating.",
        why="High request volume can be abusive or malicious, but traffic rate alone does not establish compromise.",
        parameter_definitions=_params(
            ParameterDefinition("threshold", HIGH_REQUEST_RATE_THRESHOLD),
            ParameterDefinition("window_minutes", HIGH_REQUEST_RATE_WINDOW_MINUTES),
        ),
    ),
    DetectionRuleCatalogRecord(
        rule_id="successful_login_after_spray",
        display_name="Successful Login After Spray",
        description="Triggers when password spraying activity is followed by a successful login from the same source.",
        family="authentication_sequence",
        rule_type="base",
        default_severity="critical",
        maximum_severity="critical",
        escalation_conditions="Requires at least 5 distinct failed-login usernames before a successful login within the configured correlation windows.",
        source_applicability=SourceApplicability(
            "canonical_multi_source_authentication_sequence",
            (BANK_APP, AZURE_INSIGHTS),
        ),
        mitre=MitreMapping("T1110.003", "Password Spraying", "Credential Access"),
        supported_evidence=("failed_login", "successful_login", "source_ip", "distinct_usernames"),
        investigation_guidance="Treat as likely compromise and review affected account activity immediately while preserving approval-gated containment behavior.",
        why="Successful authentication after coordinated credential attacks is a likely-compromise indicator requiring immediate human review.",
        parameter_definitions=_params(
            ParameterDefinition("threshold", SUCCESS_AFTER_SPRAY_THRESHOLD),
            ParameterDefinition("success_window_minutes", SUCCESS_AFTER_SPRAY_SUCCESS_WINDOW_MINUTES),
            ParameterDefinition("failed_lookback_minutes", SUCCESS_AFTER_SPRAY_FAILED_LOOKBACK_MINUTES),
            ParameterDefinition("correlation_window_minutes", SUCCESS_AFTER_SPRAY_CORRELATION_WINDOW_MINUTES),
        ),
    ),
    DetectionRuleCatalogRecord(
        rule_id="honeypot_env_probe_threshold",
        display_name="Honeypot Env Probe Threshold",
        description="Triggers when one source IP probes multiple distinct sensitive file paths within a time window.",
        family="honeypot_reconnaissance",
        rule_type="base",
        default_severity="high",
        maximum_severity="high",
        escalation_conditions="Threshold-based High detector; remains investigation and containment-eligible without becoming Critical.",
        source_applicability=SourceApplicability("source_specific", (HONEYPOT,)),
        mitre=None,
        supported_evidence=("env_probe", "source_ip", "path"),
        investigation_guidance="Review sensitive path probing in the context of surrounding honeypot activity and source history.",
        why="Deliberate probing of sensitive honeypot paths is hostile, but it does not prove a production compromise occurred.",
        parameter_definitions=_params(
            ParameterDefinition("threshold", HONEYPOT_ENV_PROBE_THRESHOLD),
            ParameterDefinition("window_minutes", HONEYPOT_ENV_PROBE_WINDOW_MINUTES),
        ),
    ),
    DetectionRuleCatalogRecord(
        rule_id="honeypot_admin_probe_threshold",
        display_name="Honeypot Admin Probe Threshold",
        description="Triggers when one source IP probes multiple distinct admin paths within a time window.",
        family="honeypot_reconnaissance",
        rule_type="base",
        default_severity="medium",
        maximum_severity="medium",
        escalation_conditions="Fixed Medium detector; corroborating evidence must come from other rules.",
        source_applicability=SourceApplicability("source_specific", (HONEYPOT,)),
        mitre=None,
        supported_evidence=("admin_probe", "source_ip", "path"),
        investigation_guidance="Use admin-path probing as a review signal and correlate it with stronger honeypot evidence before escalating.",
        why="Admin-path probing is suspicious, but a single probe is not enough to justify High or Critical severity on its own.",
        parameter_definitions=_params(
            ParameterDefinition("threshold", HONEYPOT_ADMIN_PROBE_THRESHOLD),
            ParameterDefinition("window_minutes", HONEYPOT_ADMIN_PROBE_WINDOW_MINUTES),
        ),
    ),
    DetectionRuleCatalogRecord(
        rule_id="honeypot_scanner_detected",
        display_name="Honeypot Scanner Detected",
        description="Triggers when scanner activity from one source IP meets the configured threshold within a time window.",
        family="honeypot_reconnaissance",
        rule_type="base",
        default_severity="medium",
        maximum_severity="medium",
        escalation_conditions="Fixed Medium detector; supports analyst review and correlation, not containment by itself.",
        source_applicability=SourceApplicability("source_specific", (HONEYPOT,)),
        mitre=None,
        supported_evidence=("scanner_detected", "source_ip", "scanner_signature"),
        investigation_guidance="Treat scanner detections as visibility signals and correlate them with other hostile behavior before escalating.",
        why="Commodity scanning is meaningful telemetry, but scanner activity alone does not imply compromise.",
        parameter_definitions=_params(
            ParameterDefinition("threshold", HONEYPOT_SCANNER_DETECTED_THRESHOLD),
            ParameterDefinition("window_minutes", HONEYPOT_SCANNER_DETECTED_WINDOW_MINUTES),
        ),
    ),
    DetectionRuleCatalogRecord(
        rule_id="honeypot_credential_stuffing_threshold",
        display_name="Honeypot Credential Stuffing Threshold",
        description="Triggers when one source IP attempts logins across multiple distinct usernames within a time window.",
        family="honeypot_authentication",
        rule_type="base",
        default_severity="high",
        maximum_severity="high",
        escalation_conditions="Threshold-based High detector; no standalone Critical path without successful-authentication evidence.",
        source_applicability=SourceApplicability("source_specific", (HONEYPOT,)),
        mitre=None,
        supported_evidence=("credential_stuffing", "source_ip", "distinct_usernames"),
        investigation_guidance="Treat as high-confidence malicious honeypot behavior and preserve approval-gated containment paths.",
        why="Credential-stuffing against the honeypot is high-confidence malicious behavior, but not a likely-compromise signal for production systems.",
        parameter_definitions=_params(
            ParameterDefinition("threshold", HONEYPOT_CREDENTIAL_STUFFING_THRESHOLD),
            ParameterDefinition("window_minutes", HONEYPOT_CREDENTIAL_STUFFING_WINDOW_MINUTES),
        ),
    ),
    DetectionRuleCatalogRecord(
        rule_id="pfsense_firewall_repeated_deny",
        display_name="pfSense Firewall Repeated Deny",
        description="Triggers when pfSense blocks repeated equivalent traffic from the same source within a time window.",
        family="firewall_reconnaissance",
        rule_type="base",
        default_severity="low",
        maximum_severity="high",
        escalation_conditions="Starts Low for inbound commodity denies, rises to Medium on sustained repetition, and reaches High only for outbound/internal-host behavior or stronger corroboration.",
        source_applicability=SourceApplicability("source_specific", (PFSENSE,)),
        mitre=None,
        supported_evidence=("firewall_block", "source_ip", "destination_ip", "destination_port", "direction"),
        investigation_guidance="Distinguish routine inbound blocking from outbound or internal-host behavior before escalating response.",
        why="Blocked activity indicates malicious intent or scanning, but blocked traffic alone does not prove successful access.",
        parameter_definitions=_params(
            ParameterDefinition("threshold", PFSENSE_REPEATED_DENY_THRESHOLD),
            ParameterDefinition("window_minutes", PFSENSE_REPEATED_DENY_WINDOW_MINUTES),
        ),
    ),
    DetectionRuleCatalogRecord(
        rule_id="pfsense_firewall_port_scan",
        display_name="pfSense Firewall Port Scan",
        description="Triggers when pfSense firewall events show one source contacting multiple distinct destination ports, or sweeping multiple distinct destination hosts.",
        family="firewall_reconnaissance",
        rule_type="base",
        default_severity="medium",
        maximum_severity="high",
        escalation_conditions="Escalates from Medium to High only on materially stronger breadth or reputation-backed stronger breadth; routine commodity scanning stays below High.",
        source_applicability=SourceApplicability("source_specific", (PFSENSE,)),
        mitre=MitreMapping("T1046", "Network Service Discovery", "Discovery"),
        supported_evidence=("firewall_block", "source_ip", "destination_ip", "destination_port", "scan_description"),
        investigation_guidance="Review the breadth, ports, and target range to separate commodity scanning from more meaningful progression.",
        why="Port-scanning is strong reconnaissance evidence, but reconnaissance alone is not a likely-compromise signal.",
        parameter_definitions=_params(
            ParameterDefinition("threshold", PFSENSE_PORT_SCAN_THRESHOLD),
            ParameterDefinition("window_minutes", PFSENSE_PORT_SCAN_WINDOW_MINUTES),
            ParameterDefinition("host_threshold", PFSENSE_PORT_SCAN_HOST_THRESHOLD),
        ),
    ),
    DetectionRuleCatalogRecord(
        rule_id="pfsense_firewall_noisy_source",
        display_name="pfSense Firewall Noisy Source",
        description="Suppresses duplicate low-value pfSense firewall alerts while retaining source activity counters.",
        family="firewall_operational_noise",
        rule_type="base",
        default_severity="low",
        maximum_severity="low",
        escalation_conditions="Suppression-focused detector; does not escalate beyond Low in the current design.",
        source_applicability=SourceApplicability("source_specific", (PFSENSE,)),
        mitre=None,
        supported_evidence=("firewall_block", "firewall_allow", "source_ip", "event_count"),
        investigation_guidance="Use this rule operationally to preserve visibility on noisy sources without overstating severity.",
        why="This rule exists to track noisy sources operationally, not to represent a compromise indicator.",
        parameter_definitions=_params(
            ParameterDefinition("threshold", PFSENSE_NOISY_SOURCE_THRESHOLD),
            ParameterDefinition("window_minutes", PFSENSE_NOISY_SOURCE_WINDOW_MINUTES),
        ),
    ),
    DetectionRuleCatalogRecord(
        rule_id="pfsense_firewall_suspicious_allow",
        display_name="pfSense Firewall Suspicious Allow",
        description="Triggers when pfSense allows inbound traffic to a sensitive destination port; escalates to high severity only on repeated, multi-port, or progression-backed evidence.",
        family="firewall_progression",
        rule_type="base",
        default_severity="medium",
        maximum_severity="high",
        escalation_conditions="Escalates to High only on repeated qualifying allows, multi-port corroboration, or progression-backed evidence; reputation alone is insufficient.",
        source_applicability=SourceApplicability("source_specific", (PFSENSE,)),
        mitre=None,
        supported_evidence=("firewall_allow", "source_ip", "destination_ip", "destination_port", "protocol"),
        investigation_guidance="Review allowed sensitive services in the context of repeated activity or progression before escalating containment.",
        why="Allowed traffic to sensitive ports is important, but it becomes High only when corroborating context suggests meaningful risk.",
        parameter_definitions=_params(
            ParameterDefinition("threshold", PFSENSE_SUSPICIOUS_ALLOW_THRESHOLD),
            ParameterDefinition("window_minutes", PFSENSE_SUSPICIOUS_ALLOW_WINDOW_MINUTES),
            ParameterDefinition(
                "high_confidence_repeat_threshold",
                PFSENSE_SUSPICIOUS_ALLOW_HIGH_CONFIDENCE_REPEAT_THRESHOLD,
            ),
            ParameterDefinition(
                "distinct_port_escalation_threshold",
                PFSENSE_SUSPICIOUS_ALLOW_DISTINCT_PORT_ESCALATION_THRESHOLD,
            ),
        ),
    ),
    DetectionRuleCatalogRecord(
        rule_id="pfsense_firewall_allow_after_deny",
        display_name="pfSense Firewall Allow After Deny",
        description="Triggers when the same external source first produces repeated inbound firewall denies and later reaches an inbound allow to the same protected service within the bounded progression window.",
        family="firewall_progression",
        rule_type="base",
        default_severity="medium",
        maximum_severity="high",
        escalation_conditions="Requires same-source inbound deny-to-allow progression within 30 minutes; High requires exact-target or sensitive-service progression.",
        source_applicability=SourceApplicability("source_specific", (PFSENSE,)),
        mitre=None,
        supported_evidence=("firewall_block", "firewall_allow", "source_ip", "destination_ip", "destination_port"),
        investigation_guidance="Treat bounded deny-to-allow progression as a source-specific escalation path and review target consistency before containment.",
        why="Later inbound access after repeated denies is stronger than commodity recon, but it still requires analyst review and approval-gated containment.",
        parameter_definitions=_params(
            ParameterDefinition("minimum_deny_threshold", PFSENSE_ALLOW_AFTER_DENY_MIN_DENY_THRESHOLD),
            ParameterDefinition("window_minutes", PFSENSE_ALLOW_AFTER_DENY_WINDOW_MINUTES),
            ParameterDefinition("high_confidence_deny_threshold", PFSENSE_REPEATED_DENY_THRESHOLD),
        ),
    ),
    DetectionRuleCatalogRecord(
        rule_id="correlated_activity",
        display_name="Correlated Activity",
        description="Detects multi-source suspicious activity from one IP when multiple qualifying open alerts align within the shared correlation window.",
        family="correlation",
        rule_type="correlation",
        default_severity="high",
        maximum_severity="high",
        escalation_conditions="Multi-source correlation stays High; Critical is reserved for likely-compromise evidence.",
        source_applicability=SourceApplicability(
            "correlation_multi_source",
            (BANK_APP, NGINX, AZURE_INSIGHTS, PFSENSE, OPENTELEMETRY),
        ),
        mitre=None,
        supported_evidence=("open_alerts", "contributing_alert_types", "contributing_sources"),
        investigation_guidance="Review the contributing alert types and sources together rather than treating each precursor in isolation.",
        why="Cross-source suspicious activity is high-confidence malicious behavior, but not proof that compromise succeeded.",
        matrix_source=("legacy", "legacy"),
    ),
    DetectionRuleCatalogRecord(
        rule_id="web_to_app_attack_pattern",
        display_name="Web-to-App Attack Pattern",
        description="Detects correlated nginx web pressure and bank application authentication pressure from the same IP within the targeted rule window.",
        family="correlation",
        rule_type="correlation",
        default_severity="high",
        maximum_severity="high",
        escalation_conditions="Requires both nginx web pressure and bank_app authentication pressure from the same IP within 10 minutes.",
        source_applicability=SourceApplicability(
            "correlation_targeted",
            (BANK_APP, NGINX),
        ),
        mitre=None,
        supported_evidence=("open_alerts", "matched_groups", "contributing_alert_types"),
        investigation_guidance="Review the matched web and authentication groups together to determine whether the attack chain is progressing.",
        why="Correlated attack-chain evidence without proof of successful compromise belongs at High, not Critical.",
        matrix_source=("nginx", "web_log"),
    ),
    DetectionRuleCatalogRecord(
        rule_id="spray_then_success_pattern",
        display_name="Spray-Then-Success Pattern",
        description="Detects the combination of password spraying and successful-login-after-spray alerts for the same IP within the targeted rule window.",
        family="correlation",
        rule_type="correlation",
        default_severity="high",
        maximum_severity="high",
        escalation_conditions="Requires both password_spraying_threshold and successful_login_after_spray to already exist for the same IP.",
        source_applicability=SourceApplicability(
            "correlation_targeted",
            (BANK_APP, AZURE_INSIGHTS),
        ),
        mitre=MitreMapping("T1110.003", "Password Spraying", "Credential Access"),
        supported_evidence=("open_alerts", "matched_groups", "contributing_alert_types"),
        investigation_guidance="Use this as corroborating context for an existing likely-compromise signal rather than a replacement for the critical detector.",
        why="This rule corroborates an existing likely-compromise signal, but the canonical Critical decision belongs to successful_login_after_spray.",
        matrix_source=("bank_app", "custom"),
    ),
    DetectionRuleCatalogRecord(
        rule_id="cloud_app_error_pattern",
        display_name="Cloud/App Error Pattern",
        description="Detects correlated Azure and nginx application error activity from the same IP within the targeted rule window.",
        family="correlation",
        rule_type="correlation",
        default_severity="high",
        maximum_severity="high",
        escalation_conditions="Requires matching cloud and nginx error activity from the same IP within the rule window.",
        source_applicability=SourceApplicability(
            "correlation_targeted",
            (AZURE_INSIGHTS, NGINX),
        ),
        mitre=None,
        supported_evidence=("open_alerts", "matched_groups", "contributing_alert_types"),
        investigation_guidance="Review correlated cloud and web error telemetry as one activity chain before deciding whether it indicates exploitation pressure.",
        why="Cross-platform error correlations can be malicious, but they still require analyst validation before being treated as compromise evidence.",
        matrix_source=("azure_insights", "cloud_api"),
    ),
    DetectionRuleCatalogRecord(
        rule_id="azure_auth_abuse_exception_correlation",
        display_name="Azure Auth Abuse Exception Correlation",
        description="Detects correlated Azure authentication-abuse and application exception activity from the same IP within the targeted rule window.",
        family="correlation",
        rule_type="correlation",
        default_severity="high",
        maximum_severity="high",
        escalation_conditions="Requires both Azure authentication-abuse pressure and an Application Insights exception spike from the same IP within the rule window.",
        source_applicability=SourceApplicability(
            "correlation_targeted",
            (AZURE_INSIGHTS,),
        ),
        mitre=None,
        supported_evidence=("open_alerts", "matched_groups", "contributing_alert_types"),
        investigation_guidance="Review authentication-abuse and exception signals together to determine whether the source is progressing beyond commodity noise.",
        why="Correlated auth abuse and application instability is a stronger signal, but still not proof of a successful compromise.",
        matrix_source=("azure_insights", "cloud_api"),
    ),
    DetectionRuleCatalogRecord(
        rule_id="suspicious_ip_reputation",
        display_name="Suspicious IP Reputation",
        description="Legacy reputation-only alert metadata preserved for MITRE enrichment compatibility.",
        family="legacy_reputation",
        rule_type="base",
        default_severity="medium",
        maximum_severity="medium",
        escalation_conditions="Legacy metadata only; not part of the current runtime Detection Rules or Severity Matrix inventory.",
        source_applicability=SourceApplicability(
            "legacy_compatibility",
            tuple(sorted(CANONICAL_SOURCE_IDENTITIES)),
        ),
        mitre=MitreMapping("T1595", "Active Scanning", "Reconnaissance"),
        supported_evidence=("reputation_score", "source_ip"),
        investigation_guidance="Preserve historical MITRE behavior for legacy alerts without reintroducing a separate metadata registry.",
        why="Legacy reputation-only alerts remain cataloged for enrichment compatibility, not for active detector inventory.",
        implementation_state="reserved",
    ),
)

_CATALOG_BY_RULE_ID = {record.rule_id: record for record in _CATALOG_RECORDS}
DETECTION_RULE_CATALOG = MappingProxyType(_CATALOG_BY_RULE_ID)


def list_detection_rule_catalog(*, include_reserved: bool = False) -> list[DetectionRuleCatalogRecord]:
    return [
        record
        for record in _CATALOG_RECORDS
        if include_reserved or record.implementation_state == "implemented"
    ]


def get_detection_rule_catalog_record(rule_id: str) -> DetectionRuleCatalogRecord:
    record = DETECTION_RULE_CATALOG.get(rule_id)
    if record is None:
        raise ValueError("Unknown detection rule catalog record")
    return record


def get_base_rule_catalog_records(*, include_reserved: bool = False) -> list[DetectionRuleCatalogRecord]:
    return [
        record
        for record in list_detection_rule_catalog(include_reserved=include_reserved)
        if record.rule_type == "base"
    ]


def get_correlation_rule_catalog_records(*, include_reserved: bool = False) -> list[DetectionRuleCatalogRecord]:
    return [
        record
        for record in list_detection_rule_catalog(include_reserved=include_reserved)
        if record.rule_type == "correlation"
    ]


def get_rule_parameter_defaults(rule_id: str) -> dict[str, int]:
    return {
        definition.name: definition.default_value
        for definition in get_detection_rule_catalog_record(rule_id).parameter_definitions
    }


def get_rule_parameter_names(rule_id: str) -> set[str]:
    return set(get_rule_parameter_defaults(rule_id))


def get_rule_mitre_mapping(rule_id: str) -> dict[str, str] | None:
    record = DETECTION_RULE_CATALOG.get(rule_id)
    if record is None:
        return None
    mapping = record.mitre
    if mapping is None:
        return None
    return {
        "mitre_technique_id": mapping.technique_id,
        "mitre_technique_name": mapping.technique_name,
        "mitre_tactic": mapping.tactic,
    }


def list_catalog_mitre_mappings(*, include_reserved: bool = True) -> list[dict[str, str]]:
    mappings: list[dict[str, str]] = []
    seen: set[str] = set()
    for record in list_detection_rule_catalog(include_reserved=include_reserved):
        mapping = get_rule_mitre_mapping(record.rule_id)
        if mapping is None:
            continue
        technique_id = mapping["mitre_technique_id"]
        if technique_id in seen:
            continue
        seen.add(technique_id)
        mappings.append(mapping)
    return mappings


def is_rule_intentionally_unmapped_mitre(rule_id: str) -> bool:
    record = DETECTION_RULE_CATALOG.get(rule_id)
    return record is not None and record.mitre is None


def validate_detection_rule_catalog(
    *,
    implemented_base_rule_ids: set[str] | None = None,
    implemented_correlation_rule_ids: set[str] | None = None,
) -> None:
    if len(_CATALOG_BY_RULE_ID) != len(_CATALOG_RECORDS):
        raise ValueError("Duplicate rule IDs exist in the detection rule catalog")

    for record in _CATALOG_RECORDS:
        if not record.rule_id or not record.display_name or not record.description:
            raise ValueError(f"Missing required metadata for rule_id={record.rule_id!r}")
        if record.default_severity not in VALID_SEVERITIES or record.maximum_severity not in VALID_SEVERITIES:
            raise ValueError(f"Invalid severity for rule_id={record.rule_id}")
        if VALID_SEVERITIES.index(record.default_severity) > VALID_SEVERITIES.index(record.maximum_severity):
            raise ValueError(f"default_severity exceeds maximum_severity for rule_id={record.rule_id}")
        if not record.source_applicability.classification:
            raise ValueError(f"Missing source applicability classification for rule_id={record.rule_id}")
        if not record.source_applicability.allowed_sources:
            raise ValueError(f"Empty source applicability for rule_id={record.rule_id}")
        for identity in record.source_applicability.allowed_sources:
            if identity not in CANONICAL_SOURCE_IDENTITIES:
                raise ValueError(f"Unsupported source applicability identity for rule_id={record.rule_id}")
        if record.mitre is not None:
            if not record.mitre.technique_id or not record.mitre.technique_name or not record.mitre.tactic:
                raise ValueError(f"Malformed MITRE metadata for rule_id={record.rule_id}")

    if implemented_base_rule_ids is not None:
        catalog_base_ids = {record.rule_id for record in get_base_rule_catalog_records()}
        missing = sorted(set(implemented_base_rule_ids) - catalog_base_ids)
        if missing:
            raise ValueError(f"Implemented base detection rule(s) missing catalog metadata: {missing}")

    if implemented_correlation_rule_ids is not None:
        catalog_correlation_ids = {record.rule_id for record in get_correlation_rule_catalog_records()}
        missing = sorted(set(implemented_correlation_rule_ids) - catalog_correlation_ids)
        if missing:
            raise ValueError(f"Implemented correlation rule(s) missing catalog metadata: {missing}")

    implemented_ids = set(implemented_base_rule_ids or set()) | set(implemented_correlation_rule_ids or set())
    orphaned = sorted(
        record.rule_id
        for record in list_detection_rule_catalog(include_reserved=True)
        if record.implementation_state == "implemented" and record.rule_id not in implemented_ids
    )
    if implemented_ids and orphaned:
        raise ValueError(f"Catalog rule(s) marked implemented without runtime implementation: {orphaned}")


def serialize_source_applicability(record: DetectionRuleCatalogRecord) -> dict[str, Any]:
    return {
        "source_applicability_category": record.source_applicability.classification,
        "applicable_sources": [
            {"source": identity.source, "source_type": identity.source_type}
            for identity in sorted(record.source_applicability.allowed_sources)
        ],
    }
