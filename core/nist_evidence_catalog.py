"""Immutable NIST SP 800-171 Rev. 3 SIEM evidence mapping catalog.

The catalog describes assessment-support evidence only. Mapping strength is a
statement about the relevance of SIEM evidence, never an assessment outcome.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json


FRAMEWORK_ID = "nist_sp_800_171"
FRAMEWORK_VERSION = "rev3"
CATALOG_VERSION = "v1"
COLLECTOR_VERSION = "v1"

STRONG_SIEM_EVIDENCE = "strong_siem_evidence"
PARTIAL_SIEM_EVIDENCE = "partial_siem_evidence"
MAPPING_STRENGTHS = frozenset({STRONG_SIEM_EVIDENCE, PARTIAL_SIEM_EVIDENCE})


@dataclass(frozen=True)
class RequirementMapping:
    requirement_id: str
    requirement_name: str
    mapping_strength: str
    evidence_categories: tuple[str, ...]
    source_requirements: tuple[str, ...]
    limitation: str
    collector_version: str = COLLECTOR_VERSION
    assessable_by_siem: bool = True
    not_assessable_rationale: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


V1_MAPPINGS = (
    RequirementMapping(
        "03.03.01", "Event Logging", PARTIAL_SIEM_EVIDENCE,
        ("event_types", "detection_configuration"), (),
        "Shows event types received and configured detection coverage; organizational selection rationale, review frequency, and full declared-system coverage require other evidence.",
    ),
    RequirementMapping(
        "03.03.02", "Audit Record Content", STRONG_SIEM_EVIDENCE,
        ("audit_record_content",), (),
        "Shows fields present in sampled SIEM records; it does not establish that every originating system records every required field.",
    ),
    RequirementMapping(
        "03.03.03", "Audit Record Generation", PARTIAL_SIEM_EVIDENCE,
        ("generated_records",), (),
        "Shows records generated and retained in the evaluated window; organization-wide retention policy and complete source coverage require other evidence.",
    ),
    RequirementMapping(
        "03.03.04", "Response to Audit Logging Process Failures", PARTIAL_SIEM_EVIDENCE,
        ("ingestion_health", "collection_response"), (),
        "Shows collection failures or staleness and attributable responses when recorded; required personnel notification and prescribed additional actions require other evidence.",
    ),
    RequirementMapping(
        "03.03.05", "Audit Record Review, Analysis, and Reporting", STRONG_SIEM_EVIDENCE,
        ("security_findings", "incident_analysis"), (),
        "Shows detections, correlation, and investigation activity; mandated human-review frequency and designated-recipient reporting require other evidence.",
    ),
    RequirementMapping(
        "03.03.06", "Audit Record Reduction and Report Generation", STRONG_SIEM_EVIDENCE,
        ("searchable_records", "evidence_references"), (),
        "Shows bounded filtering and reproducible references; preservation and protection of every originating record require other evidence.",
    ),
    RequirementMapping(
        "03.03.07", "Time Stamps", PARTIAL_SIEM_EVIDENCE,
        ("occurrence_timestamps",), (),
        "Shows parseable occurrence timestamps where supplied; clock synchronization, accuracy, and required granularity require configuration evidence.",
    ),
    RequirementMapping(
        "03.06.01", "Incident Handling", PARTIAL_SIEM_EVIDENCE,
        ("incidents", "incident_evidence", "response_workflow"), (),
        "Shows detection, analysis, approvals, containment-related decisions, and recorded outcomes; preparation, eradication, and recovery require additional evidence.",
    ),
    RequirementMapping(
        "03.06.02", "Incident Monitoring, Reporting, and Response Assistance", STRONG_SIEM_EVIDENCE,
        ("incident_tracking", "incident_documentation"), (),
        "Shows incident tracking and internal response workflow; external-authority reporting, reporting timeliness, and staffing sufficiency require other evidence.",
    ),
    RequirementMapping(
        "03.14.06", "System Monitoring", STRONG_SIEM_EVIDENCE,
        ("monitored_events", "security_alerts"), (),
        "Shows monitoring across connected sources; complete declared-system coverage and absence of threats cannot be inferred.",
    ),
    RequirementMapping(
        "03.13.01", "Boundary Protection", PARTIAL_SIEM_EVIDENCE,
        ("firewall_events", "firewall_findings"), ("pfsense",),
        "Shows observed firewall traffic and related findings; topology, subnet separation, default-deny configuration, and complete interface coverage require configuration evidence.",
    ),
    RequirementMapping(
        "03.01.08", "Unsuccessful Logon Attempts", PARTIAL_SIEM_EVIDENCE,
        ("failed_logons", "authentication_detections"),
        ("bank_app", "azure_insights", "opentelemetry", "nginx"),
        "Shows failed logons and authentication-abuse detections; lockout, retry limits, multifactor enforcement, and administrator notification require configuration evidence.",
    ),
)

V1_MAPPING_BY_ID = {item.requirement_id: item for item in V1_MAPPINGS}


def _catalog_payload() -> dict:
    return {
        "framework_id": FRAMEWORK_ID,
        "framework_version": FRAMEWORK_VERSION,
        "catalog_version": CATALOG_VERSION,
        "collector_version": COLLECTOR_VERSION,
        "mappings": [item.as_dict() for item in V1_MAPPINGS],
    }


CATALOG_HASH = hashlib.sha256(
    json.dumps(_catalog_payload(), sort_keys=True, separators=(",", ":")).encode("utf-8")
).hexdigest()


def catalog_document() -> dict:
    return {**_catalog_payload(), "catalog_hash": CATALOG_HASH}
