## 1. MAC AI — Source and Contract Audit Pass

- [x] 1.1 Reconfirm UI → handler/service → `/blocked-ips`/canonical command → response-command service → blocklist/registry/outcome/audit tables → synchronized UI flow.
- [x] 1.2 Inventory every `blocklist` section ID, landing preference, deep link, service call, legacy route, protected-target check, RBAC decorator, audit event, and idempotency key.
- [x] 1.3 Confirm no schema/migration or new removal endpoint is required and document exact VM handoff queries/endpoints without secret output.

## 2. MAC AI — Consolidation Implementation Pass

- [x] 2.1 Remove the standalone visible Blocklist entry and update section-order/visibility tests.
- [x] 2.2 Normalize stored/default/internal legacy `blocklist` destinations to Response Registry `blocklist_tracking`.
- [x] 2.3 Make Blocklist Tracking and eligible Remove Tracking controls discoverable in Response Registry.
- [x] 2.4 Add explicit tracking-only/no-firewall copy and truthful disabled/terminal reasons.
- [x] 2.5 Preserve existing RBAC, protected-target rejection, audit logging, response outcomes, idempotency, refresh synchronization, and historical visibility.

## 3. MAC AI — Verification and Handoff Pass

- [x] 3.1 Add frontend tests for sole visible navigation, legacy normalization, landing preference recovery, discoverability, terminal records, and role restrictions.
- [x] 3.2 Run focused backend tests for list/add/remove contracts, canonical command idempotency, protected targets, audit logging, registry events, and tracking-only outcomes.
- [x] 3.3 Run affected App/Sidebar/Settings/Response Registry suites and `npm run build`.
- [x] 3.4 Perform dark-theme, keyboard/focus, explanatory-copy, desktop/narrow viewport, and practical visual verification.
- [x] 3.5 Produce a VM handoff naming the approved commit/artifact gate, sanitized classification evidence, exact supported removal path, before/after counts, and stop/rollback rules.
- [x] 3.6 Run `openspec validate consolidate-blocklist-response-registry-workflow --strict` and `git diff --check`.

## 4. VM AI — Read-Only Classification Pass (Completed)

- [x] 4.1 Confirm explicit VM authorization, clean `/home/jaden/siem-security-dashboard` worktree, and exact approved deployed commit SHA; stop on any mismatch.
  - Evidence: VM HEAD matched approved `origin/main` `4a5d821e443a483908909da506c0fb85cf89fa58`; deployed frontend/backend matched approved source.
- [x] 4.2 Locate all normalized `12.12.12.12` Blocklist/registry/outcome/audit references without exposing secrets or unrelated payloads.
  - Evidence: One `blocked_ips` row; registry + historical audit located; no pending queue/approval/playbook/dead-letter refs.
- [x] 4.3 Classify each match as active, expired, historical, removed, protected, or unknown and record sanitized IDs/statuses plus before counts.
  - Evidence: `blocked_ips.status=inactive`; `indicator_registry` disposition `removed`; not protected; API/DB agree.
- [x] 4.4 Verify the supported API/UI action is available and that no direct database deletion/update is planned.
  - Evidence: Supported Remove Tracking path remains the only removal contract; no direct SQL planned or performed. Action not applicable while inactive.
- [x] 4.5 Report classification and stop; read-only authorization does not permit removal.
  - Evidence: Classification reported; no mutation; no new target-related audit event created during verification.

## 5. VM AI — Supported Removal Pass (Not Applicable — Already Removed)

- [x] 5.1 Reconfirm clean tree, approved SHA, authorization, active/non-protected/unambiguous status, audit availability, and idempotency before mutation.
  - **Not applicable — already removed.** Prerequisite active tracking record does not exist (`status=inactive`, disposition `removed`). Mutation would be incorrect/unnecessary.
- [x] 5.2 Invoke the supported Remove Tracking workflow once; do not use direct SQL mutation and do not retry blindly.
  - **Not applicable — already removed.** No removal mutation executed in this close-out. Historical audit shows supported removal already occurred on 2026-04-28.
- [x] 5.3 Capture sanitized before/after target and unrelated-record counts, API/UI state, registry event, response outcome, and audit evidence.
  - **Satisfied by terminal-state verification (not a new mutation).** Read-only evidence: inactive Blocklist row, disposition `removed`, preserved historical audit; API/DB agree; unrelated pending work absent.
- [x] 5.4 Stop and report if any unrelated count changes, outcome claims firewall enforcement, or the supported command fails/returns unknown state.
  - **Satisfied by stop-condition path.** Terminal/inactive classification correctly blocked mutation; verification performed no-op safely.
- [x] 5.5 Record rollback readiness: history remains immutable and any re-add requires a separate authorized canonical command.
  - Evidence: Historical rows/audit retained. Any future re-add requires separately authorized canonical `block_ip` / Add Tracking — not part of this change.

## 6. MAC AI / VM AI — Global Stop Conditions

- [x] 6.1 Do not commit, push, deploy, access the VM, or mutate data without the corresponding explicit authorization.
- [x] 6.2 Never delete historical Blocklist, registry, outcome, or audit evidence and never edit tracked VM source.

Status: **Complete.** Mac implementation, VM read-only classification of `12.12.12.12`, and Phase 5 disposition (**Not applicable — already removed**) are resolved. No required mutation remains. Ready to archive.
