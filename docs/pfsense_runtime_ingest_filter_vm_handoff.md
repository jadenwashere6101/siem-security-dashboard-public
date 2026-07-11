# pfSense Runtime Ingest Filter VM Handoff

Owner: VM AI after explicit deployment authorization. This document does not authorize deployment, commit, push, production mutation, or external pfSense forwarding.

## Approval and clean-tree gate

1. Obtain the exact approved commit SHA containing `add-pfsense-runtime-ingest-filter-controls` and the Mac-built frontend artifact.
2. On the VM, record `git status --short`, current SHA, migration level, backend/listener PIDs, health, event count, and sanitized filter configuration. Stop if the VM worktree is dirty or the SHA is not explicitly approved.
3. Sync only the approved commit under `docs/mac-vm-source-of-truth-policy.md`; never edit source on the VM.

## Migration and deployment order

From the clean, approved VM checkout:

```bash
bash scripts/deploy_backend_vm.sh --dry-run-migrations
bash scripts/deploy_backend_vm.sh
curl -fsS http://127.0.0.1:5051/health
```

Confirm migration `0016_pfsense_ingest_config` applied exactly once and that all five rows match approved defaults. Verify backend health and stable service status/logs, then install/restart the repository listener unit only through its approved installer. Deploy the exact Mac-built frontend artifact after backend verification. Do not expose or print API keys, cookies, DSNs, or firewall payloads.

## Approved defaults

- `block_events=true`
- `inbound_sensitive_port_allows=true`
- `all_allow_events=false`
- `dns_traffic=false`
- `icmp_traffic=false`
- Sensitive ports: `21,22,23,25,135,445,1433,3306,3389,5432,5900,6379,27017`

## Synthetic matrix

Use documentation-only addresses and the authenticated route/listener path. Record HTTP outcome, listener outcome, backend counter delta, event delta, and downstream delta for each case:

| Case | Default result |
| --- | --- |
| IPv4 TCP block | `201`, retained |
| IPv4 ICMP block | `201`, retained |
| Inbound TCP allow to port 22 | `201`, retained |
| Outbound TCP allow to port 443 | `202`, filtered |
| Outbound UDP allow to port 53 | `202`, filtered |
| Allowed IPv4 ICMP | `202`, filtered |
| Invalid normalized payload | `4xx`, rejected |

For each filtered case, prove no new event, raw-event, alert, incident, response queue, playbook execution, or SOAR delivery row exists. Retained cases must create one event and continue through the unchanged centralized pipeline.

## Restartless checks

Through the super-admin API/UI, change one control at a time and record backend/listener PIDs before and after:

1. Enable `dns_traffic`; the next destination-port-53 allow becomes retained.
2. Enable `icmp_traffic`; the next allowed IPv4 ICMP event becomes retained.
3. Enable `all_allow_events`; the next routine allow becomes retained.
4. Add a documentation-safe test port to `inbound_sensitive_port_allows`; the next inbound allow to it is retained and suspicious-allow detection uses the same list.
5. Restore every approved default and verify audit entries contain category, safe old/new values, actor, and timestamp.

No backend or listener PID may change during these checks.

## Failure fallback and observability

Use only the child spec’s approved reversible failure method. Confirm configuration failure reports `invalid` or `unavailable`, applies restrictive source defaults, and never retains all traffic. Verify backend aggregate decision reasons and listener forwarded/filtered/ingested/rejected/backend-failed statistics reconcile with the matrix. Counters are operational and reset on process restart; dropped payloads must not be persisted.

## Rollback and readiness gate

If a critical check fails, prevent external forwarding before rollback. Restore only the prior approved commit/artifact/configuration using the repository runbook, retain the additive table and audit evidence, and verify health. Do not improvise destructive schema rollback.

Production readiness passes only when the approved SHA, clean-tree evidence, migration, services, frontend artifact, complete synthetic matrix, database deltas, restartless proof, fallback proof, audit records, restored defaults, and rollback readiness are documented. External uncle/pfSense forwarding remains blocked until that explicit pass.
