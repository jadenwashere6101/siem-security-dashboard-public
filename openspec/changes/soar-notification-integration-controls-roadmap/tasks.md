## 1. Overall Goal

Track a professional Integration Delivery Controls system for SOAR notification providers (Slack, Teams, Email, Webhook) plus the permanent simulation-only boundary for Firewall, from audit through future child implementation specs, without implementing code, creating child specs, modifying application source files, modifying tests, touching the VM, configuring any real provider, or committing/pushing.

## 2. Hard Guardrails

- [x] 2.1 Confirm this is parent roadmap creation only.
- [x] 2.2 Confirm no application source files are modified.
- [x] 2.3 Confirm no tests are modified.
- [x] 2.4 Confirm no child implementation specs are created.
- [x] 2.5 Confirm no VM access or VM source edits are performed.
- [x] 2.6 Confirm no commits or pushes are performed.
- [x] 2.7 Confirm no Slack, Teams, Email, Webhook, or Firewall configuration/credentials are touched or exposed.
- [x] 2.8 Confirm no real external notification or firewall call is made.
- [x] 2.9 Confirm Firewall's simulation/dry-run-only boundary is preserved and not questioned by this roadmap.

## 3. Phase 0 - Audit

- [x] 3.1 Audit Slack adapter real-mode capability and guards.
  - Finding: `integrations/slack_adapter.py` is real-mode capable behind the canonical four-guard model; this is the only provider with a confirmed prior manual delivery.
- [x] 3.2 Audit Teams adapter real-mode capability and guards.
  - Finding: `integrations/teams_adapter.py` is structurally identical in guard model to Slack; a prior real attempt did not work and root cause is unestablished.
- [x] 3.3 Audit Email adapter real-mode capability and guards.
  - Finding: `integrations/email_adapter.py` is SMTP-based, same four-guard model, never proven.
- [x] 3.4 Audit Webhook adapter real-mode capability and guards.
  - Finding: `integrations/webhook_adapter.py` is generic HTTPS POST, same four-guard model, never proven.
- [x] 3.5 Audit Firewall adapter real-mode capability.
  - Finding: `integrations/firewall_adapter.py` has no real-mode code path at all; its own comment requires a separate future approved OpenSpec before any real execution.
- [x] 3.6 Audit current playbook notification actions.
  - Finding: `engines/playbook_step_executor.py` already defines `notify_slack`/`notify_teams`/`notify_email`/`notify_webhook` steps with existing idempotency (`_existing_active_delivery`) but no provider Active/Inactive gate.
- [x] 3.7 Audit existing delivery logs/outcomes.
  - Finding: `notification_delivery_attempts` table (`migrations/0008_soar_notification_delivery.sql`) and `core/notification_delivery_store.py` already provide append-only, secret-redacted delivery attempt storage and read/list helpers.
- [x] 3.8 Audit existing DB tables that could store active/test/delivery state.
  - Finding: delivery-attempt history already has a home; durable per-provider Configured/Tested/Active status does not exist anywhere and is net-new.
- [x] 3.9 Audit whether new migrations are likely needed.
  - Finding: likely yes for provider Active/Inactive/Tested state (child spec 2); likely no new migration for delivery history itself (child spec 4), which can largely query the existing table.
- [x] 3.10 Audit current backend routes and UI.
  - Finding: `routes/integration_routes.py` exposes `GET /integrations/status` (combined readiness across adapters) plus circuit-breaker controls; no test-send endpoint exists. `frontend/src/components/IntegrationStatusPanel.js` already renders missing-config and readiness from existing fields, alongside an in-memory/simulated circuit breaker — confirming the "mixes simulation/real mode, readiness, circuit breaker internals, and status" problem.
- [x] 3.11 Record risks and unknowns in the roadmap.

## 4. Phase 1 - Child Spec Creation

- [x] 4.1 Create `soar-notification-readiness-test-buttons`.
  - Scope: detailed adapter audit, safe manual test-send buttons/endpoints, missing-config display, last-test-result display, re-proving Slack, proving/failing Teams/Email/Webhook clearly. No Active/Inactive enforcement yet.
- [ ] 4.2 Create `soar-notification-provider-active-controls`.
  - Scope: durable backend provider status (DB, not localStorage), UI Active/Inactive toggles for Slack/Teams/Email/Webhook, Firewall excluded from real enablement, activation gated or warned by Configured/Tested state.
