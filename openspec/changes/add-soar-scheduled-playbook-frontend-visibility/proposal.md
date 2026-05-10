# Proposal: SOAR Scheduled Playbook Frontend Visibility

## Problem
Scheduled playbook metadata now exists in the backend, and read-only APIs expose schedule list and detail data. There is no frontend visibility for that metadata yet. Operators cannot inspect schedule IDs, linked playbooks, enabled/paused state, schedule expressions, next/last run fields, or missed-run policy from the UI.

Because no scheduler, daemon, or scheduled execution path exists, the frontend must make clear that schedules are metadata-only and do not execute anything yet.

## Goal
Add read-only frontend visibility for scheduled playbook metadata.

## Scope
- Add frontend service helpers for:
  - `GET /playbook-schedules`
  - `GET /playbook-schedules/<id>`
- Add read-only schedule UI in the existing Playbooks/SOAR area.
- Show schedule ID, `playbook_id`, enabled/paused state, schedule expression, `last_run_at`, `next_run_at`, missed-run policy, and safe metadata fields when present.
- Add loading, error, and empty states.
- Add focused frontend tests.

## Out of scope
- No implementation code in this change.
- No backend changes.
- No schema changes.
- No create, edit, or delete schedule UI.
- No pause or resume controls.
- No run-now controls.
- No scheduler implementation.
- No playbook execution from schedules.
- No executor or queue changes.
- No ingest, detection, or correlation changes.
- No real integrations.

## Success criteria
- Analysts and super-admins can inspect scheduled playbook metadata in the frontend where current SOAR/playbook visibility allows.
- The UI clearly states that schedules are metadata-only and do not execute yet.
- The UI shows loading, error, and empty states.
- The UI does not add mutation controls.
- Frontend tests verify service paths, rendering, error/empty states, and absence of run/pause/resume/create/edit/delete controls.

## Why this is safe
This is visibility only over existing read-only backend APIs. It does not introduce a scheduler, run playbooks, enqueue work, call adapters, mutate schedules, or imply autonomous execution exists.
