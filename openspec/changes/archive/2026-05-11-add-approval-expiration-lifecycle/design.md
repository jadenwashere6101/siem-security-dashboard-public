# Design: Approval Expiration + Lifecycle Cleanup (Phase 2.5D)

---

## Required design analysis

### Transaction boundaries

**`expire_pending_requests(conn)`** operates inside a `with conn.cursor() as cur:` block.
It does not call `conn.commit()`. The caller owns the transaction boundary.

`GET /approvals` and `GET /approvals/<id>` are not modified. Both routes remain read-only.

**In `POST /admin/soar/approvals/expire-pending`:**
```
conn.commit()   # after expire_pending_requests + sweep_terminal_approval_queue_rows
```
Both functions write in the same transaction. One commit covers both. If either fails,
roll back both. The endpoint returns 500 on exception.

---

### Race conditions between worker approval checks and expiration

**Scenario A: two concurrent calls to `POST /admin/soar/approvals/expire-pending`.**

`expire_pending_requests` uses `FOR UPDATE SKIP LOCKED` on `approval_requests`. If two calls
run simultaneously:
- Call 1 locks rows with `expires_at <= now`.
- Call 2 receives the same query but `SKIP LOCKED` skips the rows already locked by Call 1.
- Call 2 processes whatever is left (possibly nothing, if Call 1 claimed all).
- Both commit cleanly. No row is processed twice.

`sweep_terminal_approval_queue_rows` uses `FOR UPDATE OF q SKIP LOCKED` on
`response_actions_queue`. Same guarantee: two concurrent sweeps cannot double-process a row.

This is safe by construction — `FOR UPDATE SKIP LOCKED` was designed for exactly this.

**Scenario B: admin endpoint runs `expire_pending_requests` while the worker is running `_handle_approval_gate` for the same approval.**

Worker path in `_handle_approval_gate`:
1. Calls `expire_pending_requests(conn, now=now)` — this is where it can race.
2. Then calls `get_latest_approval_for_queue_action` to read the current approval state.

The worker's `conn` and the admin endpoint's `conn` are separate connections.
If the admin endpoint's `expire_pending_requests` call wins the `FOR UPDATE SKIP LOCKED`
lock on an approval row, the worker's call sees 0 rows for that row (SKIP LOCKED). Then:
- The worker reads `get_latest_approval_for_queue_action` → sees `status: "expired"` (already committed by the endpoint).
- The worker proceeds to `mark_action_skipped` on the queue row.
- This is the correct outcome: the worker properly handles the `expired` state.

If the worker's `expire_pending_requests` wins the lock instead:
- The worker materializes expiration, commits.
- The endpoint's call skips the row (already not `pending`), continues.
- Correct outcome either way.

**Scenario C: worker calls `claim_next_approved_awaiting_action` while `sweep_terminal_approval_queue_rows` runs.**

`claim_next_approved_awaiting_action` uses:
```sql
WHERE q.status = 'awaiting_approval'
  AND EXISTS (SELECT 1 FROM approval_requests WHERE ... AND approval.status = 'approved')
```
It only claims rows with `status = 'approved'`. The sweep only skips rows with
`status IN ('denied', 'expired')`. These predicates are disjoint — they cannot compete
for the same queue row.

If an approval transitions from `pending → approved` at the same moment the sweep runs:
- Sweep query uses `FOR UPDATE OF q SKIP LOCKED` with `approval.status IN ('denied', 'expired')`.
- An `approved` approval does not satisfy the sweep's predicate.
- No interference.

**Conclusion:** all scenarios are safe. The existing `SKIP LOCKED` strategy on both
`approval_requests` and `response_actions_queue` tables is the correct foundation.

---

### Retry count invariants

`retry_count` must never be incremented for queue rows transitioned by approval expiration.

**Current paths that increment `retry_count`:** only `mark_action_failed`:
```python
SET status = 'failed',
    retry_count = retry_count + 1,
    last_error = %s
```

**Paths this phase uses:**
- `mark_awaiting_approval_skipped` → calls `_transition_action_status(from_status='awaiting_approval', to_status='skipped')` → does NOT touch `retry_count`.
- `skip_next_terminal_approval_action` → its UPDATE sets `status = 'skipped'` and `last_error` — no `retry_count` increment.
- New `sweep_terminal_approval_queue_rows` — must mirror `skip_next_terminal_approval_action`: set `status = 'skipped'`, set `last_error`, do NOT touch `retry_count`.

