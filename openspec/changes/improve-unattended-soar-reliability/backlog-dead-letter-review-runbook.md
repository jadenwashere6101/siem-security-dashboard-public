# Existing Approval-Expired / Approval-Denied Dead-Letter Backlog Review

This runbook covers the historical `soar_dead_letters` rows created **before**
Phases 1–2 of `improve-unattended-soar-reliability`. Going forward, denied or
expired approvals with no `on_denied`/`on_expired: "branch"` fallback reach
`playbook_executions.status = 'not_actioned'` and **do not** create new
dead-letter rows. Existing backlog rows must not be deleted or silently mutated.

## Identify (read-only)

Use the existing list filters — no new tooling required:

```http
GET /dead-letters?failure_class=approval_expired&status=open
GET /dead-letters?failure_class=approval_denied&status=open
```

Optional metrics cross-check:

```http
GET /metrics/dead-letters
```

Inspect `by_failure_class` for `approval_expired` / `approval_denied` counts while
`status=open`.

## Review each row

For each matched open dead letter:

1. Confirm `failure_class` is `approval_expired` or `approval_denied`.
2. Confirm the linked playbook execution / approval record matches an
   expected unattended approval window (not a genuine adapter/worker bug).
3. Do **not** retry these rows — they are permanently non-retryable by design.

## Dismiss (per-row, reason-logged)

Use the existing single-row dismiss endpoint only:

```http
POST /dead-letters/<id>/dismiss
Content-Type: application/json

{
  "reason": "expected approval-window expiration/denial; pre-dates not_actioned reclassification"
}
```

Requirements preserved by the existing endpoint:

- RBAC (existing dead-letter dismiss gate)
- Non-empty reason
- Per-row audit trail via `mark_dead_letter_dismissed`

## Explicit non-goals

- No bulk deletion
- No mass silent status rewrite
- No automatic cleanup job
- Optional bulk-dismiss-by-filter convenience (OpenSpec task 2.9) is **not**
  implemented unless separately and explicitly requested
