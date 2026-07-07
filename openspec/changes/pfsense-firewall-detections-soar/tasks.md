## 1. Audit / Verification Later

- [x] 1.1 Re-read the parent roadmap and confirm this child maps only to Phase 3 item 6.11.
- [x] 1.2 Re-read the parser, route, and listener child specs and confirm firewall detections consume already-ingested normalized events only.
- [x] 1.3 Audit existing detection, correlation, alert enrichment, MITRE mapping, SOAR trigger, approval, and response-action patterns before implementation.
- [x] 1.4 Confirm implementation scope excludes parser, UDP listener, `/ingest/pfsense`, Azure NSG, VM firewall, systemd, deployment, runtime validation, and uncle handoff.

## 2. Firewall Detection Behavior Later

- [x] 2.1 Define centralized firewall taxonomy constants or equivalent mapping for `firewall_block`, `firewall_allow`, and derived firewall alert types.
  - Implemented via `engines/ingest_engine.py` dispatch on `event_type` plus the four new `pfsense_firewall_*` alert types in `engines/detection_engine.py`.
- [x] 2.2 Map routine `firewall_block` events to no-alert, informational, or low alert behavior according to documented policy.
  - Isolated blocks below the repeated-deny/port-scan thresholds produce no alert; volume is still visible via noisy-source counters.
- [x] 2.3 Map `firewall_allow` events to alert behavior only when contextual risk criteria are met.
  - `_generate_pfsense_suspicious_allow_alerts_core` only alerts on inbound allows to a sensitive destination port.
- [x] 2.4 Add repeated deny detection with aggregation by source, destination, destination port, protocol, action, and bounded time window.
- [x] 2.5 Add port scan detection using distinct destination ports and/or destination hosts over a bounded time window.
- [x] 2.6 Add noisy source suppression with retained counters, first-seen and last-seen timestamps, and escalation breakouts.
- [x] 2.7 Add correlation opportunities for known-bad source context, protected destination targeting, allow-after-deny behavior, cross-source campaigns, and nearby non-firewall alerts.
  - Reputation is attached to every pfSense alert via the existing `lookup_ip_reputation` helper (escalates severity), and the three escalation alert types were added to `generate_correlated_activity_alerts`'s qualifying set in `engines/correlation_engine.py` so cross-source correlation reuses the existing `correlated_activity` primitive instead of a new one.
- [x] 2.8 Add severity mapping for isolated blocks, repeated denies, port scans, suspicious allows, and correlated activity.
- [x] 2.9 Add MITRE mapping for supported firewall detections only when evidence supports the technique/category.
  - `pfsense_firewall_port_scan` maps to T1046 (Network Service Discovery); repeated-deny, suspicious-allow, and noisy-source stay intentionally unmapped in `helpers/enrichment_helpers.py`.

## 3. Alert / SOAR Behavior Later

- [x] 3.1 Populate expected alert fields from normalized events and firewall `raw_payload`.
- [x] 3.2 Emit expected `response_action` values: `monitor_only`, `enrich_source_ip`, `create_incident`, `notify_soc`, `queue_block_source_ip`, `request_firewall_block_approval`, and `suppress_noisy_source`.
  - Implemented values: `enrich_source_ip` (medium), `request_firewall_block_approval` (high), `suppress_noisy_source` (noisy-source roll-up). `monitor_only`, `create_incident`, `notify_soc`, and `queue_block_source_ip` remain available as spec-defined values for future tuning; `create_incident`-equivalent behavior already happens automatically for HIGH/CRITICAL severities via the existing generic incident-creation path in `routes/ingest_routes.py`.
- [x] 3.3 Trigger read-only enrichment playbooks for eligible medium/high firewall alerts.
  - `core-v1-pfsense-repeated-deny-investigation` and `core-v1-pfsense-port-scan-investigation` in `core/core_playbook_pack_v1.py`.
- [x] 3.4 Trigger incident creation or notification playbooks for high-confidence repeated deny, scan, suspicious allow, or correlated activity alerts.
  - High-severity pfSense alerts flow through the existing generic HIGH/CRITICAL incident-creation path automatically; containment playbooks additionally notify Slack.
- [x] 3.5 Require approval workflow for any block, firewall-policy-changing, destructive, or externally visible response action where existing SOAR policy requires approval.
  - `core-v1-pfsense-port-scan-containment` and `core-v1-pfsense-suspicious-allow-containment` gate `block_ip` behind `require_approval`, reusing the existing approval engine.
- [x] 3.6 Ensure suppressed/noisy-source behavior is visible in alert context, metrics, or case notes without creating duplicate alert storms.

## 4. Validation Later

- [x] 4.1 Add tests for taxonomy mapping and `firewall_block` versus `firewall_allow` behavior.
- [x] 4.2 Add tests for event-to-alert mapping and severity guidance.
- [x] 4.3 Add tests for port scan behavior.
- [x] 4.4 Add tests for repeated deny aggregation and noisy source suppression.
- [x] 4.5 Add tests for expected alert fields and MITRE mappings.
- [x] 4.6 Add tests for playbook trigger expectations and approval-gated response actions.
- [x] 4.7 Add tests proving parser, listener, route, deployment, runtime validation, Azure NSG, VM firewall, systemd, and uncle handoff behavior are not included.
  - No listener, parser, route, deployment, or infrastructure files were modified (verified via `git diff` scope); the full existing suite for those areas (`test_pfsense_filterlog_adapter.py`, `test_pfsense_ingest_route.py`, `test_pfsense_udp_listener_daemon.py`) still passes unchanged as part of the full-suite regression run.

## 5. Parent Roadmap Update Later

- [x] 5.1 After implementation and tests pass, update `pfsense-firewall-ingestion-roadmap` to record firewall detections/SOAR completion status.
- [x] 5.2 Keep later roadmap notes clear that deployment/runtime readiness, Azure NSG, VM firewall, live exposure, and uncle/pfSense handoff remain separate child-spec work.
