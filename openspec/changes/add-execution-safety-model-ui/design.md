## Context

Current SOAR surfaces correctly enforce simulation-safe defaults and guarded
real-mode paths, but some copy still says things like "Simulation only" at too
broad a level. That can confuse reviewers into thinking the whole product is a
mock or that there is one global real/simulation toggle. The desired product
language is more precise: orchestration is real, integration execution is
guarded, and firewall remediation is intentionally dry-run only.

This change should also establish lightweight traceability conventions for key
files without flooding the codebase with noisy comments.

## Goals / Non-Goals

**Goals:**

- Clarify execution safety model in the UI without changing behavior.
- Make it obvious that workflows, approvals, dead letters, metrics, audit
  logging, rate limiting, and deduplication are real operational capabilities.
- Make it obvious that outbound integrations are adapter-specific and
  guard-controlled, not governed by one global UI toggle.
- Show a small capability matrix with examples:
  - alert ingestion -> real
  - orchestration/workflows -> real
  - approvals -> real
  - Slack/email/webhook -> guarded real-capable
  - firewall -> simulation-safe/dry-run only
- Add concise `SPEC-*` traceability comments to high-value safety and
  orchestration files.

**Non-Goals:**

- No backend execution semantic changes.
- No schema or migration changes.
- No new integration adapters.
- No VM/runtime actions.
- No new mutation controls.
- No broad App.js rewrite or frontend architecture change.
- No comment spam across low-value files.

## UI Design

### Safety explanation panel

Add a compact read-only panel, preferably reusable, with language like:

- "Simulation-Safe Execution" for the default execution posture.
- "Workflows, approvals, dead letters, metrics, and audit records are real
  operational platform behavior."
- "Outbound integrations are adapter-specific and guard-controlled."
- "Slack, Teams, email, and webhook adapters can be real-capable when required
  guards pass."
- "Firewall actions remain dry-run only; no live firewall execution path exists."

Preferred surfaces:

- SOC Command Center: near integration safety/worker health or as a compact
  operational safety panel.
- SOAR Integrations: near adapter status, emphasizing per-adapter guard state.
- Playbook execution detail: near the timeline header or execution metadata,
  explaining the execution context without implying the run is fake.

Optional compact reuse is acceptable if it avoids duplication and keeps the UI
small.

### Capability matrix

Render a compact table/card, not a large dashboard:

| Capability | Current Model | Operator Meaning |
| --- | --- | --- |
| Alert ingestion | Real | Events are stored and detected by the SIEM pipeline. |
| Orchestration | Real | Playbooks, worker leases, approvals, logs, and metrics are platform behavior. |
| Approvals | Real | Human gates pause and resume workflows through existing controls. |
| Slack/Teams/Email/Webhook | Guarded real-capable | Real sends require adapter guards, credentials, audit, rate limits, and dedup. |
| Firewall | Dry-run active | No real firewall mutation path exists in this spec lineage. |

The matrix should not imply there is a single switch for all integrations.

### Wording rules

Prefer:

- Simulation-Safe Execution
- Guarded Real Integration
- Real Integration Disabled
- Dry-Run Active
- Approval-Gated
- Real-Capable Adapter
- Guard failed closed

Avoid:

- fake mode
- fake execution
- simplistic "REAL vs SIMULATION" binary toggle language
- wording that says all adapters are simulated when some are guarded real-capable
- wording that says the whole product is simulation-only

## Traceability Tagging Strategy

Use small, high-signal comments near boundaries, not repeated comments on every
function.

Recommended format:

```python
# spec: SPEC-UI-004 / SPEC-INTEG-005 - concise safety boundary.
```

```javascript
// spec: SPEC-UI-004 - concise UI safety-model label/matrix boundary.
```

Guidelines:

- Add tags only where a future contributor is likely to change safety behavior.
- Prefer one comment per file or one comment per major boundary.
- Use existing spec IDs when the boundary is already owned by a prior spec.
- Use `SPEC-UI-004` for this execution safety UI/tagging cleanup.
- Do not tag generated files, tests unless useful, or low-risk display helpers.
- Do not add comments that merely restate obvious code.

## Target Files

Primary traceability targets:

- `integrations/base_integration.py`
- `integrations/slack_adapter.py`
- `integrations/teams_adapter.py`
- `integrations/email_adapter.py`
- `integrations/webhook_adapter.py`
- `integrations/firewall_adapter.py`
- `integrations/adapter_rate_limiter.py`
- `core/integration_audit.py`
- `core/dead_letter_store.py`
- `engines/playbook_step_executor.py`
- `engines/soar_playbook_worker.py`
- `routes/metrics_routes.py`
- `frontend/src/components/SocCommandCenter.js`
- `frontend/src/components/IntegrationStatusPanel.js`
- `frontend/src/components/SoarMetricsDashboard.js`
- `frontend/src/components/DeadLettersPanel.js`
- `frontend/src/components/PlaybookExecutionTimeline.js`

If `engines/soar_playbook_worker.py` is not the active worker file in the
current repo, tag the active worker/orchestration file instead, such as
`scripts/soar_playbook_worker_daemon.py` or the current worker engine module.

## Testing Strategy

- Add or update focused frontend tests for safety panel rendering, capability
  matrix labels, and absence of confusing "fake" wording.
- Update existing component tests only where wording changes require it.
- Backend tests should not be required for comments-only traceability tags.
- Run focused frontend suites for touched components and `npm run build`.
- Run `python3 -m py_compile` on touched Python files if comments are added
  there, to catch accidental syntax issues.

## Risks / Trade-offs

- Wording can become too verbose -> keep panel and matrix compact.
- Over-tagging can reduce readability -> tag only high-value safety boundaries.
- Existing tests may assert old copy -> update tests to assert the improved
  language.
- UI can overemphasize safety at the expense of demo flow -> place the panel
  where operators already look for execution/integration context.
- Confusing real-mode language can imply global enablement -> keep labels
  adapter-specific and capability-specific.

## Implementation Plan

1. Audit current UI copy in SOC Command Center, SOAR Integrations, Playbook
   execution timeline/detail, SOAR Metrics, and SOAR Operations.
2. Create a small reusable execution safety model component if duplication would
   otherwise appear across multiple surfaces.
3. Add the compact explanation panel and capability matrix to SOC Command
   Center, then reuse or compactly mirror it in Integrations and Playbook detail
   where it fits.
4. Update broad "Simulation only" wording to precise simulation-safe /
   guard-controlled language.
5. Add concise traceability tags to the target high-value files.
6. Update focused frontend tests for labels, matrix content, and role-safe
   rendering.
7. Run focused frontend tests, build, Python compile checks for touched Python
   files, `git diff --check`, and `git status --short`.

