## 1. VM AI Phase 3 — Deployment and Production Readiness

- [ ] 1.1 Verify the Mac handoff is complete, identify the explicitly approved commit and frontend artifact, and refuse deployment if implementation validation or approval evidence is missing.
- [ ] 1.2 Prove the VM worktree is clean and on the expected deployment branch/SHA; record service PIDs/status, migration level, relevant configuration, event counts, and listener statistics before changes.
- [ ] 1.3 Fetch and fast-forward or merge only the approved source according to the Mac/VM policy, without editing source on the VM or merging over a dirty worktree.
- [ ] 1.4 Run the repository migration dry-run/preflight, review its exact plan, apply it once, and verify the new table, constraints, defaults, and schema version before restarting services.
- [ ] 1.5 Deploy backend and listener units/configuration through repository-supported procedures, reload systemd only when required, and verify stable health and logs.
- [ ] 1.6 Deploy the exact Mac-built frontend artifact and verify the super-admin Administration controls load, remain readable in the dark theme, and accurately display effective defaults.
- [ ] 1.7 Run the synthetic API and listener matrix for retained blocks, retained inbound sensitive-port allows, dropped routine allows, DNS port-53 behavior, allowed/blocked ICMP, invalid input, and backend failure using documentation-safe addresses.
- [ ] 1.8 Compare database and downstream counts before/after to prove retained events are inserted once and filtered events create no event, raw-event, alert, enrichment, correlation, SOAR, or incident records.
- [ ] 1.9 Reconcile forwarded, filtered, rejected, ingested, backend-failed, category, and reason counters with the synthetic matrix and inspect bounded logs for safe reason reporting.
- [ ] 1.10 Change each toggle and the sensitive-port list through the super-admin API/UI, prove the next request observes it while backend/listener PIDs remain unchanged, and verify audit entries.
- [ ] 1.11 Exercise the approved configuration-failure test, confirm safe defaults rather than ingest-all behavior, and restore normal database/configuration health without source edits.
- [ ] 1.12 Restore approved production defaults, repeat critical retained/dropped checks, and observe services and counters for the handoff window.
- [ ] 1.13 Verify rollback commands and prerequisites, record whether a rollback rehearsal was performed, and on failure pause external forwarding before restoring the prior approved source/artifact/configuration.
- [ ] 1.14 Issue the final readiness report with commit, migrations, service PIDs, artifact, synthetic outcomes, DB deltas, counters, restartless proof, fallback proof, audit evidence, rollback status, and an explicit pass/fail gate before uncle/pfSense forwarding is enabled.
