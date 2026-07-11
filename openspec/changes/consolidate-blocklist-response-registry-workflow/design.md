## Context

`sectionsConfig` exposes both Response Registry and Blocklist. `App.js` maps Blocklist to the same `ResponseRegistryPanel` with `blocklist_tracking`. Removal already flows through frontend service/API or the canonical Response Registry command, then `execute_response_command`, registry/blocklist persistence, response outcome, and audit logging. Historical rows are evidence, not disposable UI state.

## Goals / Non-Goals

**Goals:**

- **MAC AI:** Establish Response Registry as the only visible workspace for Blocklist tracking.
- **MAC AI:** Clarify and test the supported non-destructive removal workflow.
- **VM AI:** Define a gated classification/remediation runbook for `12.12.12.12` with sanitized evidence.

**Non-Goals:**

- Direct row deletion, firewall unblocking, bulk cleanup, data migration, new command semantics, or weakening protected-target/RBAC guards.
- Any VM access, deployment, or mutation during proposal/implementation without explicit authorization.

## Decisions

### 1. One parent, phased ownership

Use one change with MAC AI and VM AI phases because runtime classification accepts the exact source/UI contract delivered by the Mac phase. A separate VM child would duplicate acceptance criteria and could imply runtime work is independently safe before the UI/source handoff. VM tasks remain blocked on explicit deploy and mutation authorization.

### 2. Remove visible duplication, preserve compatibility

Remove `blocklist` from visible section configuration and Settings landing choices. Any stored legacy landing value or internal `handleNavigate("blocklist")` request SHALL normalize to Response Registry with `blocklist_tracking`. Do not create a second blocklist state or route.

### 3. Removal means tracking termination

The UI SHALL call the existing canonical `remove_tracking` behavior. Copy SHALL state: SIEM Blocklist tracking becomes inactive, an event/audit trail remains, and no firewall/provider/host change is claimed. Only active, authorized, non-protected records expose an enabled action. Terminal records remain readable.

### 4. Runtime classification precedes mutation

Future VM AI reads sanitized API/database state for the exact normalized IP and classifies every matching record as active, expired, historical, removed, protected, or unknown. It records IDs/status/counts without secrets. Mutation requires explicit authorization after classification, an approved deployed commit, clean VM, applicability, and a supported API/command path. Direct SQL deletion/update is forbidden.

### 5. Verification and rollback

Mac regression tests cover role visibility, legacy redirect, discoverability, idempotency, protected targets, audit/outcome contracts, and unrelated records. If a future supported removal occurs, rollback does not erase history; any re-add must be a separately authorized canonical command. Source rollback uses the previous frontend artifact/commit.

## Risks / Trade-offs

- [Bookmarks/stored landing break] → Normalize legacy `blocklist` values to the registry view.
- [“Remove” implies enforcement] → Use “Remove Tracking” plus explicit no-firewall explanatory text.
- [Duplicate active records/runtime ambiguity] → Classify all matches and stop before mutation if uniqueness/idempotency is unclear.
- [Production drift] → VM clean-tree and approved SHA gates; never edit tracked VM source.

## Migration / Deployment Order

1. **MAC AI:** implement/test source and create VM handoff; no migration.
2. User separately authorizes commit/push and frontend deployment.
3. **VM AI:** verify clean tree and exact approved SHA, deploy approved artifact if authorized, then perform read-only classification.
4. **VM AI:** only with separate mutation authorization, invoke the supported removal workflow once and verify counts/API/UI/audit evidence.

## Stop Conditions

- Dirty VM, wrong/unapproved SHA, unavailable canonical endpoint, ambiguous duplicates, protected target, terminal/non-active record, missing audit capability, or any unrelated row delta.
- Any request to delete history or imply firewall enforcement.

## Open Questions

The runtime classification of `12.12.12.12` is intentionally unknown until an approved VM read-only phase.

