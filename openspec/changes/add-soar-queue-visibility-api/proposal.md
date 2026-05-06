# Proposal: SOAR Queue Visibility API

## Problem

The SOAR queue and worker now exist, but queue health is only visible through
database inspection or tests. Admins need a read-only backend API to inspect queue
depth, recent queue items, and optionally a single queue item without running CLI
commands or touching the database directly.

This is operational visibility only. It must not mutate queue rows, retry work,
execute worker actions, or introduce frontend UI yet.

## Goal

Add admin-only read endpoints for SOAR queue visibility:

- `GET /admin/soar/queue/status`
- `GET /admin/soar/queue/recent`
- optional `GET /admin/soar/queue/<id>`

The endpoints should use existing queue store helpers where possible, preserve
queue state, handle nullable `alert_id`, and avoid exposing sensitive data.

## In Scope

- Backend read-only admin endpoints.
- Queue status counts.
- Recent queue item listing.
- Optional queue item detail.
- Serialization helpers for queue rows.
- Tests for auth, response shape, nullable `alert_id`, and no mutation.

## Out of Scope

- No queue retry/replay button.
- No worker execution endpoint.
- No frontend UI.
- No real firewall execution.
- No schema changes unless implementation proves they are absolutely necessary.
- No ingest/detection/correlation changes.
- No playbooks/incidents.
- No queue mutation from these endpoints.

## Security Requirements

- Must require login.
- Must require admin privileges using the existing admin guard pattern.
- Must not expose secrets.
- Must handle nullable `alert_id`.
- Must display deleted/missing alert references safely.
- Must not expose raw exception details in API responses.

## Success Criteria

- Unauthenticated callers receive `401`.
- Non-admin callers receive `403`.
- Admin callers can read status counts.
- Admin callers can read recent queue items.
- Queue rows with `alert_id = NULL` serialize with JSON `null` and a safe alert
  reference status.
- Calling visibility endpoints does not change queue status, retry counts, or
  timestamps.
- Existing queue worker behavior is unchanged.

