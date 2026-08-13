"""Pure deterministic semantics for NIST evidence collection results."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import ipaddress
import json
from typing import Any, Iterable

from core.nist_evidence_catalog import RequirementMapping
from core.source_inventory import normalize_source_id
from core.synthetic_data_policy import (
    CONFIRMED_LEGACY_SYNTHETIC_ALERT_IDS,
    CONFIRMED_LEGACY_SYNTHETIC_SOURCE_IPS,
    DOCUMENTATION_SOURCE_IP_NETWORK_EXCLUSIONS,
    SYNTHETIC_PROVENANCE_VALUES,
)


EVIDENCE_AVAILABLE = "evidence_available"
PARTIAL_EVIDENCE = "partial_evidence"
NO_EVIDENCE_FOUND = "no_evidence_found"
NOT_ASSESSABLE_BY_SIEM = "not_assessable_by_siem"
EVIDENCE_STATUSES = frozenset(
    {EVIDENCE_AVAILABLE, PARTIAL_EVIDENCE, NO_EVIDENCE_FOUND, NOT_ASSESSABLE_BY_SIEM}
)

CONFIDENCE_HEALTHY = "healthy"
CONFIDENCE_DEGRADED = "degraded"
CONFIDENCE_UNKNOWN = "unknown"
COLLECTION_CONFIDENCES = frozenset(
    {CONFIDENCE_HEALTHY, CONFIDENCE_DEGRADED, CONFIDENCE_UNKNOWN}
)

MAX_RUN_WINDOW = timedelta(hours=168)
MIN_MEANINGFUL_WINDOW = timedelta(minutes=5)
DEFAULT_STALE_AFTER = timedelta(hours=2)


@dataclass(frozen=True)
class EvidenceReference:
    evidence_category: str
    evidence_type: str
    entity_type: str
    entity_id: str
    canonical_source: str | None
    source_type: str | None
    occurrence_timestamp: datetime | None
    ingestion_timestamp: datetime | None
    collection_timestamp: datetime
    window_start: datetime
    window_end: datetime
    source_health_state: str
    operational_classification: str
    query_hash: str
    summary: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict:
        value = asdict(self)
        for key in (
            "occurrence_timestamp", "ingestion_timestamp", "collection_timestamp",
            "window_start", "window_end",
        ):
            item = value[key]
            value[key] = item.isoformat() if item is not None else None
        return value


@dataclass(frozen=True)
class EvidenceBundle:
    category: str
    evidence_count: int
    references: tuple[EvidenceReference, ...] = ()
    omitted_count: int = 0
    collector_completed: bool = True
    reason_code: str = "collected"
    limitation: str | None = None

    @property
    def has_evidence(self) -> bool:
        return self.evidence_count > 0


@dataclass(frozen=True)
class RequirementEvaluation:
    requirement_id: str
    evidence_status: str
    collection_confidence: str
    reason_code: str
    evidence_count: int
    omitted_count: int
    limitation: str


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def validate_window(start: datetime, end: datetime) -> tuple[datetime, datetime]:
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("assessment timestamps must be timezone-aware")
    start_utc = start.astimezone(timezone.utc)
    end_utc = end.astimezone(timezone.utc)
    if start_utc >= end_utc:
        raise ValueError("assessment window start must precede end")
    if end_utc - start_utc > MAX_RUN_WINDOW:
        raise ValueError("assessment window must not exceed 168 hours")
    return start_utc, end_utc


def deterministic_query_hash(name: str, filters: dict[str, Any]) -> str:
    payload = json.dumps(
        {"collector": name, "filters": filters},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def normalize_boundary_sources(values: Iterable[str]) -> tuple[str, ...]:
    normalized = {normalize_source_id(value) for value in values}
    if not normalized:
        raise ValueError("at least one canonical source is required")
    return tuple(sorted(normalized))


def _parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else None
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None else None
    return None


def collection_confidence_for_sources(
    source_health_snapshot: dict[str, Any],
    source_ids: Iterable[str],
    *,
    observed_at: datetime,
    stale_after: timedelta = DEFAULT_STALE_AFTER,
) -> str:
    entries = {
        item.get("source"): item
        for item in source_health_snapshot.get("sources", [])
        if isinstance(item, dict)
    }
    states: list[str] = []
    for source_id in normalize_boundary_sources(source_ids):
        entry = entries.get(source_id)
        if not entry:
            states.append(CONFIDENCE_UNKNOWN)
            continue
        connector_status = entry.get("connector_status")
        if connector_status in {"degraded", "failed"}:
            states.append(CONFIDENCE_DEGRADED)
            continue
        if connector_status != "healthy":
            states.append(CONFIDENCE_UNKNOWN)
            continue
        last_poll = _parse_timestamp(entry.get("last_poll_at"))
        if last_poll is None:
            states.append(CONFIDENCE_UNKNOWN)
        elif observed_at.astimezone(timezone.utc) - last_poll.astimezone(timezone.utc) > stale_after:
            states.append(CONFIDENCE_DEGRADED)
        else:
            states.append(CONFIDENCE_HEALTHY)
    if CONFIDENCE_DEGRADED in states:
        return CONFIDENCE_DEGRADED
    if states and all(state == CONFIDENCE_HEALTHY for state in states):
        return CONFIDENCE_HEALTHY
    return CONFIDENCE_UNKNOWN


def evaluate_requirement(
    mapping: RequirementMapping,
    bundles: Iterable[EvidenceBundle],
    *,
    collection_confidence: str,
    window_start: datetime,
    window_end: datetime,
) -> RequirementEvaluation:
    if collection_confidence not in COLLECTION_CONFIDENCES:
        raise ValueError("unsupported collection confidence")
    start, end = validate_window(window_start, window_end)
    selected = {bundle.category: bundle for bundle in bundles}
    required = [selected.get(category) for category in mapping.evidence_categories]
    total = sum(bundle.evidence_count for bundle in selected.values())
    omitted = sum(bundle.omitted_count for bundle in selected.values())

    if not mapping.assessable_by_siem:
        return RequirementEvaluation(
            mapping.requirement_id, NOT_ASSESSABLE_BY_SIEM, collection_confidence,
            "outside_siem_visibility", total, omitted,
            mapping.not_assessable_rationale or mapping.limitation,
        )

    completed = all(bundle is not None and bundle.collector_completed for bundle in required)
    present = [bundle for bundle in required if bundle is not None and bundle.has_evidence]
    all_present = len(present) == len(mapping.evidence_categories)

    if all_present and completed and collection_confidence == CONFIDENCE_HEALTHY:
        status, reason = EVIDENCE_AVAILABLE, "all_categories_present_healthy"
    elif not present and completed and collection_confidence == CONFIDENCE_HEALTHY and end - start >= MIN_MEANINGFUL_WINDOW:
        status, reason = NO_EVIDENCE_FOUND, "healthy_completed_window_empty"
    elif collection_confidence == CONFIDENCE_DEGRADED:
        status, reason = PARTIAL_EVIDENCE, "collection_degraded"
    elif collection_confidence == CONFIDENCE_UNKNOWN:
        status, reason = PARTIAL_EVIDENCE, "collection_unknown"
    elif not completed:
        status, reason = PARTIAL_EVIDENCE, "collector_incomplete"
    else:
        status, reason = PARTIAL_EVIDENCE, "required_categories_incomplete"

    return RequirementEvaluation(
        mapping.requirement_id, status, collection_confidence, reason,
        total, omitted, mapping.limitation,
    )


def classify_operational_record(
    *,
    source_ip: str | None = None,
    provenance: str | None = None,
    record_id: int | None = None,
    entity_type: str | None = None,
) -> str:
    explicit = str(provenance or "").strip().lower()
    if explicit in SYNTHETIC_PROVENANCE_VALUES:
        return "synthetic"
    if entity_type == "alert" and record_id in CONFIRMED_LEGACY_SYNTHETIC_ALERT_IDS:
        return "synthetic"
    if source_ip:
        try:
            parsed = ipaddress.ip_address(str(source_ip))
        except ValueError:
            return "unknown"
        if str(parsed) in CONFIRMED_LEGACY_SYNTHETIC_SOURCE_IPS:
            return "synthetic"
        if any(parsed in ipaddress.ip_network(network) for network in DOCUMENTATION_SOURCE_IP_NETWORK_EXCLUSIONS):
            return "synthetic"
    return "real"


def classify_soar_outcome(
    *,
    execution_mode: str,
    execution_state: str,
    external_executed: bool,
    tracking_recorded: bool = False,
    simulated: bool = False,
) -> str:
    if execution_mode == "real" and execution_state == "succeeded" and external_executed:
        return "real"
    if execution_mode == "simulation" or simulated:
        return "simulated"
    if execution_mode == "tracking_only" or tracking_recorded:
        return "tracking_only"
    return execution_state
