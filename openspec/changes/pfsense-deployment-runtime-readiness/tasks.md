## 1. Audit / Verification

- [ ] 1.1 Re-read the parent roadmap and confirm this child maps only to Phase 3 item 6.12.
- [ ] 1.2 Re-read `pfsense-filterlog-parser-normalizer`, `pfsense-ingest-route-pipeline`, and `pfsense-udp-listener-daemon` and confirm this spec only sequences their deployment/validation and does not redesign any of them.
- [ ] 1.3 Re-read `pfsense-firewall-detections-soar` (6.11) and scope alert/playbook verification tasks to "verify once implemented."
- [ ] 1.4 Confirm implementation scope remains deployment/runtime-readiness only: no parser, ingest, listener, detection, SOAR, or firewall-rule implementation, no Azure NSG creation, no live deployment, and no production traffic.

## 2. Deployment Sequence (Future Execution)

- [ ] 2.1 Verify GitHub `origin/main` is up to date and the Mac repo working tree is clean.
- [ ] 2.2 Verify the VM repo working tree is clean before fetch/merge.
- [ ] 2.3 Fetch/merge the VM repo to match `origin/main`.
- [ ] 2.4 Check for pending schema migrations and apply them before restarting dependent services.
- [ ] 2.5 Restart the backend service.
- [ ] 2.6 Restart the playbook/response-action worker services.
- [ ] 2.7 Restart or start the pfSense UDP listener service, in that order after backend and workers.
- [ ] 2.8 Verify backend health endpoint after restart.
- [ ] 2.9 Verify worker service status (`systemctl status`, `is-active`) after restart.
- [ ] 2.10 Verify listener service status and confirm it is bound to the configured UDP port after restart.
- [ ] 2.11 Confirm VM repo is clean after deployment completes.

## 3. Infrastructure Sequence (Future Execution)

- [ ] 3.1 Confirm the final pfSense-side UDP port capability (`5514` default vs `514`) before any Azure NSG rule is created.
- [ ] 3.2 Confirm the expected pfSense public IP before Azure NSG rule creation.
- [ ] 3.3 Create the Azure NSG inbound rule only after the listener passes local/VM-side synthetic validation, restricted to the confirmed pfSense public IP where possible.
- [ ] 3.4 Record the VM firewall decision (defense-in-depth rule added, or explicitly deferred) regardless of which option is chosen.
- [ ] 3.5 Install/update the listener and worker services using the existing operator-controlled install-helper pattern, without auto-enabling or auto-starting.
- [ ] 3.6 Document the required environment variables for backend, workers, and listener (bind host/port, source IP allow-list, ingest URL, ingest API key/header, packet size limit, rate limits, timeout, log level).
- [ ] 3.7 Document the rollback plan for each component: backend, workers, listener service, and Azure NSG rule.

## 4. Runtime Validation (Future Execution)

- [ ] 4.1 Send synthetic/local pfSense filterlog packets to the deployed listener without external exposure.
- [ ] 4.2 Verify the parser correctly extracts fields from synthetic packets end to end through the deployed listener.
- [ ] 4.3 Verify the ingest route accepts forwarded normalized events and responds successfully.
- [ ] 4.4 Verify normalized pfSense events are present in the database with `source=pfsense` and `source_type=firewall`.
- [ ] 4.5 Verify pfSense events are visible on the dashboard.
- [ ] 4.6 Verify expected detection rules fire on synthetic pfSense events and do not fire on synthetic allowed/benign traffic.
- [ ] 4.7 Verify playbook execution behavior for pfSense-triggered alerts where applicable.
- [ ] 4.8 Verify approval gates function correctly for any protected-target playbook actions triggered by pfSense alerts.
- [ ] 4.9 Verify structured safe logging across listener, ingest route, and worker components during synthetic testing.
- [ ] 4.10 Verify failure-path behavior: malformed packets, oversized packets, unauthorized source IP, rate-limited traffic, and backend failure responses are all handled safely without crashes or unsafe log output.

## 5. Production Readiness (Future Execution)

- [ ] 5.1 Complete the operator checklist (service status, config review, install-helper confirmation).
- [ ] 5.2 Complete the monitoring checklist (logs, metrics/counters, health endpoints reviewed).
- [ ] 5.3 Confirm health checks pass for backend, workers, and listener.
- [ ] 5.4 Confirm rollback criteria are documented and understood (health check failure, error-rate threshold, listener crash loop).
- [ ] 5.5 Confirm success criteria are documented and met (all Section 4 runtime validation scenarios pass).
- [ ] 5.6 Record explicit deployment sign-off before drafting any uncle/pfSense handoff communication.

## 6. pfSense Handoff (Future Execution)

- [ ] 6.1 Document the exact information required from the uncle (public IP, ability to target a custom UDP port, remote syslog capability).
- [ ] 6.2 Confirm the expected pfSense public IP matches what was used for the Azure NSG restriction and listener allow-list.
- [ ] 6.3 Prepare remote syslog configuration guidance for pfSense (Status -> System Logs -> Settings, enable Firewall Events, remote server target).
- [ ] 6.4 Complete the final production enablement checklist before asking the uncle to enable remote syslog.
- [ ] 6.5 Only after all prior sections pass, request the uncle configure pfSense remote logging.

## 7. Parent Roadmap Update

- [ ] 7.1 After deployment and runtime validation are actually executed, update `pfsense-firewall-ingestion-roadmap` Phase 5/6/7 checklists to record status.
- [ ] 7.2 Keep roadmap notes clear that this spec governs deployment/runtime-readiness only, and that parser, ingest, listener, detection, and SOAR behavior are owned by their respective child specs.
