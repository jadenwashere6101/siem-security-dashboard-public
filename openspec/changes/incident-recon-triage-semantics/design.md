## Context

The audit found three relevant facts:

- Detection functions create alerts with deterministic severities. Incident creation receives `alerts_created` after commit and usually stores the alert severity directly on the incident.
- Current incident policy has started separating priority from severity, but the incident UI still makes High source-alert severity look like High incident severity.
- Recon Activities are intentionally pfSense-scoped, but singleton eligible alerts can create durable activities whose display headline becomes "Source-specific recon." That overstates weak evidence in primary analyst views.

Existing historical records are evidence and must remain trustworthy. This change is prospective unless an explicit migration/backfill policy is approved.

## Goals / Non-Goals

**Goals:**
- Define separate meanings for alert severity, incident severity presentation, incident priority, and actionability.
- Keep deterministic alert creation stable while making incident triage less severity-inflated.
- Make honeypot incident eligibility alert-first for noisy singleton activity and case-worthy for stronger credential or corroborated activity.
- Add recon materiality stages and prevent weak singleton recon from occupying primary analyst views as meaningful "Source-specific recon."
- Preserve source-IP pivots, linked alerts, related-event evidence, notifications, RBAC, audit logging, and historical compatibility.

**Non-Goals:**
- No new detector families.
- No silent historical rewrite.
- No generic campaign platform beyond current incident/recon surfaces.
- No VM deployment or runtime remediation in the Mac implementation phase.

## Decisions

### 1. Treat alert severity as detector severity

Alert severity remains the detector's confidence/impact classification for an individual alert. It is not automatically the incident's business severity.

Alternative considered: retune all alert severities first. Rejected because it would destabilize detections and historical comparisons while only partly fixing incident presentation.

### 2. Present incident severity as a derived triage field

Implementation SHALL choose one explicit model before changing code:

- Preferred: store/present `incident_severity` as a recalculated incident triage severity derived from linked evidence, criticality, progression, scope, and actionability, while also exposing `max_linked_alert_severity`.
- Minimum acceptable fallback: keep the existing database `incidents.severity` as `max_linked_alert_severity` but rename UI/API presentation so analysts do not read it as incident triage severity.

The preferred model is cleaner but may require additive schema/API fields. The fallback is lower risk but leaves more legacy ambiguity.

### 3. Keep incident priority as urgency

Priority remains P1/P2/P3 and SHALL reflect response urgency. A High alert can produce a P3 incident when case-worthy but not urgent. A Critical alert or likely compromise remains P1.

### 4. Gate incident creation by actionability

Incident creation SHALL require case-worthy evidence, not only High alert severity. Honeypot scanner/admin/single env probing stay alert-only. Honeypot credential activity can create an incident when repeated or corroborated. pfSense routine recon remains aggregate-visible without per-source incident fan-out; source-specific progression remains incident-eligible.

### 5. Introduce recon materiality stages

Recon stage SHALL be one of:

- `recon_candidate`: singleton or weak evidence retained for pivots/evidence, hidden from primary analyst views by default.
- `recon_cluster`: multiple related alerts or sources with shared target/service evidence, visible in recon views.
- `possible_campaign`: sustained or broader cluster with medium confidence.
- `campaign_recon`: high-confidence multi-source/progression/incident-backed campaign.

Singleton persistence can remain if needed for dedupe and pivots, but primary views SHALL suppress or visually demote `recon_candidate`.

### 6. Preserve evidence-first navigation

Any suppression from primary views must not delete evidence. Analysts must still be able to reach source-IP context, linked alerts, related events, and backend details from alert detail or explicit search.

## Risks / Trade-offs

- [Historical ambiguity] Existing incident rows may keep old High values -> Mitigation: expose legacy labels and avoid rewriting without a migration/backfill plan.
- [Notification behavior changes] Severity presentation may affect notification thresholds -> Mitigation: keep notification policy inputs explicit: alert severity, incident triage severity, priority, and event kind.
- [Recon under-surfacing] Suppressing singleton candidates could hide early signals -> Mitigation: keep candidates available in explicit detail/search/source-IP context and promote them when thresholds are met.
- [Schema churn] Recalculated incident severity may need new fields -> Mitigation: prefer additive columns/API fields and compatibility projections.
- [Test fixture drift] Existing tests may assume High incidents -> Mitigation: update tests around semantics, not raw legacy fields, and add production-derived acceptance cases.

## Migration Plan

1. Implement prospectively on Mac source: backend semantic helpers, API projections, frontend presentation, and tests.
2. If additive fields are needed, add migrations and schema validation locally.
3. Do not rewrite old records by default. If historical cleanup is required, create an explicit dry-run-first backfill with before/after counts and rollback notes.
4. After commit/push approval, VM AI deploys through the documented Gunicorn/systemd and migration workflow.

## Open Questions

- Should the implementation choose the preferred recalculated `incident_severity` model, or the lower-risk "max linked alert severity" presentation model for the first phase?
- Should `recon_candidate` be persisted in `recon_activities` with a stage field, or staged in alert context until promoted?
- Which existing notification filters should use incident triage severity versus priority?
