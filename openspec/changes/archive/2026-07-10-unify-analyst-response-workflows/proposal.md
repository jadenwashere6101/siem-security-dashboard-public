## Why

**Owner: Mac AI.** Analyst actions currently produce inconsistent results across Dashboard alerts, playbooks, queues, approvals, Threat Hunt, incidents, source-IP context, and Blocklist views. The SIEM needs one truthful response workflow so every selected action has a durable outcome, provenance, synchronized UI state, and an obvious place to review it.

## What Changes

- Introduce a canonical response registry for IP dispositions: observed, monitored, escalated, pending, blocklist-tracked, rejected, failed, expired, and removed.
- Route every accepted `block_ip`, `monitor`, and escalation request through shared backend contracts with idempotency, protected-target validation, provenance, history, and canonical outcomes.
- Keep `block_ip` tracking-only with no firewall enforcement; make repeated requests converge on one active record while retaining every source relationship.
- Add a **Response Registry** sidebar workspace containing All, Monitoring, Blocklist Tracking, Escalated, Pending, Failed/Rejected, and History views; fold the existing Blocklist Manager into it.
- Correlate and deep-link alerts, incidents, playbooks, queue work, approvals, dead letters, source-IP context, Threat Hunt, Attack Map, and SOC Command Center.
- Make post-action responses and cross-view refreshes authoritative; disable visually locked controls and replace misleading “Escalate,” “Monitor,” and generic success behavior with truthful outcomes.
- Unify action validation and routing so deprecated/ambiguous `notify` and misrouted `enrich_context` actions cannot create new `unsupported_action` dead letters.
- Provide migration, tests, deployment instructions, and a VM-AI handoff for production migration and backlog remediation.

## Capabilities

### New Capabilities

- `canonical-indicator-response-registry`: Durable current disposition, event history, provenance, idempotency, expiry, and truthful enforcement semantics for analyst-selected indicators.
- `response-registry-workspace`: Analyst-facing Response Registry navigation, filters, detail/history, guarded actions, and integrated Blocklist management.
- `cross-workspace-response-correlation`: Deep links, contextual handoffs, lifecycle explanations, and mutation-driven synchronization across every analyst workspace.
- `canonical-action-vocabulary-routing`: One producer/validator/executor vocabulary and routing contract that prevents unsupported or misrouted SOAR actions and supports safe historical compatibility.

### Modified Capabilities

<!-- No existing base capability fully defines this end-to-end analyst workflow. -->

## Impact

Mac-owned scope includes PostgreSQL migrations, backend services/routes, action producers and executors, response outcome contracts, React navigation/components/services, tests, and deployment documentation. The change may replace the standalone Blocklist sidebar entry while preserving its API compatibility during migration. VM-owned execution remains in `vm-soar-runtime-recovery-parent`: deploy approved Mac changes, run migrations, smoke-test production, then classify the existing `unsupported_action` dead-letter cohorts and retry/dismiss them safely. No firewall enforcement, VM source edit, commit, push, or deployment is authorized by this proposal.
