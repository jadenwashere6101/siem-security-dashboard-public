## Context

**Implementation owner: Mac AI. Deployment/backlog owner: VM AI via `vm-soar-runtime-recovery-parent`.** The current system has multiple independently evolved paths for alert actions, playbook steps, response queue work, approvals, direct Blocklist mutations, Threat Hunt, and source-IP investigation. Manual alert `block_ip` creates tracking state, while playbook and queue paths do not consistently do so; `monitor` and `flag_high_priority` primarily create logs despite labels implying durable workflows. Mutation responses and refetch behavior leave related screens stale. Producers can also emit `notify` or route `enrich_context` to executors that reject them, creating `unsupported_action` dead letters.

## Goals / Non-Goals

**Goals:**

- Give every accepted indicator response one canonical current disposition and append-only history.
- Make blocklist tracking idempotent and consistently reachable from all authorized surfaces.
- Make monitoring and escalation durable internal SIEM workflows rather than unexplained no-ops.
- Create a Response Registry that replaces fragmented indicator lists without losing the existing Blocklist contract.
- Make navigation, post-mutation synchronization, authorization feedback, and lifecycle relationships analyst-coherent.
- Prevent new unsupported-action dead letters and provide a safe VM handoff for historical backlog cleanup.

**Non-Goals:**

- Real firewall/host enforcement, Teams enablement, or promotion of any external integration.
- Automatically resolving incidents when alerts resolve, or vice versa.
- Editing source on the VM, deploying, committing, or pushing without separate authorization.
- Blindly retrying historical dead letters.

## Decisions

1. **Use a registry plus events, not three isolated lists.** A canonical indicator record stores normalized type/value and derived current disposition. Append-only events store requested action, outcome, actor, originating surface, timestamps, reason, expiry, and links to alert/incident/playbook/queue/approval/dead-letter/outcome records. This supports future domains, hashes, URLs, users, and devices while initially enabling IPs.

2. **Keep operational source tables authoritative.** `blocked_ips`, approvals, playbook executions, and incidents retain their specialized semantics. The registry correlates them and exposes current state; it does not collapse every lifecycle into one ambiguous status.

3. **Centralize response commands.** A backend command service validates target/action/RBAC/protected targets, applies idempotency, performs the internal mutation, appends canonical outcome and registry events in one transaction, and returns the resulting resource IDs. Existing routes become adapters to this service during compatibility migration.

4. **Define truthful action semantics.** `block_ip` means SIEM Blocklist tracking only. `monitor` creates an active, expirable watch disposition. `flag_high_priority` becomes internal escalation tied to priority/incident/assignment policy; until that mutation succeeds it cannot report escalation success. Real external execution remains a separate outcome dimension.

5. **Separate requested action from actual outcome.** Pending, awaiting approval, rejected, failed, tracking-only, monitored, escalated, expired, removed, simulation, and real external execution are distinct fields/events. A UI label never infers success from the button clicked.

6. **Canonicalize the action vocabulary at definition time.** Producers, playbook validation, queue enqueueing, worker dispatch, and registry presentation share one registry of actions and owning executor. Bare `notify` is rejected with actionable validation unless a deterministic migration alias is explicitly defined. `enrich_context` routes only to the playbook read-only executor, never the legacy response-action worker.

7. **Synchronize by affected resources.** Successful mutation responses contain canonical outcome, registry record/event IDs, and affected resource keys. A shared frontend invalidation layer refreshes alerts, registry/blocklist, source-IP context, incidents, playbooks, queue, approvals, metrics, and command-center data as applicable.

8. **Replace Blocklist navigation gradually.** Response Registry initially embeds/reuses Blocklist functions and preserves `/blocked-ips` compatibility. After deep links and tests pass, the standalone sidebar item redirects to the Registry’s Blocklist Tracking view rather than disappearing abruptly.

## Risks / Trade-offs

- [Registry duplicates existing state] → derive specialized details from source tables, enforce foreign keys/idempotency, and test reconciliation.
- [Concurrent actions create duplicate active records] → database uniqueness plus transactional upsert and append-only provenance.
- [Escalation semantics require product policy] → encode a minimal internal handoff contract and expose policy configuration; never report success for a log-only action.
- [Cross-view refetch becomes expensive] → invalidate targeted resources, debounce aggregate refreshes, and keep read models paginated.
- [Historical data is ambiguous] → backfill only provable relationships, label inferred provenance, and never manufacture success.
- [Retrying fixed dead letters duplicates work] → VM AI uses canary cohorts and idempotency checks after deployment.

## Migration Plan

1. **Mac Phase 1 – Foundation:** add migrations, action vocabulary, canonical command service, registry/event APIs, idempotent Blocklist tracking, monitoring/escalation contracts, compatibility adapters, and backend tests.
2. **Mac Phase 2 – Registry:** build Response Registry, embed Blocklist management, add filters/detail/history/actions, redirect legacy navigation, and add frontend tests.
3. **Mac Phase 3 – Correlation:** connect all analyst surfaces, add deep links and resource invalidation, fix locked controls/messages/lifecycle explanations, and run end-to-end tests.
4. **VM deployment:** after authorized commit/push, verify clean VM, deploy source, run migration dry-run/apply, restart services, deploy frontend build, and execute smoke tests.
5. **VM backlog:** classify `unsupported_action` dead letters by `notify` and `enrich_context`, canary retry only valid corrected work, dismiss obsolete/unsafe records with reasons, and verify no new cohort growth.
6. Rollback UI/routes first while retaining additive registry tables; stop new registry writes behind a compatibility flag if necessary. Never delete operational or registry history during rollback.

## Open Questions

- Should escalation always create an incident, or update an existing incident/alert priority when present?
- What default duration and renewal rules should monitoring use?
- Should direct Blocklist additions require a reason and expiry policy?
- Can any historical bare `notify` payload be deterministically mapped to a provider, or must all be rejected/dismissed?
