## Why

Incident and recon triage currently mix detection severity, incident severity, urgency, and analyst actionability too closely. The completed audit confirmed that new incidents inherit alert severity, while weak singleton recon activities can be persisted and surfaced as "Source-specific recon," creating a noisy analyst experience even after earlier pfSense and incident policy improvements.

This change defines durable semantics before implementation so the system can preserve deterministic detections and historical compatibility while presenting incidents and recon activity in terms analysts can trust.

## What Changes

- Define explicit meanings for alert severity, incident severity or severity presentation, incident priority, and actionability.
- Decide and implement whether incident severity is recalculated from linked evidence or presented as "max linked alert severity" without implying every High alert is a High incident.
- Review automatic incident eligibility for honeypot detections so single noisy probes remain alert-visible without misleading High incidents.
- Define recon stages: `recon_candidate`, `recon_cluster`, `possible_campaign`, and `campaign_recon`.
- Prevent weak singleton recon activity from appearing as meaningful "Source-specific recon" in primary analyst views.
- Define materiality thresholds using linked alerts, source count, duration, severity, progression, and incident linkage.
- Preserve source-IP pivots, linked-alert evidence, backend auditability, and historical rows.
- Include an explicit migration/backfill decision before any historical incident or recon records are rewritten.

## Capabilities

### New Capabilities
- `incident-recon-triage-semantics`: Defines analyst-facing incident and recon semantics, eligibility, presentation, stages, and production-derived acceptance outcomes.

### Modified Capabilities
- None.

## Impact

Affected areas include detector output interpretation, `core/incident_store.py`, `core/recon_activity_store.py`, incident and recon API projections, notification policy inputs, incident/recon frontend views, source-IP pivots, and focused regression tests. Later implementation may require additive schema or migration work if the selected design stores recalculated incident severity, recon stage, or suppression state separately from existing fields.
