# Playbook Worker Daemon Health VM Handoff

This handoff applies only after explicit user authorization for VM work.

## Scope

- Apply migration `0019_playbook_worker_daemon_health.sql`.
- Restart `siem-backend.service` so `/metrics/playbook-worker` serves daemon heartbeat metadata.
- Restart `soar-playbook-worker.service` so the daemon begins writing persisted heartbeats.
- Verify worker health states and queue metrics without mutating approvals, retries, or playbook logic.

## Deployment Order

1. Run VM clean-tree preflight per [docs/mac-vm-source-of-truth-policy.md](docs/mac-vm-source-of-truth-policy.md).
2. Sync the explicitly approved commit only.
3. Dry-run migrations.
4. Apply migrations.
5. Restart `siem-backend.service`.
6. Restart `soar-playbook-worker.service`.
7. Verify backend health and worker metrics.

## Required Verification

- `curl -fsS http://127.0.0.1:5051/health`
- `curl -sS -b cookies.txt http://127.0.0.1:5051/metrics/playbook-worker`
- `systemctl status soar-playbook-worker.service --no-pager`
- `journalctl -u soar-playbook-worker.service -n 100 --no-pager`

Confirm:

- `daemon_health.status` is not permanently `unknown` after the worker starts.
- `daemon_health.last_heartbeat_at` advances over time.
- `daemon_health.started_at` and `daemon_health.uptime_seconds` are present.
- `daemon_health.build_version` is present when local git metadata is available.
- Queue counts, stale-running counts, and recovery metrics remain sane.
- No secrets appear in logs or API payloads.

## Rollback Expectations

- If migration apply fails: stop and do not restart services.
- If backend restart fails: restore the service before touching the worker service.
- If worker restart fails: inspect journal logs, leave backend available, and avoid ad hoc source edits on the VM.
- This change is additive only; rollback is operational, not destructive schema removal.

## Ownership

- Mac AI completed source, tests, build, and OpenSpec validation.
- VM AI owns deployment only after explicit authorization.
