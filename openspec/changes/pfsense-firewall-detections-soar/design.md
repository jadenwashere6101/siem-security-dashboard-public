## Context

The parser/normalizer owns pfSense filterlog parsing and normalized event shape. The ingest route owns authentication, route validation, centralized ingest, and post-commit orchestration. The listener owns UDP receipt and forwarding. This change starts after those boundaries: pfSense firewall events already exist in the centralized pipeline with `source="pfsense"` and `source_type="firewall"`.

This spec defines detection, alert, correlation, MITRE, and SOAR expectations for firewall events. It must not redefine parser fields, add a UDP listener, add `/ingest/pfsense`, change Azure NSG or VM firewall rules, perform deployment work, validate runtime services, or create any uncle/pfSense handoff.

## Goals / Non-Goals

**Goals:**

- Define firewall event taxonomy for `firewall_block`, `firewall_allow`, and derived firewall detection alerts.
- Define event-to-alert mapping for isolated blocks, repeated denies, port scans, suspicious allows, and correlated firewall activity.
- Define severity guidance that separates low-value routine firewall noise from actionable security signals.
- Define correlation opportunities using source IP, destination IP, destination port, protocol, interface, direction, action, and timing windows.
- Define noisy source suppression strategy that reduces duplicate alert volume without hiding meaningful escalation.
- Define MITRE ATT&CK mapping expectations for scan/reconnaissance and potential command-and-control or exfiltration indicators where evidence supports them.
- Define playbook trigger expectations, approval workflow expectations, expected alert fields, and expected `response_action` values.
- Define validation strategy and acceptance criteria for later implementation.

**Non-Goals:**

- No parser, normalizer, UDP listener, `/ingest/pfsense`, Azure NSG, VM firewall, systemd, deployment, runtime validation, or uncle handoff work.
- No source-code implementation, test creation, commits, or pushes during this spec-creation task.
- No direct database schema change requirement unless a later implementation audit proves existing alert/SOAR fields are insufficient.

## Decisions

1. Treat taxonomy as post-ingest detection language.

   `firewall_block` and `firewall_allow` are normalized firewall event types available to detection logic. Derived alert names should be more specific, such as `firewall_port_scan`, `firewall_repeated_deny`, `firewall_suspicious_allow`, or `firewall_correlated_activity`.

2. Blocks are signal candidates, not automatic high-severity incidents.

   A single inbound `firewall_block` is commonly expected firewall behavior. It may be stored and counted without alerting, or may produce an informational/low alert only when local alert policy requires it. Severity increases when blocks show scan breadth, repeated deny behavior, protected destination targeting, known-bad context, or correlation with other telemetry.

3. Allows require context.

   A `firewall_allow` is not inherently suspicious. It becomes alert-worthy when it involves sensitive destination ports, unexpected direction/interface, public-to-internal exposure, allow-after-deny behavior, known-bad source reputation, or correlation with other suspicious events.

4. Port scan detection should prefer breadth and time-window logic.

   Port scan behavior should evaluate distinct destination ports and/or destinations for the same source within a bounded time window. Existing port-scan concepts may be reused, but firewall-specific fields must be mapped explicitly from `raw_payload.destination_port`, `protocol`, `destination_ip`, `direction`, and `action`.

5. Repeated deny detection should suppress duplicates.

   Repeated denies from the same source to the same destination/port/protocol should aggregate into one alert per suppression window with counters and first/last-seen timestamps, rather than creating one alert per packet.

6. Noisy source suppression should be observable and reversible.

   Suppression should reduce duplicate low-value alerts while retaining event counts, representative metadata, and escalation paths when volume, port breadth, destination breadth, reputation, or correlation changes.

7. SOAR actions must respect approval boundaries.

   Firewall-triggered response actions that would block an IP, change firewall policy, or notify external channels should follow existing approval-gated workflow expectations where applicable. Read-only enrichment and case/incident creation may be automatic if current SOAR policy allows it.

8. Response actions should be explicit.

   Expected `response_action` values should include `monitor_only`, `enrich_source_ip`, `create_incident`, `notify_soc`, `queue_block_source_ip`, `request_firewall_block_approval`, and `suppress_noisy_source`. Any destructive or externally visible action must be approval-gated unless existing policy explicitly permits automatic execution.

## Risks / Trade-offs

- [Risk] Firewall logs are high-volume and may create alert fatigue -> Mitigation: aggregate repeated denies, suppress noisy sources, and escalate only on breadth, repetition, protected target, reputation, or correlation.
- [Risk] Suppression can hide meaningful activity -> Mitigation: track suppressed counts and break suppression on severity escalation conditions.
- [Risk] Allow events can be overinterpreted -> Mitigation: require contextual evidence before raising severity.
- [Risk] Automated blocking can disrupt legitimate traffic -> Mitigation: require approval-gated workflow for block or firewall-policy-changing actions.

## Validation Strategy

- Validate taxonomy mapping for representative `firewall_block` and `firewall_allow` events already accepted by centralized ingest.
- Validate event-to-alert mapping for isolated block, repeated deny, port scan, suspicious allow, noisy source suppression, and correlated activity cases.
- Validate severity assignment against documented criteria and ensure routine isolated blocks remain low/no-alert.
- Validate expected alert fields are present and populated from normalized event and `raw_payload` fields.
- Validate MITRE mappings are applied only to supported detection types.
- Validate playbook trigger selection and approval-gated response-action behavior without requiring VM, deployment, live pfSense traffic, Azure NSG, VM firewall, systemd, or uncle handoff.

## Open Questions

- Confirm exact production thresholds for port scan windows, repeated deny counts, and noisy source suppression during implementation tuning.
- Confirm whether existing SOAR policy permits automatic `notify_soc` for medium/high firewall alerts or requires approval for notification.
