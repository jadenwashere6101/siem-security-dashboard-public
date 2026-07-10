# Canonical Response Policies (Phase 1)

Owner: Mac AI — `unify-analyst-response-workflows` Phase 1.

## Monitoring / watch disposition

- Selecting `monitor` creates a durable registry disposition `monitored`.
- Default TTL: **168 hours (7 days)** from start unless the caller supplies `expires_at`.
- Renewal: a subsequent authorized `monitor` for the same normalized IP reuses the
  registry identity, appends a new event, and extends/replaces expiry when provided.
- Removal: an explicit stop-monitoring / remove command (Phase 2 UI) sets disposition
  `removed` or `expired` when TTL elapses; Phase 1 records expiry on the event and
  derives current disposition from the latest non-superseded event.
- Monitoring never implies firewall or notification delivery.

## Escalation (`flag_high_priority` / alias `escalate`)

Minimum durable internal handoff (Phase 1):

1. Require an `alert_id` when available; if only `source_ip` is provided, create or
   attach context without inventing alert linkage.
2. Ensure an incident exists for the alert/source_ip:
   - Prefer linking the alert to an existing open incident for that source IP.
   - Otherwise create an incident with priority **P2**, severity **high**, status
     `open`, titled from the alert type or a generic escalation title.
3. Raise the alert's operational priority signal by setting `response_action` to
   `flag_high_priority` and recording registry disposition `escalated`.
4. Never report escalation success for log-only behavior — the incident/registry
   mutation must succeed inside the same transaction.

Assignment to a specific analyst is optional in Phase 1 (`assigned_to` remains null
unless a future policy supplies it).

## Blocklist tracking (`block_ip`)

- Tracking-only: creates or reuses one active `blocked_ips` row.
- Enforcement statement is always **none** (no firewall/host enforcement).
- Protected, private, loopback, and malformed targets are rejected with no active
  Blocklist row.

## Affected-resource invalidation keys

Mutation responses include keys such as `alert:<id>`, `source_ip:<ip>`,
`blocked_ip:<id>`, `registry:<id>`, `incident:<id>`, plus `response_registry` and
`blocklist` for aggregate refreshes (consumed by Phase 3 UI invalidation).
