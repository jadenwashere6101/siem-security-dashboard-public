# Design: SOAR Simulation Circuit Breaker Controls

## Proposed architecture
Add an explicit operator control layer for simulation-mode integration circuit breakers. Controls should operate only on circuit breaker state and metadata. They must not execute adapters, run playbooks, enqueue SOAR queue work, replay failed executions, or contact external services.

Recommended control actions:
- Manual reset to `closed`.
- Manual force-open.
- Manual enable `half_open` probe.

All controls should be super-admin-only, audited, simulation-only, and fail-closed.

## Candidate API shape
Use the existing integration route area if that matches current project conventions. Example endpoints:

```http
POST /integrations/circuit-breakers/<adapter_name>/reset
POST /integrations/circuit-breakers/<adapter_name>/force-open
POST /integrations/circuit-breakers/<adapter_name>/enable-half-open
```

Alternative: use one action endpoint if the project prefers a compact route:

```http
POST /integrations/circuit-breakers/<adapter_name>/action
```

with a body such as:

```json
{
  "action": "force_open",
  "reason": "investigating repeated webhook simulation failures"
}
```

Either shape is acceptable if it follows existing auth, rate-limit, audit, and JSON response patterns.

## Manual reset to closed
Manual reset should set a breaker to `closed` only after a super-admin explicitly requests it. It should:
- Require a reason string where local API conventions support it.
- Reset `consecutive_failures` to zero.
- Clear `cooldown_until` or mark it inactive.
- Record `last_manual_action`, `last_manual_action_by`, and `last_manual_action_at` if metadata supports it.
- Write an audit event.
- Return updated breaker state.

Reset must not:
- Run a half-open probe.
- Retry failed playbook executions.
- Resume stale executions.
- Call adapter execution code.
- Contact external services.

If adapter state is invalid or restart-ambiguous, reset may be allowed only if the response clearly records that the operator manually accepted the reset. Otherwise, fail closed and require force-open or explicit probe enablement.

## Manual force-open
Force-open should let a super-admin place an adapter in `open` state immediately. It should:
- Set state to `open`.
- Set or preserve `cooldown_until` using a conservative default or operator-specified bounded value.
- Preserve failure counters unless the design explicitly records separate manual metadata.
- Record a reason and audit event.
- Return updated breaker state.

Force-open is containment, not execution. It must block adapter-backed simulated calls until reset or half-open probe enablement allows recovery.

## Manual enable half-open probe
Half-open enablement should prepare a single bounded recovery probe. It should:
- Require state to be `open` or otherwise explicitly eligible.
- Respect cooldown unless the API intentionally supports a super-admin override with reason.
- Set state to `half_open`.
- Mark that one probe is allowed.
- Record the operator, reason, and timestamp.
- Write an audit event.
- Return updated breaker state.

Enablement alone must not execute the probe. The actual probe should occur only through an explicit follow-up operator action or the next explicit manual simulation execution path, depending on the existing circuit breaker implementation. The UI and API response must make this distinction clear.

Probe success may close the breaker; probe failure should reopen it and record a cooldown. Both outcomes should be auditable if they are triggered by operator action.

## Audit logging expectations
Every breaker control action should write an immutable audit event. The audit payload should include:
- Adapter name.
- Previous state.
- New state.
- Action name.
- Actor user ID or username.
- Reason or note when provided.
- Timestamp.
- Cooldown or probe metadata changes.
- Request correlation information if existing audit helpers support it.

Audit logging failure should fail closed unless existing project audit behavior has a clear standard for best-effort audit writes. Do not silently perform breaker state changes without an audit trail.

## Auth and authorization
- Control endpoints are super-admin-only.
- Analyst users retain read-only visibility through existing integration status UI/API if that is already allowed.
- Viewer users remain denied following existing integration status conventions.
- Unauthenticated users receive existing unauthorized behavior.

No role should be able to use breaker controls to execute playbooks, approve gates, retry executions, or call adapters.

