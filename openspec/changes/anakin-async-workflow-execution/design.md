# Design: Anakin Async Workflow Execution

## Durable Job Model

Add a narrow `ai_workflow_requests` table for queued Anakin workflows. It is separate from SOC briefing tables because interactive Anakin requests have different lifecycles, UI ownership, idempotency semantics, and workflow contracts.

Each row stores:

- immutable request identity: workflow, context type, sanitized request envelope, idempotency key, created actor;
- lifecycle state: queued, running, completed, partial, degraded, failed, timed_out;
- truthful stage: gathering_context, retrieving_evidence, querying_tools, preparing_evidence, generating_analysis, validating_response, complete;
- lease/claim metadata: lease owner, acquired/heartbeat/expires timestamps, attempt/retry counts;
- response data: canonical workflow result envelope, metadata, failure code/message, timestamps.

One idempotency key may have at most one active non-terminal request. Repeated queue requests for the same actor/key return the existing active request instead of creating duplicate work.

## API Contract

`POST /ai/workflows/requests`

- Requires authenticated analyst or super-admin.
- Accepts the existing canonical workflow request envelope.
- Classifies `workflow="auto"` before choosing execution mode.
- Queues `deep_investigate`, `decision_support`, and `generate_artifact`.
- Returns an immediate non-queued Quick Explain result when `workflow="auto"` classifies to `quick_explain`.
- Returns a chooser immediately for low-confidence auto classification without creating a job.
- Rejects explicit Quick Explain, SOC Briefing, Repo Assistant, preview/confirm, and mutation fields.
- Validates classification and workflow safety synchronously before creating durable work.
- Persists the sanitized request envelope and returns quickly with request ID and initial lifecycle.

`GET /ai/workflows/requests/<id>`

- Requires authenticated analyst or super-admin.
- Returns the current canonical polling envelope: status, workflow, classification, lifecycle, result/error, metadata, timestamps, and read-only labels.
- Does not execute AI work.
- Hides lease owner and secret-bearing request details.

Existing `POST /ai/workflows` remains available for synchronous compatibility and explicit Quick Explain. New consolidated frontend interactions use the queue-capable API for `workflow="auto"` and for the three long workflows so backend-classified deep requests cannot sit behind nginx as long synchronous requests.

## Worker Execution

Add a bounded worker entry point and service wrapper. The worker:

- recovers stale running jobs in a bounded pass;
- claims queued jobs with row locking and a lease;
- executes one canonical workflow at a time through existing workflow engines;
- renews lifecycle stage/status around deterministic phases;
- records canonical result envelopes and terminal status;
- records failure codes/messages without leaking secrets;
- bounds retries and marks exhausted stale jobs failed/timed_out;
- never calls preview/confirm, SOC briefing routes, repo routes, or production mutation paths.

Worker runtime must exceed the guided-analysis/provider timeout with margin. Runtime configuration is documented for later VM deployment but not changed in this implementation.

## Frontend Polling UX

The consolidated workflow controls route Deep Investigate, Decision Support, and Generate Artifact through the queue endpoint. The UI stores active request IDs by stable context/workflow key in session storage, polls until terminal, and renders the same `AiResponsePanel` result shape once completed.

During polling, the panel shows:

- queued/running state;
- truthful backend lifecycle stage;
- elapsed time;
- specific errors for worker unavailable, provider unavailable, provider timeout, workflow timeout, context/prompt limit, validation failure, authorization, and network/proxy failures.

Quick Explain stays synchronous except for shared error-message improvements.

## Safety Boundaries

Decision Support remains recommendation-only. Generate Artifact remains preview/non-persistent generation with strict schema validation and one bounded repair attempt. Results must expose `persisted=false` and `applied=false` when draft payloads include those flags. No async workflow may persist drafts, apply actions, confirm mutations, use paid fallback, or bypass RBAC.

## Deployment Handoff

Later VM work must apply migration `0031`, install and enable the Anakin workflow worker unit/timer through `scripts/deploy_backend_vm.sh`, verify worker heartbeat/logs/status, and run the production acceptance policy through nginx `/siem/`.
