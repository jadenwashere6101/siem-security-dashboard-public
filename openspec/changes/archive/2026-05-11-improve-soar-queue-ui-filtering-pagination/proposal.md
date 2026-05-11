# Proposal: Improve SOAR Queue UI Filtering and Page Size

## Problem

The SOAR Queue UI provides operational visibility, detail inspection, and a
manual simulation run control. The recent queue list is still limited in
usability when admins need to focus on a specific status or inspect a smaller or
larger set of recent rows.

The backend recent endpoint already supports status filtering and limit-based
page sizing, so the frontend can improve queue inspection without adding any
mutation behavior.

## Goal

Improve SOAR Queue UI usability by adding explicit read-only controls for:

- status filter:
  - all
  - pending
  - running
  - success
  - failed
  - skipped
- page-size / limit selector:
  - 10
  - 25
  - 50
  - 100

Changing either control should refresh the recent queue rows using the existing
GET endpoint:

```text
GET /admin/soar/queue/recent
```

## Scope

In scope:

- status filter UI in `SoarQueuePanel`
- limit/page-size selector in `SoarQueuePanel`
- refresh recent queue rows when status or limit changes
- preserve selected detail behavior safely across list refreshes
- handle empty filtered results cleanly
- add or adjust targeted component tests for filtering and limit behavior
- frontend build verification

Out of scope:

- no retry/replay/cancel controls
- no worker execution changes
- no backend mutation endpoints
- no real firewall controls
- no ingest/detection/correlation changes
- no schema changes
- no backend endpoint changes unless absolutely required
- no cursor pagination or numbered pages in this phase

## Safety Requirements

- Filtering and page-size controls must be GET-only.
- No mutation buttons may be added.
- `idempotency_key` must remain hidden from list view.
- Empty filtered results must render a normal empty state.
- Detail view must remain read-only.
- Changing filters must not trigger worker execution.

## Success Criteria

- Admins can filter recent queue rows by status.
- Admins can select a recent-row limit of 10, 25, 50, or 100.
- The UI calls the existing recent endpoint with the selected status and limit.
- Selected detail behavior remains stable and read-only.
- Component tests cover filter and limit interactions.
- Frontend build passes.
