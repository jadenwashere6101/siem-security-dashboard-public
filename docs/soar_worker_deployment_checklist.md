# SOAR worker deployment checklist

Use this only on the VM after an authorized Mac commit/push. The Mac repository remains the source of truth.

1. Confirm `git status --short` is empty before merging. Never merge on a dirty VM.
2. Review changed backend, worker wrapper, and `deploy/systemd` artifacts.
3. Run `scripts/deploy_backend_vm.sh`. It installs the Gunicorn backend unit and both worker unit
   templates, runs `systemctl daemon-reload`, restarts the backend, verifies health/security gates,
   then restarts workers and prints effective units with `systemctl cat` so installed configuration
   cannot silently drift from the repository.
4. Inspect only non-secret effective guards. Expected operational modes are real Slack, Email,
   and Webhook; simulation-only Teams, firewall, `monitor`, and `flag_high_priority`.
5. Confirm backend health, Gunicorn effective-unit evidence, loopback bind, debugger absence,
   secure cookies, and worker/timer status without triggering playbooks or notifications.
6. If verification fails, restore the prior authorized revision and unit templates, run
   `systemctl daemon-reload`, restart the affected services, and repeat sanitized checks.

The notification kill switch is configuration, not a separate runtime model: set
`INTEGRATION_MODE=simulation` and all `SOAR_REAL_*_ENABLED` guards to `false`, then restart the
backend and workers. Deployment scripts do not modify `.env` and must never print secrets.
