## 1. Mac AI — Phase 1 Contract Baseline

- [x] 1.1 Inventory every producer, route, queue, playbook step, executor, and UI control for `block_ip`, `monitor`, `flag_high_priority`/escalation, `notify`, and `enrich_context`
- [x] 1.2 Define the canonical action vocabulary, owning executor, supported modes, aliases, deprecations, and validation errors in one source-controlled registry
- [x] 1.3 Add failing contract tests proving bare ambiguous `notify` is rejected before enqueue and `enrich_context` cannot enter the legacy response-action queue
- [x] 1.4 Decide and document the minimum durable escalation policy and default monitoring expiry/renewal policy
- [x] 1.5 Define API schemas for canonical commands, outcomes, affected-resource invalidation keys, registry records, events, list filters, and detail responses

## 2. Mac AI — Phase 1 Registry Data Foundation

- [x] 2.1 Add versioned migrations for normalized indicator registry identities, append-only response events, provenance relationships, and required uniqueness/foreign-key/index constraints
- [x] 2.2 Add migration rollback behavior that preserves pre-existing Blocklist, response outcome, alert, incident, queue, approval, and playbook data
- [x] 2.3 Implement registry persistence APIs for identity upsert, transactional event append, current-disposition derivation, expiry, pagination, filters, and history
- [x] 2.4 Implement evidence-safe backfill tooling that imports only provable historical relationships and labels inferred/unknown provenance
- [x] 2.5 Add database tests for concurrency, duplicate IP normalization, idempotent events, foreign-key integrity, pagination, expiry, and rollback

## 3. Mac AI — Phase 1 Canonical Response Commands

- [x] 3.1 Implement a shared response command service enforcing RBAC, protected-target checks, validation, idempotency, atomic source mutation, canonical outcome, registry event, and audit logging
- [x] 3.2 Implement idempotent tracking-only `block_ip` that creates or reuses one active Blocklist record and returns registry/outcome/Blocklist identifiers
- [x] 3.3 Implement durable monitor/watch dispositions with reason, origin, ownership, start, expiry, renewal, and history
- [x] 3.4 Implement durable internal escalation according to the approved incident/priority/assignment policy and prevent log-only success
- [x] 3.5 Adapt manual alert and direct Blocklist routes to the shared service while preserving compatible response fields
- [x] 3.6 Adapt playbook `block_ip` and approved queue/approval paths to the shared service without enabling firewall enforcement
- [x] 3.7 Route `enrich_context` exclusively through the playbook read-only executor and remove or guard every legacy producer path
- [x] 3.8 Replace or reject bare `notify` producers and add actionable validation that identifies required provider-specific actions
- [x] 3.9 Return canonical outcome, registry record/event IDs, specialized resource IDs, idempotency result, and affected-resource keys from every mutation endpoint
- [x] 3.10 Add backend unit, integration, security, concurrency, and end-to-end tests for all command origins and failure states

## 4. Mac AI — Phase 2 Response Registry Workspace

- [x] 4.1 Add Response Registry to sidebar configuration and role/visibility tests
- [x] 4.2 Build registry service clients and workspace shell with All, Monitoring, Blocklist Tracking, Escalated, Pending, Failed/Rejected, and History views
- [x] 4.3 Implement paginated search/filter/sort for indicator, disposition, requested action, outcome, enforcement, risk, origin, actor, related resource, and time range
- [x] 4.4 Implement registry detail with current state, explicit enforcement statement, complete history, provenance, related counts, and deep links
- [x] 4.5 Integrate existing Blocklist add/list/expiry/unblock behavior into Blocklist Tracking with canonical outcomes and history
- [x] 4.6 Add guarded Monitor, Stop Monitoring, Track in Blocklist, Remove Tracking, Escalate, note, and expiry controls using shared command contracts
- [x] 4.7 Redirect the legacy Blocklist sidebar/deep link to the Registry Blocklist Tracking view after compatibility tests pass
- [x] 4.8 Add responsive, accessibility, viewer/analyst/super-admin, empty/error/loading, and truthful-copy frontend tests

## 5. Mac AI — Phase 3 Cross-Workspace Correlation

- [ ] 5.1 Replace every duplicated alert-action rendering with one permission-correct shared component and disable locked controls before requests are sent
- [ ] 5.2 Connect Dashboard, alert detail/expanded row, Threat Hunt, Attack Map, incidents, Source-IP Context, SOC Command Center, playbooks, queue, and approvals to canonical commands or contextual handoffs
- [ ] 5.3 Implement targeted mutation invalidation for alerts, response logs, registry/blocklist, IP context, incidents, playbooks, queue, approvals, metrics, and command-center summaries
- [ ] 5.4 Make SOC attention items navigate to filtered authoritative views for approvals, dead letters, executions, notifications, queue pressure, and integrations
- [ ] 5.5 Make incident alert IDs, registry relationships, queue/approval/playbook identifiers, and source-IP summaries deep-linkable with selection/filter/back-navigation context
- [ ] 5.6 Replace generic action success and vague legacy response status presentation with actual canonical outcomes and created/reused resource identifiers
- [ ] 5.7 Add independent alert/incident lifecycle warnings and review handoffs without automatically coupling status mutations
- [ ] 5.8 Add browser-level workflow tests proving equivalent actions from every supported surface converge on the same registry/Blocklist state and synchronized UI

## 6. Mac AI — Migration and VM Handoff

- [ ] 6.1 Run migration dry-run/upgrade/rollback tests plus focused and full backend/frontend test suites
- [ ] 6.2 Verify no test path performs firewall or host enforcement and Teams remains disabled unless separately configured
- [ ] 6.3 Produce a historical `unsupported_action` classifier/report for `notify` and `enrich_context` with safe retry, dismiss, and escalation criteria
- [ ] 6.4 Document VM deployment order: clean-tree check, fetch/merge after authorization, migration dry-run/apply, backend/worker restart, health checks, frontend build deployment, and rollback
- [ ] 6.5 Document production smoke tests for each action origin, idempotent Blocklist convergence, watch/escalation state, deep links, synchronized views, and absence of new unsupported-action cohorts
- [ ] 6.6 Hand deployment and dead-letter remediation to `vm-soar-runtime-recovery-parent`; do not edit VM source, commit, push, or deploy without separate authorization

## 7. VM AI — Existing Runtime Parent Follow-Through

- [ ] 7.1 Execute only through `vm-soar-runtime-recovery-parent` after the approved Mac implementation is committed, pushed, and ready; do not create a competing VM feature spec
- [ ] 7.2 Confirm the VM worktree is clean, deploy through the documented source-of-truth workflow, run migrations, restart affected services, deploy the frontend build, and capture sanitized smoke evidence
- [ ] 7.3 Recount and classify the audited 82-open `unsupported_action` records for `notify`/`enrich_context` and the one retrying record using current live values rather than assuming counts are unchanged
- [ ] 7.4 Canary-retry only relevant idempotent records corrected by the deployed routing change; dismiss or escalate obsolete, ambiguous, unsafe, and duplicate-prone records with reasons and preserved history
- [ ] 7.5 Observe production for new `unsupported_action` creation, verify the cohort no longer grows, and return any continuing producer evidence to the Mac AI
