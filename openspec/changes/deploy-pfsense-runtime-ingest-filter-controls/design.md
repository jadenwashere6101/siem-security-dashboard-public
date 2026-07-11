## Context

**Owner: VM AI. Runtime child of `add-pfsense-runtime-ingest-filter-controls`.** The Mac parent introduces a migration, backend policy/API/metrics, filterlog parser and listener accounting changes, detector integration, Administration UI, and a deployment handoff. The VM remains deployment/runtime only. Production pfSense forwarding must not begin until the full retained/dropped matrix and restartless controls are proven against the deployed commit.

## Goals / Non-Goals

**Goals:**

- Deploy the exact approved Mac commit from a clean VM.
- Prove migration, services, UI, defaults, overrides, filtering order, observability, and rollback.
- Establish a signed-off readiness gate before external pfSense configuration.

**Non-Goals:**

- Source edits, emergency hotfixes, commits, pushes, schema invention, or external pfSense changes.
- Load testing beyond bounded synthetic verification or ingesting real uncle traffic before approval.

## Decisions

1. **Stop on dirty or wrong commit.** Record `git status --short`, current/approved SHAs, branch, and remote. Any dirt or mismatch blocks deployment.
2. **Deploy backend before frontend.** Run migration dry-run, apply with the repository helper, verify backend/worker health, install/restart the pfSense listener from repository artifacts, then copy the Mac-built frontend output.
3. **Use synthetic documentation-range traffic.** Submit authenticated normalized payloads and listener fixtures using non-routable test addresses; avoid real external delivery or firewall mutation.
4. **Verify storage with before/after queries.** For every matrix row, record route/listener outcome and event-table delta. Filtered rows must have zero event/raw/alert/downstream delta; retained rows must have expected event and detector behavior.
5. **Prove exact restartless semantics.** Record service start timestamps/PIDs, change each setting through the UI/API, send the next event, verify changed behavior, and prove PIDs did not restart. Restore approved defaults afterward.
6. **Rollback without deleting evidence.** Revert source only through an approved prior commit, use documented migration compatibility, restore config rows, and pause external forwarding if rollback would re-enable unfiltered storage.

## Risks / Trade-offs

- [Synthetic events trigger automation] → use documentation IPs, approved test environment/mode, and confirm no real external provider/firewall effect.
- [Filtered events are confused with UDP loss] → test route and listener separately and reconcile counters.
- [Migration succeeds but UI/backend versions mismatch] → deploy in dependency order and verify API contract before frontend.
- [Rollback restores ingest-all behavior] → external forwarding stays disabled until either filtering is healthy or a safe upstream rule is in place.

## Migration Plan

1. Preflight clean tree, approved SHA, backups, current services, config, counters, schema ledger, and event counts.
2. Fetch/merge approved commit; run `deploy_backend_vm.sh --dry-run-migrations`, then normal deploy/apply.
3. Install/restart current pfSense listener service and verify sanitized effective configuration.
4. Deploy the exact Mac-built frontend artifact and verify Administration access.
5. Run default, override, failure-fallback, listener, DB-delta, detector, and restartless matrices.
6. Restore approved defaults, observe health/counters, and record readiness decision.
7. On failure, stop external forwarding, restore prior approved source/artifact/config using the runbook, verify services/health, and preserve logs/data.

## Open Questions

- None blocking; the VM AI must use the concrete commands and expected values supplied by the completed Mac handoff.
