# pfSense Deployment Runtime Readiness

This runbook implements the `pfsense-deployment-runtime-readiness` contract as operator guidance and local validation only. Mac repo is the source of truth. VM repo is deployment/runtime only.

No Azure NSG rule is created by this runbook. No VM firewall rule is created by this runbook. No live pfSense production traffic is used for validation. Do not ask the uncle to configure pfSense until Deployment Sign-off is recorded.

## Scope Boundaries

This readiness layer sequences deployment and validation for previously implemented child specs. It does not implement or redesign the parser, `/ingest/pfsense` route, UDP listener, detections, SOAR playbooks, database schema, Azure NSG rules, VM firewall rules, production deployment, or production log collection.

Alert, playbook, and approval validation is "verify once implemented." If a dependent behavior is not present in the deployed revision, record it as blocked by that owning child spec rather than implementing it here.

## Deployment Sequence

1. Confirm local GitHub state from the Mac repo:

   ```bash
   git fetch origin
   git rev-parse HEAD
   git rev-parse origin/main
   git status --short
   ```

   Continue only when `HEAD` matches `origin/main` and the Mac working tree is clean.

2. Confirm VM repo cleanliness before sync:

   ```bash
   ssh -i ~/.ssh/jadeng15.pem jaden@4.204.25.149 'cd /home/jaden/siem-security-dashboard && git status --short'
   ```

   Stop if any output is returned. Never merge on a dirty VM.

3. Sync VM code only after the VM is clean:

   ```bash
   ssh -i ~/.ssh/jadeng15.pem jaden@4.204.25.149 'cd /home/jaden/siem-security-dashboard && git fetch origin && git merge origin/main'
   ```

4. Check and apply pending migrations before dependent restarts:

   ```bash
   bash scripts/deploy_backend_vm.sh --dry-run-migrations
   bash scripts/deploy_backend_vm.sh --skip-restart
   ```

5. Restart in dependency order: backend first, then workers, then listener.

   ```bash
   sudo systemctl restart siem-backend.service
   curl -fsS http://127.0.0.1:5051/health
   sudo systemctl restart soar-playbook-worker.service
   sudo systemctl restart soar-response-action-worker.timer
   sudo systemctl restart pfsense-syslog-listener.service
   ```

6. Verify service status and listener bind:

   ```bash
   systemctl is-active siem-backend.service
   systemctl is-active soar-playbook-worker.service
   systemctl is-active soar-response-action-worker.timer
   systemctl is-active pfsense-syslog-listener.service
   ss -lunp | grep ':5514'
   ```

7. Confirm VM repo cleanliness after deployment:

   ```bash
   git status --short
   ```

## Infrastructure Gates

Confirm the final UDP port before any Azure NSG rule is drafted. The default is `5514`; use UDP `514` only if pfSense cannot target a custom port and a privilege plan is documented.

Confirm the expected pfSense public IP before any Azure NSG rule or listener allow-list is finalized. The Azure NSG source must be restricted to that IP where possible. A broader source is a temporary exception only with explicit approval and a cleanup task.

Record the VM firewall decision either way:

- Added defense-in-depth VM firewall rule for the confirmed UDP port, with command and rollback noted.
- Deferred VM firewall rule, with rationale and compensating controls noted.

Service installation remains operator-controlled:

```bash
scripts/install_soar_playbook_worker_service.sh --dry-run
scripts/install_response_action_worker_service.sh --dry-run
scripts/install_pfsense_syslog_listener_service.sh --dry-run
```

Running install helpers without `--enable` or `--start` must not enable or start services.

## Environment Variables

Review these before deployment:

