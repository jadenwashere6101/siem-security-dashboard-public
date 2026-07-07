## 1. Audit / Verification

- [x] 1.1 Re-read the parent roadmap and confirm this child maps only to Phase 3 item 6.12.
  - Confirmed. Implementation stays scoped to deployment/runtime readiness.
- [x] 1.2 Re-read `pfsense-filterlog-parser-normalizer`, `pfsense-ingest-route-pipeline`, and `pfsense-udp-listener-daemon` and confirm this spec only sequences their deployment/validation and does not redesign any of them.
  - Confirmed. No parser, ingest route, or listener internals were changed.
- [x] 1.3 Re-read `pfsense-firewall-detections-soar` (6.11) and scope alert/playbook verification tasks to "verify once implemented."
  - Confirmed. Runtime validation guidance verifies available behavior and records blockers against owning specs.
- [x] 1.4 Confirm implementation scope remains deployment/runtime-readiness only: no parser, ingest, listener, detection, SOAR, or firewall-rule implementation, no Azure NSG creation, no live deployment, and no production traffic.
  - Confirmed. Implementation added runbook/helper/test artifacts only.

## 2. Deployment Sequence (Future Execution)

- [x] 2.1 Verify GitHub `origin/main` is up to date and the Mac repo working tree is clean.
  - Implemented as a documented deployment gate and optional `--require-clean-git` readiness helper check. Current implementation validation did not require a clean tree because these files are intentionally being edited.
- [x] 2.2 Verify the VM repo working tree is clean before fetch/merge.
  - Implemented as a documented deployment gate. Not executed in this implementation to avoid VM operations.
- [x] 2.3 Fetch/merge the VM repo to match `origin/main`.
  - Implemented as an operator-controlled documented step. Not executed; no VM modification was performed.
- [x] 2.4 Check for pending schema migrations and apply them before restarting dependent services.
  - Implemented through the runbook using existing `scripts/deploy_backend_vm.sh --dry-run-migrations` and `--skip-restart` sequencing.
- [x] 2.5 Restart the backend service.
  - Implemented as an operator-controlled documented step in dependency order. Not executed.
- [x] 2.6 Restart the playbook/response-action worker services.
  - Implemented as operator-controlled documented steps in dependency order. Not executed.
- [x] 2.7 Restart or start the pfSense UDP listener service, in that order after backend and workers.
  - Implemented as an operator-controlled documented step after backend and workers. Not executed.
- [x] 2.8 Verify backend health endpoint after restart.
  - Implemented as a documented verification step.
- [x] 2.9 Verify worker service status (`systemctl status`, `is-active`) after restart.
  - Implemented as documented verification steps.
- [x] 2.10 Verify listener service status and confirm it is bound to the configured UDP port after restart.
  - Implemented as documented `systemctl` and UDP bind verification steps.
- [x] 2.11 Confirm VM repo is clean after deployment completes.
  - Implemented as a documented post-deployment gate. Not executed.

## 3. Infrastructure Sequence (Future Execution)

- [x] 3.1 Confirm the final pfSense-side UDP port capability (`5514` default vs `514`) before any Azure NSG rule is created.
  - Implemented as a documented infrastructure gate.
- [x] 3.2 Confirm the expected pfSense public IP before Azure NSG rule creation.
  - Implemented as a documented infrastructure gate.
- [x] 3.3 Create the Azure NSG inbound rule only after the listener passes local/VM-side synthetic validation, restricted to the confirmed pfSense public IP where possible.
  - Implemented as a documented gated future action. No Azure NSG rule was created.
- [x] 3.4 Record the VM firewall decision (defense-in-depth rule added, or explicitly deferred) regardless of which option is chosen.
  - Implemented as a required runbook record.
- [x] 3.5 Install/update the listener and worker services using the existing operator-controlled install-helper pattern, without auto-enabling or auto-starting.
  - Implemented by verifying existing install helpers in `scripts/pfsense_deployment_readiness_check.py`.
- [x] 3.6 Document the required environment variables for backend, workers, and listener (bind host/port, source IP allow-list, ingest URL, ingest API key/header, packet size limit, rate limits, timeout, log level).
  - Implemented in `docs/pfsense_deployment_runtime_readiness.md`.
