## 1. OpenSpec

- [x] 1.1 Create proposal, design, spec, and tasks.
- [x] 1.2 Validate `repo-assistant-async-execution` strictly before implementation.

## 2. Backend Async Repo Assistant

- [x] 2.1 Add repo request queue/read service using existing durable request store where safe.
- [x] 2.2 Add `POST /ai/repo/requests` and `GET /ai/repo/requests/<id>` with super-admin RBAC.
- [x] 2.3 Preserve immediate live-SIEM boundary response without queueing or retrieval.
- [x] 2.4 Extend worker dispatch and lifecycle stages for `repo_assistant`.
- [x] 2.5 Preserve repo citations, developer_assistant profile, no-paid-fallback, and repo/live-SIEM boundary behavior.

## 3. Frontend Polling

- [x] 3.1 Update repo assistant service to queue and poll repo requests.
- [x] 3.2 Update Repo Architecture Assistant panel loading/progress/error behavior.
- [x] 3.3 Add remount recovery and duplicate-submit protection.
- [x] 3.4 Preserve immediate boundary rendering.

## 4. Tests

- [x] 4.1 Add backend tests for queue, completion, boundary no-job, citations, RBAC, duplicate requests, timeout/stale recovery.
- [x] 4.2 Add frontend service/panel tests for polling, boundary, remount recovery, duplicate protection, and errors.
- [x] 4.3 Run deployment-script contract tests if worker wiring changes.

## 5. Verification

- [x] 5.1 Run Python compilation for modified backend files.
- [x] 5.2 Run focused backend and PostgreSQL-backed async tests.
- [x] 5.3 Run affected frontend tests and production build.
- [x] 5.4 Run offline acceptance harness.
- [x] 5.5 Run `git diff --check`.
- [x] 5.6 Run strict OpenSpec validation.
- [x] 5.7 Capture `git status --short`.
