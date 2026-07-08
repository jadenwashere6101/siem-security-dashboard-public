## Why

`soar-notification-integration-controls-roadmap` names `soar-notification-readiness-test-buttons` as the first child spec, because nothing else in the roadmap (provider Active/Inactive controls, playbook enforcement, delivery history) should be built on top of a provider that has never been proven to actually work. Today, Slack, Teams, Email, and Webhook all share identical, well-guarded real-mode adapter code (`integrations/slack_adapter.py`, `teams_adapter.py`, `email_adapter.py`, `webhook_adapter.py`), but only Slack has ever been manually confirmed to deliver. There is no manual test-send endpoint anywhere in the codebase today — `routes/integration_routes.py` only exposes read-only combined status and circuit-breaker controls — and no durable "Tested: Passed/Failed/Never Tested" state exists for any provider. This spec plans exactly that: a safe way to prove or disprove each provider on demand, with clear, honest evidence, and nothing more.

## What Changes

- Add a detailed, code-verified audit of the current Slack/Teams/Email/Webhook adapters, existing endpoints, existing tests, existing delivery logging, and existing UI (see `design.md`).
- Define a `Configured` → `Manual Test Passed` → `Ready` readiness model, explicitly distinct from the adapter layer's existing `real_mode_ready`/`real_mode_allowed` guard-readiness concept (which answers "is this adapter deployment-guarded to attempt a real send," not "has a human proven it actually works"). Both concepts will coexist; this spec must not blur or rename the existing one.
- Plan a new, safe, rate-limited manual test-send capability for Slack, Teams, Email, and Webhook only — Firewall is explicitly excluded, has no test button, and gains no real-mode path of any kind through this spec.
- Plan a new per-provider readiness surface showing Configured (Yes/No), Tested (Passed/Failed/Never Tested), Ready (Yes/No), Missing Configuration (env var names only), and Last Test (timestamp) — kept separate from the existing, already-overloaded `/integrations/status` response rather than adding further fields to the page this whole roadmap exists to de-conflict.
- Plan reuse of the existing `notification_delivery_attempts` table and `core/notification_delivery_store.py` for recording and reading test-send results, via a new `action` value convention that marks a row as a manual test (distinct from playbook-triggered actions) and a small, additive `action` filter on `list_notification_delivery_attempts` — no new migration planned.
- Plan a small new orchestration layer for standalone test sends, since today only `engines/playbook_step_executor.py` writes to `notification_delivery_attempts`; there is no existing code path that executes an adapter and records the attempt outside of a playbook execution context.
- Explicitly exclude Active/Inactive provider toggles, playbook executor changes, notification skipping, and delivery-history dashboards — those remain scoped to later child specs in this roadmap.
- Do not implement code, modify application source files, modify tests, touch the VM, touch Azure, configure any provider, send any real notification, commit, or push.

## Capabilities

### New Capabilities
- `soar-notification-readiness-test-buttons`: defines the Configured/Tested/Ready readiness model, the manual test-send capability and its safety constraints, the missing-configuration display, the last-test-result display, and the backend/frontend/testing/validation plan needed to independently prove Slack, Teams, Email, and Webhook before any later child spec treats them as production-ready.

### Modified Capabilities
(none — this spec does not modify `soar-notification-integration-controls-roadmap`; it plans work that extends the existing adapter/delivery-store layer additively)

## Impact

- **Affected backend (future implementation only):** `routes/integration_routes.py` (new test-send route(s)), a new small orchestration module for standalone test sends, `core/notification_delivery_store.py` (additive `action` filter on `list_notification_delivery_attempts`), and each of `integrations/slack_adapter.py`, `teams_adapter.py`, `email_adapter.py`, `webhook_adapter.py` (a new `test_notification` supported action, or an equivalent test-marking convention, decided during implementation).
- **Affected frontend (future implementation only):** `frontend/src/components/IntegrationStatusPanel.js` and/or a new dedicated readiness panel, plus `frontend/src/services/integrationService.js`.
- **Affected database:** none expected — reuses the existing `notification_delivery_attempts` table (`migrations/0008_soar_notification_delivery.sql`) and its existing nullable playbook/incident/approval/alert linkage columns (left `NULL` for standalone test sends).
- **Runtime behavior:** none from this spec itself. No code is implemented here. Future implementation will not weaken or bypass the adapters' existing four-guard fail-closed real-mode model (`INTEGRATION_MODE=real` + `SOAR_ENV` allowlist + per-adapter `SOAR_REAL_<PROVIDER>_ENABLED` + credential envs) — a test send is only a manual trigger of the same already-guarded path, not a new bypass.
- **External systems:** none contacted by this spec-creation change. Future implementation of a test send will, by design, contact the real provider exactly once per click when all existing guards are met — that is the explicit purpose of a "test" button, and must remain the only real-world side effect this child spec introduces.
- **Parent roadmap:** this child belongs to `soar-notification-integration-controls-roadmap` and is sequenced first; no parent roadmap file changes are required for this spec.
