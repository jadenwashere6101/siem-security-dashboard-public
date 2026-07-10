# Response Registry VM Handoff (Mac Phase 3 complete)

Owner: **VM AI** via `vm-soar-runtime-recovery-parent` after Mac commits/pushes are authorized.

Mac source of truth: `/Users/jadengomez/Desktop/siem-security-dashboard-public`  
VM runtime only: `jaden@4.204.25.149:/home/jaden/siem-security-dashboard`

Do **not** edit feature source on the VM. Do **not** merge on a dirty VM.

## Prerequisites

1. Mac change `unify-analyst-response-workflows` Phases 1–3 implemented and validated.
2. Separate authorization to commit, push, and deploy.
3. VM worktree clean (`git status` empty of local edits).
4. Migration `0015_indicator_response_registry.sql` present on the deployed revision.

## Deployment sequence

1. **Clean-tree check (VM)**
   - `cd /home/jaden/siem-security-dashboard`
   - `git status --short` must be empty (or only approved runtime artifacts).

2. **Sync origin/main (after push authorization)**
   - Fetch/merge from the authorized Mac-pushed revision using the project source-of-truth workflow.
   - Never force-push; never rewrite applied migration files.

3. **Migration dry-run**
   - `python3 scripts/migrate.py --db-url "$DATABASE_URL" --dry-run`
   - Confirm `0015_indicator_response_registry` is pending (or already applied).

4. **Apply migration 0015**
   - `python3 scripts/migrate.py --db-url "$DATABASE_URL"`
   - Re-run dry-run; expect `Nothing to apply`.

5. **Registry backfill (safe, evidence-only)**
   - `python3 scripts/backfill_indicator_response_registry.py --db-url "$DATABASE_URL"`
   - Imports only provable Blocklist relationships; labels inferred/unknown provenance.
   - Do **not** invent success outcomes.

6. **Restart backend / workers**
   - Restart `siem-backend.service` and SOAR workers (`soar-playbook-worker`, response-action worker) per existing runbooks.
   - Confirm `/health` returns ok.

7. **Frontend build + Nginx**
   - Build frontend from the deployed revision.
   - Reload/restart Nginx so the new SPA assets are served.

8. **Runtime smoke tests**
   - Block / Monitor / Escalate from Dashboard and Response Registry → same registry/Blocklist state.
   - Blocklist Tracking view shows tracking-only copy; no firewall implication.
   - Deep links: Source IP / alert / incident / queue / approval → Response Registry filters.
   - SOC attention “Pending approvals” opens Approvals filtered to pending.
   - Confirm no new `unsupported_action` dead letters from supported UI paths (`notify` remains provider-specific; `enrich_context` playbook-only).

9. **Dead-letter canary remediation (after deploy)**
   - Classify historical `notify` / `enrich_context` unsupported_action records (see classifier script).
   - Canary-retry only idempotent records corrected by routing changes.
   - Dismiss/escalate obsolete, ambiguous, or unsafe records with reasons; preserve history.
   - Do **not** bulk-retry blindly.

## Rollback posture

- Prefer leaving additive registry tables in place.
- Roll back UI/routes first; stop new registry writes only if a compatibility flag is required.
- Never delete operational Blocklist/alert/incident/queue/approval history during rollback.
- Destructive `DROP TABLE` down-migrations are prohibited.

## Classifier / report helper

```bash
python3 scripts/classify_unsupported_action_dead_letters.py --db-url "$DATABASE_URL" --report
```

Produces a sanitized classification report only. It does **not** retry or dismiss records.
