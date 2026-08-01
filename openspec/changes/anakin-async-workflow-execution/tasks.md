## 1. OpenSpec

- [x] 1.1 Create proposal, design, spec, and tasks for `anakin-async-workflow-execution`.
- [x] 1.2 Run strict OpenSpec validation before implementation.

## 2. Backend Durable Jobs

- [x] 2.1 Add migration/schema snapshot for `ai_workflow_requests` with idempotency, lifecycle, result, failure, and lease fields.
- [x] 2.2 Add store helpers for create/get, claim, heartbeat/stage update, completion/failure, stale recovery, and safe serialization.
- [x] 2.3 Add async workflow worker service that executes Deep Investigate, Decision Support, and Generate Artifact through existing engines.
- [x] 2.4 Add documented worker runner and systemd wrapper/template without changing production runtime.

## 3. API

- [x] 3.1 Add `POST /ai/workflows/requests` to validate and queue long workflows quickly.
- [x] 3.2 Add `GET /ai/workflows/requests/<id>` to return polling lifecycle/result/error.
- [x] 3.3 Preserve synchronous `POST /ai/workflows` compatibility and Quick Explain behavior.

## 4. Frontend

- [x] 4.1 Route Deep Investigate, Decision Support, and Generate Artifact controls through the async queue API.
- [x] 4.2 Poll queued requests through terminal state, preserve context, prevent duplicate matching clicks, and recover active requests from session storage when safe.
- [x] 4.3 Render truthful progress, elapsed time, terminal results, and specific error messages without collapsing non-JSON failures to only `AI response unavailable`.
- [x] 4.4 Keep Quick Explain synchronous.

## 5. Tests And Acceptance

- [x] 5.1 Add backend tests for queue speed, duplicate idempotency, worker claim/complete, stale recovery, failures, and workflow safety.
- [x] 5.2 Add frontend tests for async queue/poll, remount recovery, duplicate prevention, specific errors, and Quick Explain sync behavior.
- [x] 5.3 Update acceptance coverage/contracts for async workflow lifecycle without removing legacy compatibility adapters.

## 6. Verification

- [x] 6.1 Run Python compilation for modified backend modules/scripts.
- [x] 6.2 Run focused backend tests.
- [x] 6.3 Run focused frontend tests and production build.
- [x] 6.4 Run offline AI acceptance harness.
- [x] 6.5 Run `git diff --check`.
- [x] 6.6 Run `openspec validate anakin-async-workflow-execution --strict`.
- [x] 6.7 Capture `git status --short`.

## 7. Deployment Correction: Auto Routing And Worker Install

- [x] 7.1 Allow `POST /ai/workflows/requests` to classify `workflow="auto"` before choosing immediate Quick Explain, chooser state, or queued long workflow execution.
- [x] 7.2 Route frontend freeform Ask Anakin auto requests through the queue-capable endpoint and handle immediate, chooser, and queued responses.
- [x] 7.3 Add idempotent Anakin workflow worker systemd installer and wire it into `scripts/deploy_backend_vm.sh`.
- [x] 7.4 Add backend, frontend, remount recovery, duplicate idempotency, restricted-workflow, and deployment-helper regression tests for the production defects.