- Backend: `SIEM_PORT`, database settings through `DATABASE_URL` or `SIEM_DB_*` / `DB_*`, ingest API key configuration used by existing ingest routes.
- Workers: service environment files and SOAR execution mode settings required by the playbook and response-action worker runbooks.
- Listener: `PFSENSE_LISTENER_BIND_HOST`, `PFSENSE_LISTENER_PORT`, `PFSENSE_ALLOWED_SOURCE_IPS`, `PFSENSE_BACKEND_URL`, `PFSENSE_INGEST_API_KEY`, `PFSENSE_API_KEY_HEADER`, `PFSENSE_MAX_PACKET_BYTES`, `PFSENSE_GLOBAL_RATE_LIMIT`, `PFSENSE_PER_SOURCE_RATE_LIMIT`, `PFSENSE_RATE_LIMIT_WINDOW_SECONDS`, `PFSENSE_BACKEND_TIMEOUT_SECONDS`, `PFSENSE_RECV_TIMEOUT_SECONDS`, `PFSENSE_ENVIRONMENT`, `PFSENSE_SYSLOG_TIMEZONE` (the pfSense firewall's IANA timezone, for example `America/New_York`), and log level from the daemon invocation.

## Runtime Validation

Use synthetic/local packets only. Keep Azure NSG closed to external pfSense traffic until this section passes.

1. Send synthetic pfSense filterlog packets locally to the deployed listener.
2. Verify parser output fields through the listener path: action, interface, direction, protocol, source IP, destination IP, destination port, `source=pfsense`, and `source_type=firewall`.
3. Verify `/ingest/pfsense` accepts forwarded normalized events and returns success.
4. Verify database rows exist with `source=pfsense` and `source_type=firewall`.
5. Verify dashboard visibility for pfSense events.
6. Verify expected detections fire on blocked/suspicious synthetic events and do not fire on benign allowed traffic.
7. Verify playbook execution behavior for pfSense-triggered alerts where applicable.
8. Verify protected-target approval gates for any disruptive firewall response action.
9. Verify structured safe logging across listener, ingest route, and worker components without raw payloads or secrets.
10. Verify failure paths: malformed packet, oversized packet, unauthorized source IP, rate-limited traffic, backend 4xx, backend 5xx, backend timeout, and backend network failure. No component may crash or enter an unrecoverable state.

## Production Readiness

Operator checklist:

- Service install helpers reviewed and dry-run output reviewed.
- Backend, worker, and listener service files reviewed.
- Required environment variables reviewed with secrets redacted.
- Final port and expected pfSense public IP recorded.
- VM firewall decision recorded.

Monitoring checklist:

- Backend health endpoint reviewed.
- Worker service status and recent journal entries reviewed.
- Listener service status, bind status, counters, and recent journal entries reviewed.
- Error counts, rejected-source counts, malformed counts, oversized counts, rate-limit counts, parser failures, and ingest failures reviewed.

Rollback criteria:

- Backend health check failure after restart.
- Worker service inactive/failing after restart.
- Listener inactive, not bound, or in crash loop.
- Error-rate threshold breach during synthetic validation.
- Unsafe logs, secret leakage, or raw attacker-controlled payload leakage.

Success criteria:

- All Runtime Validation items pass using synthetic/local traffic.
- Backend, workers, and listener health checks pass.
- VM repo remains clean.
- No Azure NSG or VM firewall rule is opened before local validation and sign-off.

## Rollback Plan

- Backend: stop rollout, redeploy prior known-good revision, run migration rollback only if explicitly designed for the migration, restart `siem-backend.service`, and recheck `/health`.
- Playbook worker: stop or roll back `soar-playbook-worker.service`, reinstall prior unit if needed, and verify status.
- Response-action worker: stop or disable `soar-response-action-worker.timer`, reinstall prior unit/timer if needed, and verify timer state.
- Listener service: stop/disable `pfsense-syslog-listener.service`, run `scripts/install_pfsense_syslog_listener_service.sh --rollback`, and verify no UDP bind remains.
- Azure NSG rule: remove the listener inbound rule and verify no external listener exposure remains.
- VM firewall rule: remove the defense-in-depth rule if one was added and record the removal.

## Deployment Sign-off

Record sign-off only after the operator checklist, monitoring checklist, health checks, rollback criteria review, and all Runtime Validation scenarios pass.

Required sign-off record:

- Git revision deployed.
- Confirmed listener UDP port.
- Confirmed pfSense public IP.
- Azure NSG state.
- VM firewall decision.
- Runtime validation evidence location.
- Operator name and date.

No uncle/pfSense handoff communication may be sent before this sign-off exists.

## pfSense Handoff

Information required from the uncle:

- Confirmed pfSense public IP.
- Confirmation pfSense can target the confirmed custom UDP port, expected `5514`, or whether it requires `514`.
- Confirmation remote syslog is available.

Guidance to prepare after sign-off:

- Navigate to Status -> System Logs -> Settings.
- Enable Firewall Events for remote logging.
- Configure the remote server target as `<Azure VM public IP>:<confirmed listener UDP port>`.
- Confirm the expected source public IP still matches the Azure NSG restriction and `PFSENSE_ALLOWED_SOURCE_IPS`.

Only after the final production enablement checklist passes should the uncle be asked to enable remote syslog.
