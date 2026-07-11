## Why

**Owner: VM AI. Child of `add-pfsense-runtime-ingest-filter-controls`.** Runtime filtering is not production-ready until the approved Mac implementation is cleanly deployed and proven to retain security-relevant traffic, discard routine allows before storage, apply configuration without restarts, and roll back safely before external pfSense forwarding begins.

## What Changes

- Verify the VM worktree is clean and deploy only the explicitly approved Mac commit.
- Dry-run and apply the configuration migration through the repository deployment workflow.
- Deploy backend source, current pfSense listener service artifacts, and the Mac-built frontend output in dependency order.
- Capture sanitized service, health, configuration, and database baselines without exposing secrets or editing VM source.
- Execute a synthetic matrix covering blocks, inbound/outbound sensitive allows, routine allows, DNS port-53 traffic, supported ICMP, invalid payloads, and configuration failure fallback.
- Prove filtered events never appear in `events` or secondary raw storage, retained events still drive expected detections, and counters distinguish rejected, filtered, forwarded, and ingested outcomes.
- Change every runtime control and the sensitive-port list, prove the next request uses it without a service restart, then restore the approved production defaults.
- Document rollback and enforce a final readiness gate before the uncle/pfSense handoff.

## Capabilities

### New Capabilities

- `pfsense-ingest-filter-production-readiness`: Clean deployment, migration, runtime matrix, restartless configuration, data verification, rollback, and external-handoff gates.

### Modified Capabilities

<!-- No base capability requirements change; this is the runtime acceptance child for the Mac parent. -->

## Impact

This change governs only the deployment VM, PostgreSQL migration/config rows, backend and pfSense listener services, frontend build artifact, journals/health checks, synthetic test traffic, and evidence. It may mutate approved runtime configuration and synthetic test data during the maintenance window, but it must not edit VM source, configure the external pfSense, commit, push, or proceed from a dirty VM.
