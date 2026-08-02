# Design

## Storage

Reuse the existing `ai_workflow_requests` table with a distinct `repo_assistant` workflow value. This keeps durable leases, idempotency, stale recovery, polling serialization, and worker deployment on the already-installed Anakin workflow worker path.

Separation is preserved in service and route layers:

- `/ai/repo/requests` requires super-admin authorization.
- `/ai/repo/requests/<id>` reads only the current actor's request.
- worker execution dispatches `repo_assistant` to `answer_repo_question`, not normal Anakin auto-classification.

The existing table uses check constraints for workflow and stage values, so this change includes the smallest schema migration to admit `repo_assistant` and repo-specific lifecycle stages. No table shape, index, or data-retention behavior changes.

## API

- `POST /ai/repo/requests`
  - validates auth and payload;
  - applies live-SIEM boundary detection first;
  - returns immediate `scope_boundary` response with no job when applicable;
  - otherwise queues durable `repo_assistant` request and returns `202`.

- `GET /ai/repo/requests/<id>`
  - returns queued/running/completed/failed/timed_out lifecycle;
  - returns answer, question type, citations, retrieval, metadata, timestamps, and exact error.

The legacy `/ai/repo/chat` route remains for compatibility in this phase.

## Worker

The existing Anakin workflow worker claims `repo_assistant` jobs and executes them under the saved actor context. Repo-specific truthful stages:

- `retrieving_repository_evidence`
- `preparing_repository_context`
- `generating_answer`
- `validating_citations`
- `complete`

No model call runs in the POST request.

## Frontend

`RepoArchitectureAssistantPanel` submits to `/ai/repo/requests`, handles immediate boundary responses, and polls queued repo requests until terminal.

It prevents duplicate submission while an equivalent request is active and stores enough request state to recover after component remount when safe.

## Boundaries

Repo Assistant remains super-admin only, repository scoped, and citation validated. Live SIEM-data questions return boundary guidance immediately and are not queued.
