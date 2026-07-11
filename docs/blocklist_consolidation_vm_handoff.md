# Blocklist Consolidation — VM Handoff (Mac phase complete)

Owner: **VM AI** after explicit deploy authorization, then separately for mutation.  
Mac change: `consolidate-blocklist-response-registry-workflow`  
Mac source: `/Users/jadengomez/Projects/siem-security-dashboard-public`  
VM runtime: `jaden@4.204.25.149:/home/jaden/siem-security-dashboard`

**NOT AUTHORIZED** to deploy, classify production data, or mutate from this document alone.

## Mac contract delivered

- Standalone Blocklist sidebar destination removed.
- Response Registry → **Blocklist Tracking** is the sole user-facing Blocklist workspace.
- Legacy `blocklist` landing/nav IDs normalize to Response Registry `blocklist_tracking`.
- Supported removal remains:
  - UI: **Remove Tracking** (Blocklist Tracking table + registry detail)
  - API: `PATCH /blocked-ips/<id>/unblock` → canonical `remove_tracking`
  - Command: `execute_response_command(action="remove_tracking", …)`
- No new endpoint, migration, or direct-delete path.
- Copy states: ends SIEM tracking, preserves history/audit, **no firewall/provider/host change**.

## Audit inventory (Mac 1.1–1.3)

| Layer | Path |
| --- | --- |
| UI | `ResponseRegistryPanel` Blocklist Tracking tab → `BlocklistManagerPanel`; detail **Remove Tracking** |
| Services | `blocklistService.unblockBlocklistEntry`, `responseRegistryService.executeRegistryCommand` |
| APIs | `GET/POST /blocked-ips`, `PATCH /blocked-ips/<id>/unblock`, registry command route |
| Command | `core/response_command_service._execute_remove_tracking` |
| Persistence | `blocked_ips.status` → `inactive`; `indicator_registry_events`; disposition `removed` |
| Audit | `log_audit_event("block_ip_removed", …)` |
| Guards | `@analyst_or_super_admin_required`, `require_unprotected_target`, idempotency keys `blocklist-unblock-<id>` / command keys |
| Schema | **None required** |

## Prerequisites before any VM work

1. Explicit commit + push of the Mac change.
2. Explicit deploy authorization naming the **approved commit SHA**.
3. VM `git status --short` empty.
4. `git rev-parse HEAD` equals approved SHA after sync.
5. Frontend artifact from that SHA deployed (`frontend/build/` rsync). Backend restart **not** required unless SHA also contains unrelated backend changes (this change is primarily frontend + message strings).

## Phase 4 — Read-only classification of `12.12.12.12` (explicit auth required)

Stop if dirty tree, wrong SHA, or secrets would be printed.

### Sanitized classification queries (no secrets)

```bash
# Count matches (sanitize output to id/status/ip only)
psql "$DATABASE_URL" -c "
SELECT id, status, created_by IS NOT NULL AS has_actor, expires_at IS NOT NULL AS has_expiry
FROM blocked_ips
WHERE host(ip_address) = '12.12.12.12'
ORDER BY id;"

psql "$DATABASE_URL" -c "
SELECT ir.id, ir.current_disposition, ir.active_blocked_ip_id
FROM indicator_registry ir
WHERE ir.indicator_type = 'ip' AND ir.indicator_value = '12.12.12.12';"

psql "$DATABASE_URL" -c "
SELECT COUNT(*) AS event_count
FROM indicator_registry_events e
JOIN indicator_registry ir ON ir.id = e.registry_id
WHERE ir.indicator_value = '12.12.12.12';"
```

### API read (session cookie required; do not paste tokens)

```bash
curl -fsS -b "$SESSION_COOKIE" 'http://127.0.0.1:5051/blocked-ips' | python3 -c "
import json,sys
rows=[r for r in json.load(sys.stdin) if r.get('ip_address')=='12.12.12.12']
print([{'id':r['id'],'status':r['status']} for r in rows])
"
```

### Classification labels

For each match record: `active` | `expired` | `historical` | `removed` | `protected` | `unknown`.  
Record sanitized IDs, statuses, and before counts (target + unrelated totals).  
**Stop after reporting. Read-only auth does not permit removal.**

## Phase 5 — Supported removal (separate explicit mutation authorization)

Allowed only when classification shows **exactly one** active, non-protected, unambiguous record and audit is available.

### Supported path (once)

1. UI: Response Registry → Blocklist Tracking → **Remove Tracking** for that row, **or**
2. API once:
   ```bash
   curl -fsS -X PATCH -b "$SESSION_COOKIE" \
     "http://127.0.0.1:5051/blocked-ips/<ACTIVE_ID>/unblock"
   ```
3. Do **not** use SQL `UPDATE`/`DELETE`, bulk tools, or blind retries.

### Before/after evidence

- Target row status active → inactive
- Unrelated `blocked_ips` / registry counts unchanged
- Registry event `tracking_removed`, disposition `removed`
- Audit `block_ip_removed`
- API/UI message asserts tracking-only / no firewall change

### Stop / rollback

- Stop if duplicates, protected target, terminal status, failed/unknown outcome, firewall claim, or unrelated count delta.
- Rollback: history stays; re-add only via separately authorized canonical `block_ip` / Add Tracking.

## Deployment artifact summary

| Artifact | Required? |
| --- | --- |
| Frontend `frontend/build/` | Yes |
| Backend restart | Only if approved SHA includes backend `.py` message changes you want live; prefer restart if deploying those files |
| Migrations | No |
| Direct DB mutation | Never |
