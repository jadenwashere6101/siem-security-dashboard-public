## Context

The canonical response-outcome model already records mode, state, `external_executed`, `simulated`, summaries/reason codes, actors, and related resource IDs. Queue manual run is intentionally simulation-only and uses `SimulationExecutor`. Alert, queue, playbook, delivery, approval, and metrics read models draw from different tables and must remain distinct. Current UI badges compress this evidence too aggressively.

## Goals / Non-Goals

**Goals:**

- **MAC AI:** Make canonical labels explainable and traceable without changing their truth.
- **MAC AI:** State exactly what manual queue simulation processes and cannot do.
- **MAC AI:** prove Metrics endpoint-to-table ownership and surface partial failures honestly.
- **VM AI:** reconcile representative production chains and metric snapshots read-only.

**Non-Goals:**

- Global text replacement, canonical writer/backfill changes, enabling Teams, enabling real firewall actions, sending notifications, retrying queues/dead letters, or mutating production.
- Treating tracking-only, read-only, pending approval, blocked, failed, skipped, unknown, or real execution as simulation.

## Decisions

### 1. Canonical outcomes remain authoritative

`ResponseOutcomeBadge` remains the compact label. An evidence summary/detail SHALL derive only from canonical fields and linked read models, showing mode, execution/external-effect state, reason/summary, and related identifiers when available. Missing evidence is “Unknown” or “Not recorded,” never inferred as real. Legacy fields may be displayed as provenance but may not override canonical truth.

Terminology:

- **Real executed:** canonical real mode plus confirmed external effect.
- **Simulated:** simulation mode/no real external effect.
- **Tracking-only:** durable SIEM record only, no enforcement.
- **Read-only/observed:** retrieved or observed state without action.
- **Pending approval:** requested effect not yet authorized/executed.
- **Blocked/rejected/failed/skipped:** terminal or guarded non-success with reason.
- **Unknown:** evidence insufficient; never promoted to success.

### 2. Explain the manual simulation boundary before action

Queue copy SHALL state that the bounded admin endpoint claims pending queue rows, evaluates them with `SimulationExecutor`, may update queue/outcome lifecycle records, and performs no real provider, notification, firewall, host, or external integration effect. Confirmation/help text and result copy SHALL distinguish internal state mutation from external effect.

### 3. Evidence uses links, not duplicated joins in the browser

Reuse existing related IDs and navigation contracts. If an affected API omits already-stored canonical evidence, allow the smallest additive read-model serialization change with RBAC unchanged. Do not add browser-side speculative joins or a second outcome vocabulary. A schema/migration need is a stop condition.

### 4. Metrics map explicitly to source tables

Document each UI section → service → endpoint → query/table mapping: playbook executions/outcomes, dead letters, notification delivery attempts, incidents, approvals, worker/runtime state, and queue actions. UI SHALL preserve per-section error states and last-refreshed time; it SHALL not imply a failed source returned zero.

### 5. One parent, phased ownership

The VM verification phase accepts the same outcome and metrics contracts built by MAC AI, is read-only, and has no independently deployable feature. Keeping one parent prevents a verification child from drifting or being run before its approved source commit.

### 6. Production verification is sampled and read-only

After explicit authorization, clean-tree and approved-SHA checks, VM AI selects representative simulated, real-capable, pending/blocked/failed, and tracking-only records where present. It traces alert → outcome → queue → execution → delivery → integration mode using sanitized IDs/statuses/counts. Metrics are compared to bounded source queries at one timestamp. No action endpoints are called.

## Risks / Trade-offs

- [Information overload] → Compact badge plus expandable evidence, prioritizing mode/effect/reason/links.
- [Legacy contradiction] → Canonical fields win; surface contradiction as unknown/data-quality evidence and stop remediation.
- [Verification query races] → Record a bounded snapshot timestamp and tolerances for rows created during sampling.
- [Sensitive payload exposure] → IDs/statuses/counts only; redact secrets, endpoints, message bodies, and personal data.

## Migration / Deployment / Rollback

1. **MAC AI:** audit vocabulary/read models, implement evidence/copy/tests, build, and create read-only VM handoff.
2. Original Mac pass expected no migration. **Correction pass:** additive CHECK expansion only via `migrations/0017_approval_expired_reason_code.sql` to allow `approval_expired` (no historical rewrite).
3. Future deployment requires explicit commit/push/deploy authorization; deploy **backend + migration first**, then frontend (reason-code + legacy-status presentation).
4. **VM AI:** after explicit read-only authorization, verify clean approved SHA and capture sanitized traces/snapshots without mutation.
5. Rollback deploys prior source/artifact; no data rollback is needed for presentation-only/read-only verification. Reverting migration is optional only if the CHECK must be narrowed again (new rows with `approval_expired` would then be blocked).

## Stop Conditions

- Stop if a requested label would contradict canonical data or require inferring real execution.
- Stop if work would enable Teams/firewall real mode, expose secrets, send notifications, retry work, mutate data, or require a migration.
- VM AI stops on dirty tree, wrong SHA, unavailable source tables, contradictory identifiers, or any tool/action that is not demonstrably read-only.

## Open Questions

Specific production records and availability of each outcome class remain unknown until the authorized VM phase; absence is reported, not manufactured.