**Invariant:** a queue row in `awaiting_approval` that is transitioned to `skipped` via
approval expiration will have the same `retry_count` it had when it entered `awaiting_approval`.
The retry budget is preserved — if the system is later reconfigured to not require approval
for `block_ip`, the same IP could be queued again and have full retries available.

---

### Duplicate approval prevention

**When is a new approval created?** Only in `_handle_approval_gate`, in this branch:
```python
if approval is None:
    create_approval_request(...)
    mark_action_awaiting_approval(...)
```

A new approval is only created if `get_latest_approval_for_queue_action(conn, queue_id=..., action=...)` returns `None`. That function returns the most recent approval for the `(queue_id, action)` pair. An `expired` approval is not `None` — it is a record with `status: 'expired'`.

After expiration:
- `get_latest_approval_for_queue_action` returns the expired record.
- The worker hits the `else` branch:
  ```python
  reason = "approval expired"
  updated = mark_action_skipped(conn, row["id"], reason, now=now)
  ```
- The queue row transitions to `skipped`. No new approval is created.

**This phase does not change this logic.** The worker's duplicate-prevention behavior is
unchanged. Expiration materializing via the read path only moves `pending → expired` on the
approval table — it does not create new records.

**Edge case: what if the admin calls `POST /admin/soar/approvals/expire-pending` and
immediately after the worker processes the same queue row?**

- The endpoint expires the approval and sweeps the queue row to `skipped` in one commit.
- The worker's `skip_next_terminal_approval_action` (or `_handle_approval_gate`) looks for
  `awaiting_approval` rows with terminal approvals.
- If the queue row is already `skipped`, the worker finds nothing for it — the `WHERE q.status = 'awaiting_approval'` predicate excludes it.
- Safe. Idempotent.

---

### How expiration interacts with approved/denied requests

`expire_pending_requests` uses:
```sql
WHERE status = 'pending' AND expires_at <= %s
```
It only touches `pending` rows past their TTL. `approved` and `denied` rows are never touched.

