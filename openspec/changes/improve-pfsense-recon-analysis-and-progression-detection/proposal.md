## Why

pfSense detections were tuned against synthetic traffic, but the first sustained real-world firewall stream exposed an analyst-experience failure rather than a simple threshold problem. Production evidence is now authoritative: 504 unique source IPs produced 510 alerts, 289 of 289 High pfSense alerts became High only because `AbuseIPDB reputation_score >= 70`, 298 separate open P2 incidents were created, and 165 approval requests expired unactioned. The activity reflects distributed commodity Internet reconnaissance against the protected `8.14.136.x` range, not proven coordination or compromise.

The platform is preserving evidence, but it is operationally misclassifying routine inbound commodity scanning as hundreds of independent High-priority cases. This change is needed now to keep pfSense telemetry visible while restoring honest severity, incident, approval, and notification behavior.

## What Changes

- Redefine pfSense severity escalation so reputation alone cannot turn a minimum-threshold commodity scan into `high`; `high` must require meaningful observed behavior against this environment.
- Narrow automatic incident creation, approval generation, and containment eligibility for pfSense alerts so routine distributed reconnaissance stays visible without creating one P2 incident and one approval per external source.
- Add an analyst-facing distributed reconnaissance aggregate, labeled `Distributed Internet Reconnaissance Activity`, that preserves underlying alerts/events while giving analysts one primary summary for many-source commodity scanning.
- Expand pfSense target evidence with bounded deterministic samples, related-event inspection paths, and backend-owned human-readable scan descriptions.
- Add one narrowly defined allow-after-deny firewall progression detection that preserves deny/allow evidence and supports investigation or approved containment without auto-blocking.
- Integrate the new behavior into existing notification policy, Severity & Response Matrix, and small focused UI surfaces without redesigning the application.

## Capabilities

### New Capabilities
- `pfsense-recon-severity-and-operational-response`: pfSense severity correction, incident creation rules, approval eligibility, containment boundaries, notification eligibility, and baseline strategy for routine versus escalating reconnaissance.
- `pfsense-distributed-recon-activity`: durable analyst-facing aggregation of many-source commodity reconnaissance against the same protected destination range/services, including lifecycle, membership, assessment text, notifications, and UI entry points.
- `pfsense-target-evidence-and-scan-descriptions`: bounded target-context expansion, related-event inspection paths, and canonical backend-generated analyst wording for pfSense scan behavior.
- `pfsense-allow-after-deny-progression`: same-source firewall deny-to-allow progression detection, severity, evidence preservation, incident behavior, and response boundaries.

### Modified Capabilities
- (none)

## Impact

- **Affected code later:** `engines/detection_engine.py`, `engines/detection_config.py`, `engines/ingest_engine.py`, `core/incident_store.py`, `core/core_playbook_pack_v1.py`, `core/notification_policy_service.py`, `engines/severity_response_matrix.py`, pfSense alert detail/read-only API routes, new recon-activity APIs, and focused React surfaces for alert details, a bounded recon activity view, and SOC Command Center summaries.
- **Affected data model later:** likely one new persistence model for distributed recon aggregates and membership; no rewrite of historical alerts, incidents, approvals, or thresholds.
- **Affected APIs later:** additive read-only aggregate/detail/list endpoints plus additive pfSense alert detail fields; existing contracts remain backward-compatible.
- **Operational constraints:** no VM work, no production mutation, no threshold edits, no historical rewrites, and no implementation in this change authoring step.
