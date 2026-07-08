## 1. Scope Confirmation

- [x] 1.1 Confirm this child spec belongs under `openspec/changes/soar-notification-integration-controls-roadmap` and is sequenced first.
- [x] 1.2 Confirm this spec is about proving providers, not enabling, enforcing, or reporting delivery history.
- [x] 1.3 Confirm scope is limited to Slack, Teams, Email, Webhook; Firewall is excluded entirely.
- [x] 1.4 Confirm no Active/Inactive toggle, playbook executor change, or delivery-history dashboard is introduced by this spec.
- [x] 1.5 Confirm no real notification is sent, no provider is configured, and no secret is exposed while creating or reviewing this spec.

## 2. Readiness Helper Audit And Design

- [x] 2.1 Confirm, per provider, the exact existing "configured" boolean/fields already computed by `get_slack_real_mode_readiness`, `get_teams_real_mode_readiness`, `get_email_real_mode_readiness`, `get_webhook_real_mode_readiness` and reuse them as the basis for `Configured` rather than `real_mode_allowed`/`real_mode_ready`.
- [x] 2.2 Confirm and, if needed, correct Email's "Configured" env var list — the existing readiness function does not currently check `SMTP_PASSWORD` even though the adapter uses it for auth.
- [x] 2.3 Define the exact `missing_configuration` env var name list per provider (Slack: `SLACK_WEBHOOK_URL`; Teams: `TEAMS_WEBHOOK_URL`; Email: `SMTP_HOST`, `SMTP_USERNAME`, `SMTP_FROM_EMAIL`, `SMTP_TO_EMAIL` plus any correction from 2.2; Webhook: `WEBHOOK_URL`/`WEBHOOK_BASE_URL`).
- [x] 2.4 Confirm `missing_configuration` never includes deployment-mode guard names (`INTEGRATION_MODE`, `SOAR_ENV`, `SOAR_REAL_<PROVIDER>_ENABLED`) — those are not "configuration" in this spec's model.

## 3. Test-Send Orchestration (Backend)

- [x] 3.1 Add a new orchestration function (e.g. `core/notification_test_service.py`) that validates the adapter name is one of `slack`/`teams`/`email`/`webhook`, rejecting `firewall` and any unknown name.
- [x] 3.2 If not Configured, return a clear "not configured" result without attempting a send and without writing a delivery-attempt row.
- [x] 3.3 If Configured, execute the adapter's existing guarded real-mode path with a `test_notification` action (added to each of the four adapters' `supported_actions`, or an equivalent test-marking convention decided at implementation time) and a synthetic, per-call `correlation_id`/`idempotency_key`.
- [x] 3.4 Record the outcome via `create_notification_delivery_attempt`, leaving `playbook_execution_id`/`incident_id`/`approval_request_id`/`alert_id` `NULL`.
- [x] 3.5 Confirm the test path goes through the existing per-adapter rate limiter (`check_adapter_rate_limit`) exactly as a real send would.
- [x] 3.6 Confirm the test payload text is unmistakably marked as a manual readiness test, not a real security event.
- [x] 3.7 Confirm guard-blocked attempts are recorded with `status = "blocked"`, not `"failed"`.
- [x] 3.8 Do not add `test_notification` (or any real-mode action) to `FirewallSimulationAdapter`.

## 4. Backend Endpoints

- [x] 4.1 Add `POST /integrations/<adapter_name>/test-send` in `routes/integration_routes.py`, `login_required` + `super_admin_required`, 404 for `firewall`/unknown names.
- [x] 4.2 Add a new `GET` readiness endpoint (e.g. `GET /integrations/notification-readiness`) returning, per provider: `configured`, `missing_configuration`, `tested` (`passed`/`failed`/`never_tested`), `ready`, `last_test_at`.
- [x] 4.3 Add an additive, optional `action` filter parameter to `list_notification_delivery_attempts` in `core/notification_delivery_store.py`.
- [x] 4.4 Use the new `action` filter (or `provider` + post-filter) to compute "most recent `test_notification` attempt per provider" for the readiness endpoint.
- [x] 4.5 Confirm the new endpoints do not modify or weaken `GET /integrations/status`'s existing response shape or the circuit-breaker routes.
- [x] 4.6 Confirm no endpoint added here ever returns a webhook URL, SMTP credential, or webhook auth token.

