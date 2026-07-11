# SOAR Outcome Evidence — VM Read-Only Handoff

Owner: **VM AI** after explicit read-only authorization.  
Mac change: `clarify-soar-outcome-evidence-and-verification`  
Mac source: `/Users/jadengomez/Projects/siem-security-dashboard-public`  
VM: `jaden@4.204.25.149:/home/jaden/siem-security-dashboard`

**NOT AUTHORIZED** to deploy or verify from this document alone.

## Gates

1. Explicit read-only authorization.
2. Clean VM worktree (`git status --short` empty).
3. `git rev-parse HEAD` equals approved deployed SHA.
4. No secrets in output (IDs/statuses/counts only).
5. **No** action endpoints: no notification sends, simulation batch, approve/deny, queue/dead-letter retry, Teams/firewall enablement, or mutation.
6. Rollback for source issues: redeploy prior artifact; no data rollback for read-only work.

## Deploy prerequisites (when deploy is later authorized)

1. Apply migration `0017_approval_expired_reason_code.sql` (additive CHECK; no row rewrite).
2. Apply migration `0018_internal_read_only_execution_modes.sql` (additive CHECK for `internal`/`read_only` modes; no row rewrite/backfill).
3. Restart backend workers/API so new outcome writers persist truthful modes and `approval_expired`.
4. Deploy frontend so Alert Details no longer treats legacy `alerts.response_status` as authoritative, Expired ≠ Rejected, and Internal/Read-only badges render for new modes.

Note: historical rows may still show `execution_mode=simulation` for monitor/escalation until naturally superseded by newer events; do not backfill.

## 5.1 Representative selection (do not manufacture)

Where naturally present, select sanitized samples of:

- simulated success
- tracking-only
- pending / blocked / rejected / failed / skipped
- **expired approval** (`reason_code=approval_expired`) distinct from **denied** (`approval_denied`)
- alert with terminal ResponseOutcome + stale legacy `alerts.response_status=pending` (presentation must prefer canonical)
- real executed (only if `execution_mode=real` and `external_executed=true`)
- unknown / missing evidence
- historical `approval_denied` rows (including any pre-correction expire-path records) still render safely

Absence of a class is reported, not invented.

## 5.2 Read-only outcome chain

Trace each selected record:

`alert → soar_response_outcome_events/decisions → queue → playbook_execution → notification_delivery_attempt → approval → integration mode`

Use GET/list APIs or SELECT of IDs/statuses/counts only. Redact tokens, endpoints, bodies, PII.

Compare each user-facing label (Simulated, Tracking only, Real executed, Expired, Rejected, Unknown, etc.) to canonical fields. Report match, missing link, or contradiction **without remediation**.

**Presentation checks (post-correction):**

- Alert Details / expanded row MUST NOT show standalone authoritative “Response Status: pending” when ResponseOutcome is terminal.
- Expired approvals MUST show `reason_code=approval_expired` on newly produced events (post-migration deploy); denied remain `approval_denied`.
- Effect booleans remain false for blocked/expired/denied paths.

## 5.3 Metrics reconciliation

At boundary timestamp T:

1. Capture SOAR Metrics API section values.
2. Compare to source tables/services in `docs/soar_metrics_source_mapping.md`.
3. Explain bounded concurrent-ingest differences.
4. Capture sanitized service health/config mode presence (no secrets).
5. Report unresolved source-contract drift to Mac AI.

## Stop conditions

Dirty tree, wrong SHA, unavailable tables, contradictory identifiers requiring mutation, secret exposure risk, or any non-read-only tool → stop immediately.