- [ ] 4.3 Create `soar-playbook-notification-enforcement`.
  - Scope: executor checks provider Active state before notification steps; Active attempts delivery; Inactive skips cleanly with a recorded skipped-by-policy outcome; no fake success; no endless retry; no unrelated-step blocking unless explicitly required.
- [ ] 4.4 Create `soar-notification-delivery-history`.
  - Scope: last successful delivery, last failed delivery, last tested, secret-free error reasons, clear UI evidence — built primarily on the existing `notification_delivery_attempts` table.
- [ ] 4.5 Confirm each child spec repeats the Firewall simulation-only boundary and the Configured/Tested/Active/Delivered/Simulation terminology exactly as defined in this roadmap.
- [ ] 4.6 Confirm each child spec states which parts require backend/database changes and which can reuse existing endpoints/data.

## 5. Phase 2 - Implementation Sequencing

- [x] 5.1 Implement `soar-notification-readiness-test-buttons` first.
  - Reason: nothing should be treated as trustworthy before it can be manually proven or disproven.
- [ ] 5.2 Implement `soar-notification-provider-active-controls` second.
  - Reason: production authorization should be informed by real Tested evidence, not introduced blind.
- [ ] 5.3 Implement `soar-playbook-notification-enforcement` third.
  - Reason: playbook behavior should only change once a durable Active state exists to check against.
- [ ] 5.4 Implement `soar-notification-delivery-history` fourth.
  - Reason: evidence display is most valuable once test sends and real playbook attempts are actually producing delivery records.
- [ ] 5.5 Keep each child implementation separately validated before starting the next child implementation.

## 6. Phase 3 - Validation Plan

- [ ] 6.1 Validate guard enforcement (four-guard fail-closed model) remains intact for all four notification adapters.
- [x] 6.2 Validate manual test-send behavior and result display, fully mocked in tests (no real external calls in any test suite).
- [ ] 6.3 Validate durable provider Active/Inactive persistence and its independence from the in-memory/simulated circuit breaker.
- [ ] 6.4 Validate playbook executor skip-by-policy behavior for inactive providers, including the exact recorded message format.
- [ ] 6.5 Validate no fake-success and no endless-retry behavior for both skipped and failed notification steps.
- [ ] 6.6 Validate unrelated playbook steps are unaffected by a skipped notification step.
- [ ] 6.7 Validate delivery-history queries return correct last-success/last-failure/last-tested data without exposing secrets.
- [ ] 6.8 Validate Firewall remains simulation-only with no real-mode code path introduced anywhere in this initiative.
- [ ] 6.9 Run child-specific backend and frontend tests.
- [ ] 6.10 Run any new/changed migrations against a test database and confirm rollback/idempotent-apply behavior consistent with existing migration conventions.

## 7. Phase 4 - Deployment / Rebuild

- [ ] 7.1 Confirm this parent roadmap requires no VM sync and no deployment.
- [ ] 7.2 For future backend/migration changes, run backend validation and migration checks before any deployment.
- [ ] 7.3 For future frontend changes, build on the Mac and deploy only frontend build output when deployment is requested.
- [ ] 7.4 Before any future VM deployment sync, verify the VM working tree is clean.
- [ ] 7.5 Do not edit source code on the VM.
- [ ] 7.6 Confirm no child spec in this roadmap requires Azure work.

## 8. Phase 5 - Future Expansion Considerations

- [ ] 8.1 Decide, within child spec 2, whether provider activation strictly requires a passing Tested result or only warns without blocking.
- [ ] 8.2 Decide, within child spec 1, whether manual test sends extend `notification_delivery_attempts` with a distinguishing marker or use a separate mechanism.
- [ ] 8.3 Scope any new migration, table shape, RBAC requirement (e.g. who can toggle Active/Inactive), and audit-log behavior explicitly within the owning child spec, not in this roadmap.
- [ ] 8.4 Reassess, only in a separate future explicitly-approved OpenSpec, whether Firewall should ever gain any real-execution path; this roadmap and its four planned children must not introduce one.

## Safety Boundaries

- [x] This parent change contains no implementation steps that authorize source edits.
- [x] Do not modify application source files.
- [x] Do not modify tests.
- [x] Do not create child implementation specs as part of this parent roadmap.
- [x] Do not touch the VM.
- [x] Do not configure or contact Slack, Teams, Email, Webhook, or Firewall.
- [x] Do not expose credentials or secrets.
- [x] Do not commit.
- [x] Do not push.