## 5. Frontend

- [x] 5.1 Add a new readiness panel (or clearly separated section, not additional fields bolted onto the existing mixed status/circuit-breaker view) rendering Configured/Tested/Ready/Missing Configuration/Last Test/Test button per provider, for Slack/Teams/Email/Webhook only.
- [x] 5.2 Add `getNotificationReadiness()` to `frontend/src/services/integrationService.js` calling the new `GET` endpoint.
- [x] 5.3 Add `sendNotificationTest(adapterName)` to `integrationService.js` calling the new `POST` endpoint, mirroring the existing `postCircuitControl` fetch pattern (`buildSiemPath`, `parseJsonResponse`, `getApiErrorMessage`).
- [x] 5.4 Add a confirmation step before sending a test (real, singular external action).
- [x] 5.5 Render all three Tested outcomes distinctly — Passed, Failed, and Never Tested (including a guard-blocked result read as a form of Never Tested with a guard reason, never as bare "Failed").
- [x] 5.6 Disable or clearly explain the Test button when a provider is not Configured.
- [x] 5.7 Confirm no Firewall card or Firewall test button appears anywhere in this new panel.

## 6. Tests To Add During Implementation

- [x] 6.1 Unit test the new readiness helper's `configured`/`missing_configuration` output for each provider, including fully configured, partially configured, and fully unconfigured cases.
- [x] 6.2 Unit test the test-send orchestration: rejects `firewall`/unknown adapters; skips the send and records nothing when not Configured; records `blocked` when a deployment guard is missing; records `success`/`failed`/`timeout` correctly when a (mocked) real call is attempted — no test in this suite may contact a real Slack/Teams/SMTP/webhook endpoint.
- [x] 6.3 Unit test that test-send attempts respect the existing rate limiter.
- [x] 6.4 Unit test the `action` filter addition to `list_notification_delivery_attempts` is backward compatible (existing callers without the new param behave unchanged).
- [x] 6.5 Route test for `POST /integrations/<adapter_name>/test-send`: auth enforcement (`super_admin_required`), 404 for firewall/unknown adapters, correct response shape for each Tested outcome.
- [x] 6.6 Route test for the new `GET` readiness endpoint: correct per-provider shape, correct `ready` computation (Configured AND Tested=Passed), correct `last_test_at`.
- [x] 6.7 Component tests for the new frontend panel: renders all four providers and no Firewall card; renders each Tested outcome distinctly; confirmation step blocks accidental sends; Test button disabled/explained when not Configured.
- [x] 6.8 Regression test that `GET /integrations/status` and existing circuit-breaker routes/tests are unaffected.

## 7. Validation To Run During Implementation

- [x] 7.1 Run focused backend tests for the readiness helper, test-send orchestration, and new endpoints.
- [x] 7.2 Run focused frontend tests for the new readiness panel.
- [x] 7.3 Run the existing `tests/test_integration_adapters.py`, `tests/test_notification_delivery_store.py`, `tests/test_notification_delivery_routes.py`, and `tests/test_notification_delivery_metrics_routes.py` suites to confirm no regression.
- [x] 7.4 Confirm no test in the full suite performs a real outbound network/SMTP call.
- [x] 7.5 Run `git diff --check`.

## 8. Out Of Scope

- [x] 8.1 Do not add provider Active/Inactive toggles or any durable production-enablement state.
- [x] 8.2 Do not change the playbook executor, notification step handling, or skip-by-policy behavior.
- [x] 8.3 Do not build a delivery-history dashboard or cross-provider aggregate view beyond this spec's own Last Test field.
- [x] 8.4 Do not add any Firewall test button, endpoint, or real-mode path.
- [x] 8.5 Do not add a new database migration unless implementation discovers a genuine gap not identified in `design.md`; if so, that gap and its migration must be explicitly justified before proceeding.
- [x] 8.6 Do not touch the VM.
- [x] 8.7 Do not touch Azure.
- [x] 8.8 Do not configure or contact a real Slack, Teams, Email, or Webhook endpoint while writing or reviewing this spec.
