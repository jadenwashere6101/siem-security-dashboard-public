# Proposal: SOAR Operations UI

## Problem

The backend SOAR platform is complete through the dead letter queue. Every SOAR operation — dead letter review, execution retry, approval decisions, circuit breaker controls, worker invocation — requires direct API calls. There is no frontend interface for the dead letter queue at all. The PlaybooksPanel execution detail lacks dead letter linkage and lease/recovery context. Analysts and operators must use curl, Postman, or scripts for all super_admin mutations.

This creates an operational gap:

- Failed playbook executions write dead letters to `soar_dead_letters` but no UI shows them. Operators have no review queue, backlog gauge, or action surface.
- Retry decisions (dismiss, retry-request, retry-execute) must be made via raw POST calls with no context about what failed, what the linked incident/alert is, or what the current dead letter status is.
- PlaybooksPanel shows execution detail but does not surface whether a dead letter exists for a failed execution, or show lease/recovery fields that help distinguish stale vs. permanently failed rows.
- The existing ApprovalsPanel and IncidentsPanel are functional but are not linked to dead letter state, making it harder to trace a failure from incident → execution → dead letter and back.

## Goal

Add analyst-facing and super_admin-facing SOAR Operations UI using existing backend APIs. No new backend behavior is introduced. The primary deliverable is a `DeadLettersPanel` with full review and action controls. Secondary deliverables are PlaybooksPanel execution detail improvements (dead letter linkage, lease/recovery fields) and a new "SOAR Operations" nav section that lands on the dead letter dashboard.

The change should:

1. Add `deadLetterService.js` wrapping existing dead letter APIs.
2. Add `DeadLettersPanel` — the first dedicated dead letter frontend.
3. Wire dismiss, retry-request, and retry-execute actions with correct role gating and safety copy.
4. Surface dead letter linkage in PlaybooksPanel execution detail.
5. Add lease/recovery field visibility to execution detail if the API exposes them.
6. Add a "SOAR Operations" nav tab in `App.js` that renders the dead letter panel.
7. Preserve existing panel architecture; no global rewrite of App.js.

## Scope

**In scope:**

- `frontend/src/services/deadLetterService.js` — new service wrapping GET/POST dead letter APIs.
- `frontend/src/components/DeadLettersPanel.js` — new component with list, detail, metrics, and action controls.
- `App.js` — add `soar-operations` section and nav tab; no other structural changes.
- `PlaybooksPanel.js` — add dead letter linkage in execution detail; add lease/recovery fields if API exposes them.
- `deadLetterService.test.js` and `DeadLettersPanel.test.js` — new test files.
- Optionally: `frontend/src/services/deadLetterService.test.js`.

**Out of scope:**

- No new backend routes, store helpers, or schema changes.
- No changes to ingest, detection, or correlation.
- No changes to ApprovalsPanel or IncidentsPanel beyond confirming they link correctly to existing execution/approval data.
- No new execution semantics — retry-execute creates a pending row only; the manual CLI still runs it.
- No real Slack/Teams/firewall actions.
- No daemon, scheduler, or background worker.

**Conditional backend change (read-only fields only):**

If `GET /playbook-executions/<id>` does not currently return lease fields (`lease_owner`, `lease_expires_at`, `recovery_count`), a minimal backend change to include them in the response is acceptable. This is strictly additive — no behavior change, no schema change. This must be verified before implementation and is a prerequisite only for the lease/recovery visibility sub-slice.

## Existing Backend APIs Used

| Endpoint | Method | Access | Purpose |
|---|---|---|---|
| `GET /dead-letters` | GET | analyst + super_admin | List dead letters with filters |
| `GET /dead-letters/<id>` | GET | analyst + super_admin | Dead letter detail |
| `GET /metrics/dead-letters` | GET | analyst + super_admin | Aggregate counts by status/source/failure_class |
| `POST /dead-letters/<id>/dismiss` | POST | analyst + super_admin | Dismiss open or retrying dead letter |
| `POST /dead-letters/<id>/retry-request` | POST | analyst + super_admin | Signal intent to retry; transitions open → retrying |
| `POST /dead-letters/<id>/retry-execute` | POST | super_admin only | Create new pending execution; transitions retrying → retried |
| `GET /playbook-executions` | GET | analyst + super_admin | Execution list for cross-linking |
| `GET /playbook-executions/<id>` | GET | analyst + super_admin | Execution detail for cross-linking |
| `GET /incidents/<id>` | GET | analyst + super_admin | Incident detail for cross-linking |

No new backend endpoints are required.

## Role Access Summary

| Action | Analyst | Super Admin |
|---|---|---|
| View dead letter list / detail / metrics | Yes | Yes |
| Dismiss (open or retrying) | Yes | Yes |
| Retry-request (open → retrying) | Yes | Yes |
| Retry-execute (retrying → retried) | No — hidden | Yes — with safety confirmation |
| View lease/recovery fields in execution detail | Yes (read-only) | Yes (read-only) |

## Why This Order

The dead letter queue is the highest-priority gap: backend complete, zero frontend coverage, operators must use raw API calls to review failed work. PlaybooksPanel execution detail improvements are additive to existing functionality. The nav integration is minimal (one new section in App.js, following the exact pattern of every existing section).
