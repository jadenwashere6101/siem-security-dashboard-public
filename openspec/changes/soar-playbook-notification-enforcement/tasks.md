## 1. Audit and Planning

- [ ] 1.1 Reconfirm `notify_slack`, `notify_teams`, `notify_email`, and `notify_webhook` mappings in `engines/playbook_step_executor.py`.
- [ ] 1.2 Reconfirm `_existing_active_delivery()` remains a delivery-idempotency helper and is not confused with provider Active state.
- [ ] 1.3 Reconfirm current Slack, Teams, Email, and Webhook adapter guard/fail-closed behavior.
- [ ] 1.4 Reconfirm `notification_delivery_attempts` statuses and whether a `skipped` status migration is needed.
- [ ] 1.5 Reconfirm response-outcome event fields can represent skipped-by-policy without secrets.
- [ ] 1.6 Reconfirm response-action queue retry/skipped semantics remain separate from playbook notification delivery.
- [ ] 1.7 Reconfirm prior Active-controls implementation and its read helper/table shape before coding.
- [ ] 1.8 Reconfirm Firewall remains simulation/dry-run only and excluded from this enforcement.

## 2. Backend Enforcement

- [ ] 2.1 Add or reuse a provider-control read helper that returns Active state for Slack, Teams, Email, and Webhook.
- [ ] 2.2 Treat missing provider-control rows as inactive.
- [ ] 2.3 Fail closed when provider Active state cannot be read.
- [ ] 2.4 Check provider Active state before notification adapter execution.
- [ ] 2.5 Preserve duplicate-delivery idempotency behavior.
- [ ] 2.6 Preserve existing Active-provider adapter/env/fail-closed behavior and delivery logging.
- [ ] 2.7 Skip Inactive providers with a clear skipped-by-policy step entry.
- [ ] 2.8 Ensure Inactive providers do not create fake success, retry loops, or dead letters.
- [ ] 2.9 Ensure unrelated later playbook steps continue unless a playbook explicitly requires the notification.

## 3. Delivery and Outcome Evidence

- [ ] 3.1 Decide whether to add `skipped` to `notification_delivery_attempts.status`.
- [ ] 3.2 If adding `skipped`, add migration/store support and append skipped delivery rows for inactive policy skips.
- [ ] 3.3 If not adding `skipped`, record skipped-by-policy through step log and response outcome only.
- [ ] 3.4 Record policy-read failures distinctly from provider inactive and delivery failures.
- [ ] 3.5 Keep all metadata secret-free and preserve existing redaction.

## 4. Frontend

- [ ] 4.1 Audit `PlaybooksPanel.js` execution timeline rendering for skipped notification step clarity.
- [ ] 4.2 If needed, display skipped-by-policy clearly in execution/timeline views.
- [ ] 4.3 Do not add provider Active/Inactive toggles in this spec.
- [ ] 4.4 Do not add manual test-send buttons or delivery-history dashboard UI.

## 5. Tests

- [ ] 5.1 Add executor tests for Active Slack, Teams, Email, and Webhook preserving existing adapter behavior.
- [ ] 5.2 Add executor tests for Inactive Slack, Teams, Email, and Webhook ensuring no provider send/adapter delivery is called.
- [ ] 5.3 Add tests for skipped-by-policy step log and response outcome evidence.
- [ ] 5.4 Add tests that inactive policy is not fake success and not system failure.
- [ ] 5.5 Add tests that inactive policy does not create retry loops or dead letters.
- [ ] 5.6 Add tests that unrelated later steps continue after inactive notification skips.
- [ ] 5.7 Add tests for provider Active-state read failure fail-closed behavior.
- [ ] 5.8 Add migration/store tests if `notification_delivery_attempts.status` gains `skipped`.
- [ ] 5.9 Add frontend tests only if execution/timeline rendering changes.
- [ ] 5.10 Keep all provider/network/firewall calls mocked; no tests may contact real external systems.

## 6. Validation

- [ ] 6.1 Run relevant backend tests.
- [ ] 6.2 Run relevant frontend tests if frontend code changes.
- [ ] 6.3 Run migration validation if a migration is added.
- [ ] 6.4 Run `openspec validate soar-playbook-notification-enforcement --strict`.
- [ ] 6.5 Run `git diff --check`.

## 7. Explicitly Deferred

- [ ] 7.1 Manual test-send buttons remain in `soar-notification-readiness-test-buttons`.
- [ ] 7.2 Provider Active/Inactive UI creation remains in `soar-notification-provider-active-controls`.
- [ ] 7.3 Provider status table/migration creation remains in `soar-notification-provider-active-controls` unless the prior implementation already exists and only a `skipped` delivery status migration is needed here.
- [ ] 7.4 Delivery history dashboard remains in `soar-notification-delivery-history`.
- [ ] 7.5 Real notification configuration is out of scope.
- [ ] 7.6 Real firewall execution is out of scope and requires a separate explicitly approved OpenSpec.
- [ ] 7.7 VM, Azure, commits, and pushes are out of scope.