`approve_request` and `deny_request` check expiry at decision time (`row[13] <= decision_time`
where `row[13]` is `expires_at`). If a super_admin submits a decision for an overdue-but-still-
`pending` approval (because expiration hasn't been materialized yet), the decision function
materializes expiration itself and raises `ValueError("approval request expired")`. The route
returns 400.

The approval route's decision endpoint behavior is not changed by this phase.
A super_admin who submits a decision for an approval that has passed its TTL but was not yet
materialized will receive a 400 from the decision route — this is unchanged behavior. Running
`POST /admin/soar/approvals/expire-pending` before deciding will materialize the expiration
and surface the correct `expired` state in the UI before the decision is attempted.

---

### Where cleanup belongs: worker path vs. admin path vs. standalone runner

**Worker path (current behavior, unchanged):**
`process_next_action` calls `expire_pending_requests` when no `pending` row is available.
It calls `skip_next_terminal_approval_action` as a last step before returning None.
This is opportunistic — it fires when a super_admin manually runs the worker via
`POST /admin/soar/worker/run-once`.

**Decision: preserve worker path as-is.** Changing it creates risk without benefit.

**Admin read path (NOT this phase):**
`GET /approvals` and `GET /approvals/<id>` remain read-only. Expiration is an explicit
operational action, not a side effect of reading. The UI may show stale `pending` state
until the admin endpoint or worker runs. This is an acceptable tradeoff — GET routes with
write side effects are semantically surprising and harder to reason about under concurrent
load. A future phase could revisit if the operational burden becomes significant.

**Standalone admin endpoint (new behavior, this phase):**
`POST /admin/soar/approvals/expire-pending` is the operational cleanup tool. It:
1. Expires all overdue pending approvals (batch).
2. Sweeps all `awaiting_approval` queue rows with terminal approvals to `skipped` (batch).

This is the only path that cleans up both the approval records AND the linked queue rows in
a single explicit operation. An operator runs it when they want to confirm the system is
clean — after a long idle period, after a deployment, or before starting Phase 3 real adapters.

**Decision: add the admin endpoint. Keep it `super_admin_required`. Co-locate with other
`POST /admin/soar/*` endpoints in `admin_routes.py`.**

**Standalone runner process (out of scope):**
Not added. No daemon, no cron, no subprocess. The two paths above (worker + admin endpoint)
cover all operational needs without a scheduler.

---

## New component: `sweep_terminal_approval_queue_rows(conn, *, now=None, limit=100)`

Location: `core/response_action_queue_store.py`

This is a batch version of `skip_next_terminal_approval_action`. Where that function
processes exactly one row, this function processes all eligible rows up to `limit`.

```python
def sweep_terminal_approval_queue_rows(conn, *, now=None, limit=100):
    """
    Transition all awaiting_approval queue rows whose latest linked approval
    is terminal (denied or expired) to skipped status, in a single batch.

    Does not commit. Caller commits.
    Returns a list of transitioned queue row dicts.
    """
    cap = min(max(int(limit), 0), 100)

    with conn.cursor() as cur:
        cur.execute(
            f"""
            WITH candidates AS (
                SELECT q.id,
                       approval.status AS approval_status
                FROM response_actions_queue q
                JOIN LATERAL (
                    SELECT status
                    FROM approval_requests
                    WHERE queue_id = q.id
                      AND action = q.action
                    ORDER BY created_at DESC, id DESC
                    LIMIT 1
                ) approval ON TRUE
                WHERE q.status = 'awaiting_approval'
                  AND approval.status IN ('denied', 'expired')
                ORDER BY q.id
                FOR UPDATE OF q SKIP LOCKED
                LIMIT %s
            )
            UPDATE response_actions_queue AS queue
            SET status = 'skipped',
                last_error = CASE
                    WHEN candidates.approval_status = 'denied' THEN 'approval denied'
                    ELSE 'approval expired'
                END,
                updated_at = COALESCE(%s::timestamptz, NOW())
            FROM candidates
            WHERE queue.id = candidates.id
            RETURNING queue.id, queue.alert_id, host(queue.source_ip), queue.action,
                      queue.status, queue.retry_count, queue.max_retries,
                      queue.last_error, queue.idempotency_key,
                      queue.created_at, queue.updated_at,
                      candidates.approval_status
            """,
            (cap, now),
        )
        rows = cur.fetchall()
        result = []
        for row in rows:
            queue_row = _queue_row_from_record(row[:11])
            queue_row["approval_status"] = row[11]
            result.append(queue_row)
        return result
```

Key properties:
- Mirrors the SQL structure of `skip_next_terminal_approval_action` exactly, adding `LIMIT %s`
  and removing `LIMIT 1`.
- `FOR UPDATE OF q SKIP LOCKED` prevents concurrent sweeps from double-processing rows.
- No `retry_count` increment — only `status` and `last_error` are updated.
- Does not commit — caller owns the transaction.

---

## New endpoint: `POST /admin/soar/approvals/expire-pending`

Location: `routes/admin_routes.py`

Auth: `super_admin_required` (consistent with all other `POST /admin/soar/*` endpoints).

```python
@admin_bp.route("/admin/soar/approvals/expire-pending", methods=["POST"])
@limiter.limit("10 per minute")
@login_required
@super_admin_required
def expire_pending_approvals():
    """
    Manually expire all overdue pending approvals and sweep linked queue rows to skipped.
    """
    conn = None
    try:
        conn = get_db_connection()
        expired = expire_pending_requests(conn)
        swept = sweep_terminal_approval_queue_rows(conn)
        conn.commit()
        return jsonify({
            "expired_approvals": len(expired),
            "skipped_queue_rows": len(swept),
            "expired_approval_ids": [r["id"] for r in expired],
            "skipped_queue_ids": [r["id"] for r in swept],
        }), 200
    except Exception:
        if conn:
            conn.rollback()
        current_app.logger.exception("Error in expire_pending_approvals")
        return jsonify({"error": "Unable to expire approvals"}), 500
    finally:
        if conn:
            conn.close()
```

Add imports at the top of `admin_routes.py`:
```python
from core.approval_store import expire_pending_requests
from core.response_action_queue_store import sweep_terminal_approval_queue_rows
```

Rate limit is `10 per minute` — stricter than queue reads (30/min) because this is a write
operation. An operator will call it once, not in a loop.

---

## State transition diagrams

### Approval request

```
pending  ──(expires_at <= now, worker or admin endpoint)──▶  expired  (terminal)
pending  ──(super_admin approves, expires_at > now)───────▶  approved (terminal)
pending  ──(super_admin denies,  expires_at > now)────────▶  denied   (terminal)
```

`expired`, `approved`, and `denied` are all terminal. No transitions out of them.

`approve_request` and `deny_request` check expiry at decision time and will materialize
`expired` and raise rather than allowing the decision if `expires_at <= decision_time`.

### Queue row (approval-gated path)

```
pending  ──(worker claims)──▶  running  ──(_handle_approval_gate: no approval)──▶  awaiting_approval
                                                                                      │
        ┌─────────────────────────────────────────────────────────────────────────────┤
        │                                                                             │
        ├──(linked approval: approved)──▶  running  ──(executor)──▶  success         │
        │                                                                             │
        ├──(linked approval: denied or expired)──▶  skipped                          │
        │   via worker skip_next_terminal_approval_action  OR                         │
        │   via sweep_terminal_approval_queue_rows (this phase)                       │
        │                                                                             │
        └─────────────────────────────────────────────────────────────────────────────┘
```

`retry_count` is never incremented on any `awaiting_approval → skipped` path.

---

## Operational flow: manual cleanup

When an operator wants to ensure the system is in a clean state (e.g., before enabling real
adapters in Phase 3):

```
POST /admin/soar/approvals/expire-pending
→ { "expired_approvals": 3, "skipped_queue_rows": 3, ... }
```

Then:
```
GET /admin/soar/queue/status
→ counts.awaiting_approval should be 0 (all swept)
→ counts.skipped will have increased
```

Then:
```
GET /approvals?status=expired
→ should show the 3 expired approvals
```

All three steps are read-or-idempotent-write. Running the endpoint a second time returns
`{ "expired_approvals": 0, "skipped_queue_rows": 0 }` — nothing left to process.

---

## Failure handling

| Failure point | Effect | Recovery |
|---|---|---|
| `expire_pending_requests` fails in admin endpoint | 500 returned, rolled back | Caller retries endpoint |
| `sweep_terminal_approval_queue_rows` fails in admin endpoint | 500 returned, rolled back | Caller retries endpoint; approvals may already be expired from a prior partial call — sweep processes them on retry |
| DB connection failure in admin endpoint | 500 returned, rolled back | Standard |
| Concurrent calls to admin endpoint | SKIP LOCKED prevents double-processing; idempotent | No special handling needed |

---

## Files changed summary

| File | Change |
|---|---|
| `core/response_action_queue_store.py` | Add `sweep_terminal_approval_queue_rows(conn)` |
| `routes/admin_routes.py` | Add imports; add `POST /admin/soar/approvals/expire-pending` endpoint |
| `tests/test_soar_worker_admin_run_control.py` | Tests for new admin endpoint |
| `tests/test_response_action_queue_store.py` | Tests for `sweep_terminal_approval_queue_rows` |

No schema changes. No frontend changes. No worker changes. No changes to `approval_routes.py`.

---

## Risks and stop conditions

**Risk 1: `sweep_terminal_approval_queue_rows` and `skip_next_terminal_approval_action` coexist.**
Both functions touch the same rows (`awaiting_approval` with terminal approvals). They are
not mutually exclusive — both can remain in the codebase.
- The worker continues to use `skip_next_terminal_approval_action` (one at a time, in its
  normal flow).
- The admin endpoint uses `sweep_terminal_approval_queue_rows` (batch, on demand).
- Neither function creates a transition conflict because `FOR UPDATE SKIP LOCKED` ensures
  a row is only processed by one caller at a time.

**Risk 2: `expired_approval_ids` list in the admin response may be large.**
The endpoint returns full ID lists. If many approvals expire simultaneously (e.g., after
a long idle period), the response body could include hundreds of IDs.
- Mitigation: `expire_pending_requests` is capped at `limit=100`. The sweep is also capped
  at `limit=100`. Maximum response: 100 approval IDs + 100 queue IDs. Acceptable.

**Risk 3: UI shows stale `pending` state until the admin endpoint is called.**
`GET /approvals` is read-only. An analyst viewing the approvals panel will see approvals as
`pending` even after their TTL has passed, until a super_admin triggers
`POST /admin/soar/approvals/expire-pending` or the worker runs. This is a known and
accepted tradeoff — the alternative (writing on read) was explicitly removed from scope.
- Mitigation: operators should call the endpoint before reviewing pending approvals for
  cleanup decisions. The `expires_at` field is visible in the UI and provides the ground
  truth regardless of materialized status.

**Risk 4: `expire_pending_requests` index coverage.**
The query `WHERE status = 'pending' AND expires_at <= now` benefits from an index on
`(status, expires_at)`. This applies to the admin endpoint, not a GET route, so the impact
is lower — the endpoint is called explicitly, not on every page load. Still, verify the
index exists in `schema.sql` before implementing. The `approval_requests` table has 7
indexes per the handoff document — confirm coverage before writing the endpoint.

**Risk 5: DB user for the admin sentinel (pre-existing risk, not introduced here).**
The handoff document notes that `approved_by IS NOT NULL` is a DB CHECK constraint and that
the hardcoded `testadmin` sentinel has no `users` row. This is not affected by expiration
paths — expiration writes `approved_by = NULL` and `decided_by = NULL`, which satisfies any
non-null constraint. Not a risk for this phase.