## UI visibility expectations
The integration status UI should remain operator-visible and simulation-first. It should show:
- Current breaker state.
- Whether the state was automatic or manually set.
- Last manual action and timestamp when available.
- Cooldown status.
- Whether a half-open probe is enabled.
- Clear simulation-only notice.
- Super-admin-only controls for eligible actions.
- Disabled or hidden controls for analysts/viewers according to existing role patterns.

Controls should use explicit labels and confirmation affordances where actions affect recovery state, especially force-open and reset-to-closed. UI copy must not imply real Slack, email, webhook, firewall, blocklist, or external remediation occurred.

## Safe handling of stale/open states
Stale or open breaker states should remain fail-closed until an explicit operator action changes them. A stale `open` state may be reset, force-opened again, or prepared for half-open probing by a super-admin, but none of those actions should replay prior executions.

Invalid or unknown breaker state should:
- Be visible to operators.
- Deny adapter-backed execution.
- Prefer force-open or explicit reset with audit over silent repair.
- Never transition automatically on page load, status read, metrics read, or server restart.

## Restart-safe behavior
Restart behavior must be documented and visible. If breaker state is persisted, controls should read and update persisted state transactionally. If breaker state is in memory, the status API and UI should clearly report reset or unknown state after restart.

No hidden state transitions should occur during app startup. Startup should not auto-close open breakers, auto-enable half-open probes, replay adapter calls, or heal stale state without an explicit operator action.

## Interaction with playbook execution states
Breaker controls operate on adapter availability, not execution state. They must not mutate existing playbook executions.

Safe interactions:
- `pending`: remains pending; breaker controls do not execute it.
- `running`: breaker controls do not resume or stop it directly.
- `awaiting_approval`: breaker controls do not bypass approval.
- `failed`: remains failed unless existing explicit playbook retry controls are used separately.
- `permanently_failed`: remains terminal and is not resurrected by breaker reset.
- `abandoned`: remains terminal.

If a future manual retry occurs after breaker reset, it must use existing playbook retry semantics and preserve immutable execution history.

## Immutable execution history
Breaker controls must not rewrite `steps_log`, terminal statuses, attempt counters, or historical execution rows. They may create audit records and update breaker state only. If an operator needs to retry a playbook after breaker recovery, that remains a separate explicit playbook execution control path.

## Safety boundaries
- Simulation-only.
- Fail-closed.
- Operator-visible.
- Bounded/manual recovery only.
- Restart-safe behavior clearly documented.
- No hidden state transitions.
- No autonomous retries.
- No automatic replay.
- No daemon or scheduler behavior.
- No real outbound calls.
- No enabling `INTEGRATION_MODE=real`.
- No Redis/Celery/RQ migration.
- No queue redesign.
- No background healing.
- No firewall or blocklist mutation.
- No `blocked_ips` mutation.
- No ingest, detection, or correlation changes.
- No subprocess execution.
- No external API dependencies.

## Test strategy
Add backend and frontend tests that verify:
- Unauthenticated control requests are rejected.
- Analyst/viewer control requests are forbidden.
- Super-admin can manually reset an eligible breaker to `closed`.
- Super-admin can manually force-open a breaker.
- Super-admin can enable `half_open` probe eligibility without executing the probe.
- Every successful control writes an audit event.
- Invalid adapter names fail safely.
- Invalid or unknown breaker state fails closed.
- Read-only status requests do not mutate breaker state.
- Controls do not call adapter execution methods.
- Controls do not run playbooks, retry executions, resume approvals, or enqueue queue work.
- Controls do not mutate `blocked_ips`.
- Controls do not make network or subprocess calls.
- UI shows state and super-admin-only controls without implying real execution.
- Existing playbook execution state tests still pass.

## Risks and stop conditions
- Stop if controls require real outbound calls or external API checks.
- Stop if controls enable `INTEGRATION_MODE=real`.
- Stop if controls can trigger replay, retry, execution, approval bypass, or adapter calls.
- Stop if status reads or page loads mutate state.
- Stop if audit logging cannot be made reliable enough for state changes.
- Stop if implementation requires queue redesign, Redis/Celery migration, daemon behavior, or ingest/detection/correlation changes.
