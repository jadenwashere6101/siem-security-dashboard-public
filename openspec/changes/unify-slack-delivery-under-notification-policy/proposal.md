## Why

Slack delivery is currently split between the notification-policy path and legacy playbook `notify_slack` steps. That split bypasses the runtime policy controls that were just added, and it allows overlapping playbooks to send duplicate equivalent messages for the same alert even when operators expect one authoritative Slack decision path.

## What Changes

- Route every playbook `notify_slack` step through the existing notification-policy evaluation path before any Slack adapter call.
- Keep `SOAR_REAL_SLACK_ENABLED` as the final adapter-level kill switch after policy evaluation and route selection.
- Add a bounded notification-purpose contract so playbook-originated Slack sends can be classified as immediate alert paging, incident creation, investigation update, containment outcome, or route test.
- Add deterministic duplicate suppression for equivalent Slack sends using the existing notification delivery evidence store rather than a new generic framework.
- Reconcile current core playbook Slack steps so duplicate immediate messages are removed, while intentionally distinct lifecycle updates remain eligible to send once.
- Reuse the existing Notification Policy UI, adding only small read-only explanatory text if needed to clarify that all playbook Slack sends now obey policy.
- Preserve current route-specific webhook behavior for policy sends and keep the legacy generic `SLACK_WEBHOOK_URL` path only for explicitly non-policy/manual integration tests.
- Avoid database migration unless implementation proves an existing authoritative key cannot safely support policy-purpose deduplication.

## Capabilities

### New Capabilities
- `unify-slack-delivery-under-notification-policy`: defines one authoritative Slack decision path for alerts, incidents, playbook notifications, bounded notification purposes, deterministic duplicate suppression, and safe suppression/failure behavior without changing detection or containment logic.

### Modified Capabilities
- None.

## Impact

- **Affected backend:** `core/notification_policy_service.py`, `engines/playbook_step_executor.py`, `engines/playbook_registry.py`, `core/core_playbook_pack_v1.py`, notification delivery attempt recording, and the small admin/runtime policy surface if explanatory text is added.
- **Affected frontend:** existing Notification Policy panel only if explanatory copy is needed.
- **Affected APIs:** existing notification-policy admin APIs and route-test APIs remain the control surface; no new general notification page is added.
- **Affected database:** prefer none; implementation should reuse `notification_delivery_attempts` and the existing `notification_policy` table if they can safely support purpose/stage-aware deduplication.
- **Out of scope:** new provider types, per-rule routing, arbitrary templates, detection severity changes, approval redesign, VM changes, and any enablement of Slack in Mac or production runtime settings.
