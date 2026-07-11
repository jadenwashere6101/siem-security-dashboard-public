## 1. MAC AI — Source and Contract Audit Pass

- [ ] 1.1 Reconfirm UI → handler/service → `/blocked-ips`/canonical command → response-command service → blocklist/registry/outcome/audit tables → synchronized UI flow.
- [ ] 1.2 Inventory every `blocklist` section ID, landing preference, deep link, service call, legacy route, protected-target check, RBAC decorator, audit event, and idempotency key.
- [ ] 1.3 Confirm no schema/migration or new removal endpoint is required and document exact VM handoff queries/endpoints without secret output.

## 2. MAC AI — Consolidation Implementation Pass

- [ ] 2.1 Remove the standalone visible Blocklist entry and update section-order/visibility tests.
- [ ] 2.2 Normalize stored/default/internal legacy `blocklist` destinations to Response Registry `blocklist_tracking`.
- [ ] 2.3 Make Blocklist Tracking and eligible Remove Tracking controls discoverable in Response Registry.
- [ ] 2.4 Add explicit tracking-only/no-firewall copy and truthful disabled/terminal reasons.
- [ ] 2.5 Preserve existing RBAC, protected-target rejection, audit logging, response outcomes, idempotency, refresh synchronization, and historical visibility.

## 3. MAC AI — Verification and Handoff Pass

- [ ] 3.1 Add frontend tests for sole visible navigation, legacy normalization, landing preference recovery, discoverability, terminal records, and role restrictions.
- [ ] 3.2 Run focused backend tests for list/add/remove contracts, canonical command idempotency, protected targets, audit logging, registry events, and tracking-only outcomes.
- [ ] 3.3 Run affected App/Sidebar/Settings/Response Registry suites and `npm run build`.
- [ ] 3.4 Perform dark-theme, keyboard/focus, explanatory-copy, desktop/narrow viewport, and practical visual verification.
- [ ] 3.5 Produce a VM handoff naming the approved commit/artifact gate, sanitized classification evidence, exact supported removal path, before/after counts, and stop/rollback rules.
- [ ] 3.6 Run `openspec validate consolidate-blocklist-response-registry-workflow --strict` and `git diff --check`.

## 4. VM AI — Future Read-Only Classification Pass (Explicit Authorization Required)

- [ ] 4.1 Confirm explicit VM authorization, clean `/home/jaden/siem-security-dashboard` worktree, and exact approved deployed commit SHA; stop on any mismatch.
- [ ] 4.2 Locate all normalized `12.12.12.12` Blocklist/registry/outcome/audit references without exposing secrets or unrelated payloads.
- [ ] 4.3 Classify each match as active, expired, historical, removed, protected, or unknown and record sanitized IDs/statuses plus before counts.
- [ ] 4.4 Verify the supported API/UI action is available and that no direct database deletion/update is planned.
- [ ] 4.5 Report classification and stop; read-only authorization does not permit removal.

## 5. VM AI — Future Supported Removal Pass (Separate Explicit Mutation Authorization Required)

- [ ] 5.1 Reconfirm clean tree, approved SHA, authorization, active/non-protected/unambiguous status, audit availability, and idempotency before mutation.
- [ ] 5.2 Invoke the supported Remove Tracking workflow once; do not use direct SQL mutation and do not retry blindly.
- [ ] 5.3 Capture sanitized before/after target and unrelated-record counts, API/UI state, registry event, response outcome, and audit evidence.
- [ ] 5.4 Stop and report if any unrelated count changes, outcome claims firewall enforcement, or the supported command fails/returns unknown state.
- [ ] 5.5 Record rollback readiness: history remains immutable and any re-add requires a separate authorized canonical command.

## 6. MAC AI / VM AI — Global Stop Conditions

- [ ] 6.1 Do not commit, push, deploy, access the VM, or mutate data without the corresponding explicit authorization.
- [ ] 6.2 Never delete historical Blocklist, registry, outcome, or audit evidence and never edit tracked VM source.
