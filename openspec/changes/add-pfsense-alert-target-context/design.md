## Context

The current pfSense pipeline already preserves destination evidence at ingest time inside `events.raw_payload`. The four pfSense detector families then persist a smaller alert summary in `alerts.context`, and the alerts APIs already return that context verbatim. The missing piece is a stable target-oriented sub-structure that the UI can render without parsing detector-specific message text or opening a new backend endpoint.

The change is intentionally narrow. The authoritative event source remains `events.raw_payload`. `alerts.context` remains a snapshot for investigations, not a second event store. `AlertDetailsPanel` is the only new UI surface. There is no migration, no dedicated enrichment endpoint, and no asset-labeling system in this phase.

## Goals / Non-Goals

**Goals:**
- Standardize a `target_context` shape for pfSense alerts inside the existing `alerts.context` JSON.
- Preserve single-target precision for `pfsense_firewall_repeated_deny` and `pfsense_firewall_suspicious_allow`.
- Add deterministic top-target aggregation for `pfsense_firewall_port_scan` and `pfsense_firewall_noisy_source` without fabricating an exact destination.
- Surface the new context through existing alerts payloads and `AlertDetailsPanel`.
- Keep the UI read-only, accessible, and narrow-layout safe.

**Non-Goals:**
- No new endpoint or backend enrichment service.
- No migration or denormalized event table columns.
- No manual asset labels, application-name mapping, CMDB, topology, or Azure enrichment.
- No new UI surfaces beyond `AlertDetailsPanel`.
- No changes to playbook execution, leases, retries, approvals, or non-pfSense alerts.

## Decisions

### Persist a nested `context.target_context` snapshot

Store target evidence under `alerts.context["target_context"]` while preserving existing top-level pfSense context keys used by current API consumers.

Rationale: this adds one documented shape for the new UI without breaking the current `why-fired` contract or forcing all existing pfSense evidence to move at once.

Alternative considered: replace the current pfSense context shape entirely. Rejected because it creates avoidable compatibility risk for existing tests and routes that already read the top-level fields.

### Use exact fields for single-target families and aggregate fields for multi-target families

For `pfsense_firewall_repeated_deny` and `pfsense_firewall_suspicious_allow`, persist:
- `mode: "single_target"`
- `destination_ip`
- `destination_port`
- `protocol`
- `firewall_action`
- `attempts`
- `first_seen`
- `last_seen`
- `interface`
- `direction`

For `pfsense_firewall_port_scan` and `pfsense_firewall_noisy_source`, persist:
- `mode: "aggregate_targets"`
- `top_destination_ip`
- `top_destination_port`
- `distinct_destination_count` where available
- `distinct_port_count` where available
- `attempts`
- `first_seen`
- `last_seen`
- `firewall_action` when it can be summarized safely

Rationale: single-target families already identify one concrete target, while multi-target families represent breadth across multiple targets and must not fabricate a precise destination.

### Compute top-target aggregation directly in detector queries

Derive top destination IP and top destination port from the same event window that produced the alert, using deterministic frequency ordering and stable tie-breaking.

Rationale: this keeps `events.raw_payload` as the source of truth, avoids a migration, and keeps the alert snapshot self-contained for later UI reads.

Alternative considered: compute aggregation on demand in the API or UI. Rejected because it duplicates detector-window logic and weakens the persisted alert snapshot as the investigation record.

### Reuse the existing alerts transport and render only in `AlertDetailsPanel`

No dedicated target-context endpoint will be added. The existing alert APIs already return `context`, and `AlertDetailsPanel` already owns detailed alert investigation content.

Rationale: this is the smallest maintainable contract and the narrowest UI addition that materially improves investigations.

## Risks / Trade-offs

- Detector aggregation tie cases could produce unstable top-target output -> use explicit ordering by count descending and deterministic secondary sort by destination value.
- Duplicating too much raw event data into `alerts.context` could blur source of truth -> persist only the investigation summary fields listed above.
- The UI could misrepresent aggregate fields as exact targets -> include explicit labels separating exact destination fields from top-target aggregate fields.
- Existing `why-fired` consumers could regress if top-level context keys move -> keep current top-level pfSense keys intact and add `target_context` additively.
