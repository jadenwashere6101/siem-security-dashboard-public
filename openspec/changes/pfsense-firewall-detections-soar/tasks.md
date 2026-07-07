## 1. Audit / Verification Later

- [ ] 1.1 Re-read the parent roadmap and confirm this child maps only to Phase 3 item 6.11.
- [ ] 1.2 Re-read the parser, route, and listener child specs and confirm firewall detections consume already-ingested normalized events only.
- [ ] 1.3 Audit existing detection, correlation, alert enrichment, MITRE mapping, SOAR trigger, approval, and response-action patterns before implementation.
- [ ] 1.4 Confirm implementation scope excludes parser, UDP listener, `/ingest/pfsense`, Azure NSG, VM firewall, systemd, deployment, runtime validation, and uncle handoff.

## 2. Firewall Detection Behavior Later

- [ ] 2.1 Define centralized firewall taxonomy constants or equivalent mapping for `firewall_block`, `firewall_allow`, and derived firewall alert types.
- [ ] 2.2 Map routine `firewall_block` events to no-alert, informational, or low alert behavior according to documented policy.
- [ ] 2.3 Map `firewall_allow` events to alert behavior only when contextual risk criteria are met.
- [ ] 2.4 Add repeated deny detection with aggregation by source, destination, destination port, protocol, action, and bounded time window.
- [ ] 2.5 Add port scan detection using distinct destination ports and/or destination hosts over a bounded time window.
- [ ] 2.6 Add noisy source suppression with retained counters, first-seen and last-seen timestamps, and escalation breakouts.
- [ ] 2.7 Add correlation opportunities for known-bad source context, protected destination targeting, allow-after-deny behavior, cross-source campaigns, and nearby non-firewall alerts.
- [ ] 2.8 Add severity mapping for isolated blocks, repeated denies, port scans, suspicious allows, and correlated activity.
- [ ] 2.9 Add MITRE mapping for supported firewall detections only when evidence supports the technique/category.

## 3. Alert / SOAR Behavior Later

- [ ] 3.1 Populate expected alert fields from normalized events and firewall `raw_payload`.
- [ ] 3.2 Emit expected `response_action` values: `monitor_only`, `enrich_source_ip`, `create_incident`, `notify_soc`, `queue_block_source_ip`, `request_firewall_block_approval`, and `suppress_noisy_source`.
- [ ] 3.3 Trigger read-only enrichment playbooks for eligible medium/high firewall alerts.
- [ ] 3.4 Trigger incident creation or notification playbooks for high-confidence repeated deny, scan, suspicious allow, or correlated activity alerts.
- [ ] 3.5 Require approval workflow for any block, firewall-policy-changing, destructive, or externally visible response action where existing SOAR policy requires approval.
- [ ] 3.6 Ensure suppressed/noisy-source behavior is visible in alert context, metrics, or case notes without creating duplicate alert storms.

## 4. Validation Later

- [ ] 4.1 Add tests for taxonomy mapping and `firewall_block` versus `firewall_allow` behavior.
- [ ] 4.2 Add tests for event-to-alert mapping and severity guidance.
- [ ] 4.3 Add tests for port scan behavior.
- [ ] 4.4 Add tests for repeated deny aggregation and noisy source suppression.
- [ ] 4.5 Add tests for expected alert fields and MITRE mappings.
- [ ] 4.6 Add tests for playbook trigger expectations and approval-gated response actions.
- [ ] 4.7 Add tests proving parser, listener, route, deployment, runtime validation, Azure NSG, VM firewall, systemd, and uncle handoff behavior are not included.

## 5. Parent Roadmap Update Later

- [ ] 5.1 After implementation and tests pass, update `pfsense-firewall-ingestion-roadmap` to record firewall detections/SOAR completion status.
- [ ] 5.2 Keep later roadmap notes clear that deployment/runtime readiness, Azure NSG, VM firewall, live exposure, and uncle/pfSense handoff remain separate child-spec work.
