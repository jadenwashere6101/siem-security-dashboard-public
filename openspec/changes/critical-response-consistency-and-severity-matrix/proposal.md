## Why

Critical is the SIEM's top severity, but it currently behaves inconsistently. Two of the three Critical-producing paths overstate their evidence or duplicate each other: `web_to_app_attack_pattern` is hardcoded Critical despite having no confirmed-login evidence, and `spray_then_success_pattern` requires the very same `successful_login_after_spray` alert to already exist, so the same compromise evidence produces a second Critical alert, a second incident-eligible path, and a second approval-gated containment playbook. Separately, `maybe_create_or_link_incident` never upgrades an existing lower-severity incident when a Critical alert links to it, so a High/P2 incident can silently absorb Critical evidence without becoming P1. Notification routing only recognizes `pfsense` and `honeypot` sources (`normalize_notification_source`), so Critical alerts from `bank_app` and `nginx`/correlation sources never reach the notification-policy Slack path at all — and several ingest routes call `_send_alert_notifications_for_alerts` both directly and again inside `_create_playbook_executions_for_alerts`, double-sending the same Slack message today. Finally, analysts have no authoritative, in-product reference for what Low/Medium/High/Critical actually mean or how each detection currently behaves, so severity is effectively tribal knowledge.

## What Changes

- Adopt a single, documented severity definition (Low/Medium/High/Critical) and reclassify the three Critical-producing paths against it, based on the actual evidence each rule requires.
- **BREAKING**: `web_to_app_attack_pattern` severity changes from `critical` to `high`; its playbook trigger threshold is updated to match.
- Reduce `spray_then_success_pattern` to an investigation/correlation signal rather than a second full containment path, since it duplicates `successful_login_after_spray` evidence; `successful_login_after_spray` remains the sole canonical Critical containment trigger for that evidence set.
- Add incident severity/priority upgrade behavior: a Critical alert linking to an existing open High/P2 (or lower) incident upgrades it to Critical/P1 and records an audit trail entry. Incidents are never downgraded, and a Critical alert never spawns a duplicate incident solely to obtain P1.
- Extend notification-policy source routing with one new bounded destination for non-pfSense/non-honeypot Critical sources (`bank_app`, `nginx`, correlation alerts), instead of routing them through the pfSense or honeypot webhook.
- Fix the existing double-notification bug where several ingest routes call the alert-notification path twice for the same alert.
- Ensure the immediate notification-policy Slack path fires before any approval gate, and align/de-duplicate it against legacy per-playbook `notify_slack` steps for Critical paths so the same Critical event does not page Slack twice.
- Ensure Critical alerts never resolve to `response_action = "monitor"` when policy calls for investigation/containment consideration; keep unattended approval expiration fail-closed (`not_actioned`) and containment approval-gated.
- Add a read-only, backend-sourced "Severity & Response Matrix" workspace so analysts can see severity definitions and per-detection behavior without a second, drifting policy model in the frontend.

## Capabilities

### New Capabilities
- `critical-alert-severity-contract`: formal Low/Medium/High/Critical definitions, final severity for each current Critical-producing detector/correlation, and precedence between overlapping spray-success signals.
- `incident-severity-escalation`: incident upgrade-on-link behavior, audit trail, and no-downgrade/no-duplicate guarantees.
- `critical-notification-routing`: immediate pre-approval Critical notification, new source-routing destination, Slack-failure fail-open behavior, and de-duplication against legacy playbook notifications.
- `severity-response-matrix`: read-only backend contract and frontend workspace exposing severity meaning and per-detection behavior.

### Modified Capabilities
- None. The existing `openspec/specs/core-playbook-pack-v1/spec.md` documents an earlier five-playbook planning phase that no longer matches the thirteen playbooks actually seeded in `core/core_playbook_pack_v1.py`; rather than editing that stale spec, playbook trigger/step consistency for the two affected playbooks (`core-v1-web-to-app-attack-investigation`, `core-v1-spray-then-success-correlation-investigation`) is captured as new requirements under `critical-alert-severity-contract` below, scoped to this change's actual playbooks.

## Impact

- Backend: `engines/correlation_engine.py`, `engines/detection_config.py`, `core/incident_store.py`, `core/notification_policy_service.py`, `core/notification_policy_store.py`, `core/core_playbook_pack_v1.py`, `core/playbook_store.py`, `routes/ingest_routes.py`, `core/ip_helpers.py` (response-action floor), a new migration extending `notification_policy`, and a new read-only matrix API route.
- Frontend: new `Severity & Response Matrix` section registered in `sectionsConfig.js`, a new read-only component/service, and a link from `NotificationPolicyPanel`.
- No new detection rules, no auto-containment, no CMDB/analytics work.