- [x] 3.7 Document the rollback plan for each component: backend, workers, listener service, and Azure NSG rule.
  - Implemented in `docs/pfsense_deployment_runtime_readiness.md`.

## 4. Runtime Validation (Future Execution)

- [x] 4.1 Send synthetic/local pfSense filterlog packets to the deployed listener without external exposure.
  - Implemented as a runbook validation step; local listener tests cover synthetic packet behavior without external exposure.
- [x] 4.2 Verify the parser correctly extracts fields from synthetic packets end to end through the deployed listener.
  - Implemented as a runbook validation step and covered by existing listener/parser tests.
- [x] 4.3 Verify the ingest route accepts forwarded normalized events and responds successfully.
  - Implemented as a runbook validation step and covered by existing route tests.
- [x] 4.4 Verify normalized pfSense events are present in the database with `source=pfsense` and `source_type=firewall`.
  - Implemented as a runbook validation step for future deployment execution.
- [x] 4.5 Verify pfSense events are visible on the dashboard.
  - Implemented as a runbook validation step for future deployment execution.
- [x] 4.6 Verify expected detection rules fire on synthetic pfSense events and do not fire on synthetic allowed/benign traffic.
  - Implemented as a runbook validation step and scoped to available 6.11 behavior.
- [x] 4.7 Verify playbook execution behavior for pfSense-triggered alerts where applicable.
  - Implemented as a runbook validation step and scoped to available 6.11 behavior.
- [x] 4.8 Verify approval gates function correctly for any protected-target playbook actions triggered by pfSense alerts.
  - Implemented as a runbook validation step and scoped to available approval behavior.
- [x] 4.9 Verify structured safe logging across listener, ingest route, and worker components during synthetic testing.
  - Implemented as a runbook validation step.
- [x] 4.10 Verify failure-path behavior: malformed packets, oversized packets, unauthorized source IP, rate-limited traffic, and backend failure responses are all handled safely without crashes or unsafe log output.
  - Implemented as a runbook validation step and covered by existing listener tests for local failure paths.

## 5. Production Readiness (Future Execution)

- [x] 5.1 Complete the operator checklist (service status, config review, install-helper confirmation).
  - Implemented as a runbook checklist.
- [x] 5.2 Complete the monitoring checklist (logs, metrics/counters, health endpoints reviewed).
  - Implemented as a runbook checklist.
- [x] 5.3 Confirm health checks pass for backend, workers, and listener.
  - Implemented as runbook health criteria.
- [x] 5.4 Confirm rollback criteria are documented and understood (health check failure, error-rate threshold, listener crash loop).
  - Implemented as runbook rollback criteria.
- [x] 5.5 Confirm success criteria are documented and met (all Section 4 runtime validation scenarios pass).
  - Implemented as runbook success criteria.
- [x] 5.6 Record explicit deployment sign-off before drafting any uncle/pfSense handoff communication.
  - Implemented as a runbook sign-off gate.

## 6. pfSense Handoff (Future Execution)

- [x] 6.1 Document the exact information required from the uncle (public IP, ability to target a custom UDP port, remote syslog capability).
  - Implemented in the handoff section of the runbook.
- [x] 6.2 Confirm the expected pfSense public IP matches what was used for the Azure NSG restriction and listener allow-list.
  - Implemented as a handoff gate.
- [x] 6.3 Prepare remote syslog configuration guidance for pfSense (Status -> System Logs -> Settings, enable Firewall Events, remote server target).
  - Implemented as post-sign-off guidance.
- [x] 6.4 Complete the final production enablement checklist before asking the uncle to enable remote syslog.
  - Implemented as a handoff gate.
- [x] 6.5 Only after all prior sections pass, request the uncle configure pfSense remote logging.
  - Implemented as an explicit blocked-until-sign-off rule. No handoff was performed.

## 7. Parent Roadmap Update

- [x] 7.1 After deployment and runtime validation are actually executed, update `pfsense-firewall-ingestion-roadmap` Phase 5/6/7 checklists to record status.
  - Implemented by documenting that roadmap status is updated only after actual execution. No Phase 5/6/7 execution status was changed during this implementation.
- [x] 7.2 Keep roadmap notes clear that this spec governs deployment/runtime-readiness only, and that parser, ingest, listener, detection, and SOAR behavior are owned by their respective child specs.
  - Confirmed through this task file and the readiness runbook.
