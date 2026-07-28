## 1. Semantic Model Decisions

- [x] 1.1 Choose the first-phase incident severity model: recalculated `incident_severity` plus `max_linked_alert_severity`, or explicit presentation-only relabeling of the existing severity field.
- [x] 1.2 Choose the first-phase recon candidate storage model: persisted `recon_activities` stage, alert-context staging, or additive candidate table.
- [x] 1.3 Document whether any historical incident or recon rows require an explicit dry-run-first migration/backfill, or confirm prospective-only behavior.

## 2. Backend Incident Semantics

- [x] 2.1 Add focused semantic helpers for alert severity, incident severity presentation, priority, and actionability without changing detector severity outputs.
- [x] 2.2 Update incident creation/linking to apply actionability gates for honeypot, pfSense, correlation, and generic high/critical alerts.
- [x] 2.3 Update incident list/detail API projections to expose priority reasons, severity presentation, and maximum linked alert severity clearly.
- [x] 2.4 Preserve legacy incident compatibility and make legacy semantics explicit in API/UI projection when needed.
- [x] 2.5 Add backend tests for single honeypot alerts, repeated honeypot credential activity, low/medium linked incidents, and genuinely critical incidents.

## 3. Backend Recon Semantics

- [x] 3.1 Add recon stage calculation for `recon_candidate`, `recon_cluster`, `possible_campaign`, and `campaign_recon`.
- [x] 3.2 Update recon enrollment or projection so singleton weak candidates do not appear as meaningful "Source-specific recon" in primary views.
- [x] 3.3 Preserve source-IP, linked-alert, related-event, and explicit-search access for suppressed or candidate recon evidence.
- [x] 3.4 Add backend tests for one eligible pfSense recon alert, several related alerts from one source, and multiple sources over time with service overlap.

## 4. Frontend Presentation

- [x] 4.1 Update Incident UI labels to distinguish incident triage severity, max linked alert severity, priority, and actionability.
- [x] 4.2 Update Recon Activity UI to show stages and suppress or visually demote `recon_candidate` from primary analyst views.
- [x] 4.3 Preserve existing pivots from incident, alert detail, recon detail, and source-IP context.
- [x] 4.4 Add focused frontend tests for incident semantic labels, recon candidate suppression, and promotion to visible recon stages.

## 5. Notifications and SOAR Interactions

- [x] 5.1 Reconfirm notification policy inputs for alert severity, incident severity presentation, priority, and recon stage.
- [x] 5.2 Reconfirm playbook and queue trigger behavior does not regress RBAC, audit logging, protected-target checks, fail-closed integration guards, or simulation/tracking-only semantics.
- [x] 5.3 Add focused regression tests for notification and SOAR trigger decisions affected by semantic changes.

## 6. Verification and Handoff

- [x] 6.1 Run focused backend tests for incident policy, recon activity, notification policy, and affected API contracts.
- [x] 6.2 Run focused frontend tests for Incident and Recon Activity views.
- [x] 6.3 Run migration/schema validation if additive schema changes are selected.
- [x] 6.4 Run frontend production build if frontend source changes are included.
- [x] 6.5 Run `git diff --check`.
- [x] 6.6 Run `openspec validate incident-recon-triage-semantics --strict`.
- [x] 6.7 Prepare a VM handoff for eventual implementation deployment, including migration/backfill and production smoke-test requirements.
