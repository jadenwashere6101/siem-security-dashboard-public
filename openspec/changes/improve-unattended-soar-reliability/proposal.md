## Why

The operational-reliability audit conducted after the SIEM's first sustained real pfSense event stream (this session) found that SOAR's approval-expiration path is fail-closed by design but operationally hostile to being unattended: `_process_awaiting_approval_execution` routes every denied/expired approval with no `on_denied`/`on_expired: "branch"` step config through the same `_finalize_failed` choke point used for genuine adapter/worker/integration failures, which unconditionally sets `playbook_executions.status = 'failed'` and unconditionally calls `capture_failed_execution_dead_letter`. Because `classify_dead_letter_retryable` hard-denies retry for `approval_expired`/`approval_denied` failure classes, every containment playbook left unattended past its 15–30 minute approval window becomes a **permanent, non-retryable dead letter indistinguishable from a real bug**, growing linearly with unattended time. Separately, the "SOAR Queue" nav section is the legacy response-action queue, frozen by the already-recorded `soar-automation-path-consolidation-decision` — but nothing in the UI says so, so an idle queue reads as broken automation rather than an intentionally retired path. And "SOAR Operations" (the nav section meant to be the operational home) today renders only the dead-letter list — there is no single place to see what's running, what's waiting on a human, and what actually needs engineering attention.

None of this is a security or detection problem — it is an interpretability and lifecycle-modeling gap.

## What Changes

- Add a new, code-only terminal `playbook_executions` status for "approval resolved to denied/expired with no fallback configured" — distinct from `failed` (genuine execution/adapter/worker/integration errors), `abandoned` (manual operator stop), and `success`. Fail-closed behavior is unchanged: no protected action executes on this path today or after this change.
- Stop creating a dead-letter row for this specific, expected terminal case going forward. Dead letters remain reserved for genuine failures. The approval's own history (`approval_requests.status`, already `expired`/`denied`) and the existing outcome-event ledger remain the permanent audit trail — nothing about approval history is deleted or altered.
- Add a small number of read-only, aggregation-only backend endpoints (reusing existing list/store functions) so the dashboard can show running playbooks, pending approvals, recent expired/denied outcomes, genuine failures, and actionable dead letters without five separate manual queries.
- Extend the existing "SOAR Operations" section with a compact operational summary (not a new analytics dashboard) and add a small frozen-queue banner to the existing "SOAR Queue" section.
- Define, document, and (where safe) tool a non-destructive review path for the existing backlog of `approval_expired`/`approval_denied` dead letters, reusing the existing single-row dismiss endpoint and audit trail — no bulk deletion, no silent mutation.

## Capabilities

### New Capabilities
- `improve-unattended-soar-reliability`: approval-expiration terminal-state lifecycle, dead-letter classification for expected vs. genuine outcomes, and SOAR operational-visibility UI for unattended operation.

### Modified Capabilities
- (none) — this does not modify `soar-automation-path-consolidation-decision`, `pfsense-firewall-detections-soar`, `pfsense-detection-quality-and-analyst-experience`, or any other existing spec. It reuses the frozen-queue decision as a fact, not a change target.

## Impact

- **Affected code later:** `engines/playbook_step_executor.py` (`_process_awaiting_approval_execution`'s denied/expired branch), `core/playbook_store.py` (new `set_playbook_execution_not_actioned`, extended `_VALID_EXECUTION_STATUSES`/`_TERMINAL_EXECUTION_STATUSES`), a small number of new read-only route(s) for the operational summary, `frontend/src/components/SocCommandCenter.js`/`DeadLettersPanel.js`/`SoarQueuePanel` area for the UI additions, and focused tests.
- **Affected APIs later:** additive, read-only summary endpoint(s) only; no existing endpoint's contract changes. `POST /dead-letters/<id>/dismiss` (existing) is reused, not changed, for backlog review.
- **Affected systems now:** none. Writing this proposal/design/tasks/spec makes no changes under `engines/`, `core/`, `routes/`, `migrations/`, `frontend/`, or `tests/`, does not touch the VM, and performs no runtime validation.
- **Dependencies:** builds on already-implemented, already-recorded decisions (`soar-automation-path-consolidation-decision`, the existing approval/dead-letter/playbook-execution stores) — no unimplemented spec is a prerequisite.
- **Migrations:** none assumed. `playbook_executions.status` is `VARCHAR(30)` with no `CHECK` constraint (verified against `schema.sql`), so a new status value is a pure application-code change. `soar_dead_letters.status` *does* have a `CHECK` constraint, but this proposal's design avoids needing a new dead-letter status value by not creating a dead-letter row for the expected-expiration case at all — see `design.md` for the alternative that would require a migration, explicitly not chosen here.
