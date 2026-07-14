## 1. Slack Path Inventory And Unified Contract

- [x] 1.1 Trace every current playbook `notify_slack` path from playbook step execution to Slack adapter invocation and confirm the exact remaining bypass points.
- [x] 1.2 Refactor the notification-policy service contract so alert, incident, route-test, and playbook-originated Slack sends can share one policy-evaluated backend entrypoint.
- [x] 1.3 Define and implement the bounded notification purpose and delivery-stage contract for policy-routed Slack sends.
- [x] 1.4 Reuse existing notification-delivery evidence to support deterministic duplicate suppression without adding a migration, or stop and report the precise blocker if reuse is unsafe.

## 2. Playbook Slack Policy Integration

- [x] 2.1 Update the playbook execution path so every `notify_slack` step routes through notification policy before any Slack adapter call.
- [x] 2.2 Preserve non-Slack adapter actions and keep `SOAR_REAL_SLACK_ENABLED` as the final adapter-level guard for Slack sends.
- [x] 2.3 Ensure Slack suppression or duplicate-skip outcomes do not fail playbook execution or change approval/containment behavior.
- [x] 2.4 Record clear append-only delivery or suppression evidence for policy-routed playbook Slack attempts without exposing secrets.

## 3. Deduplication And Purpose Behavior

- [x] 3.1 Implement deterministic duplicate suppression for equivalent Slack notifications across overlapping playbooks using alert or incident identity plus purpose, route, and stage.
- [x] 3.2 Preserve independent delivery eligibility for intentionally different lifecycle messages such as immediate Critical alert pages and later containment outcomes.
- [x] 3.3 Keep unsupported sources and missing route-specific webhooks fail-closed without falling back across routes or to the generic webhook in policy sends.

## 4. Core Playbook Reconciliation

- [x] 4.1 Audit every core playbook containing `notify_slack` and classify each step as remove, retain as `investigation_update`, or retain as `containment_outcome`.
- [x] 4.2 Update the seeded core playbook definitions and any idempotent reconciliation path so redundant immediate-equivalent Slack steps are removed while distinct outcome steps remain.
- [x] 4.3 Verify persisted core playbook reconciliation remains idempotent after the Slack-step changes.

## 5. UI And Documentation Clarification

- [x] 5.1 Reuse the existing Notification Policy UI and add only minimal explanatory text if needed to state that playbook Slack sends also obey notification policy.
- [x] 5.2 Keep the legacy SOAR integrations/manual Slack test clearly separate from notification-policy routing behavior.

## 6. Verification

- [x] 6.1 Add or update focused backend tests covering unified playbook Slack policy gating, global disable, minimum severity, route isolation, missing-secret behavior, deduplication, distinct lifecycle messages, and suppression-without-playbook-failure.
- [x] 6.2 Add or update focused tests for core playbook reconciliation and any affected frontend text if UI copy changes.
- [x] 6.3 Run Python compilation, affected backend tests, affected frontend tests if needed, schema validation, `openspec validate unify-slack-delivery-under-notification-policy --strict`, and `git diff --check`.
