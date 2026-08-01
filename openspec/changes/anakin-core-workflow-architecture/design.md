## Context

The current Anakin backend has shared low-level routes (`/ai/explain`, `/ai/chat`, `/ai/drafts`, `/ai/investigations`, `/ai/repo/chat`) but the product semantics are still driven by action strings such as `why_important`, `summarize_activity`, `recommend_next_steps`, and `investigate_cluster`. This change keeps those routes as compatibility adapters while making a new workflow orchestrator the authoritative path for classification, routing, validation, metadata, and inventory.

## Architecture

Add `core.ai.workflow_orchestrator` as the single entry point for canonical Anakin workflows. It owns:

- request envelope validation;
- trusted workflow classification for `workflow=auto`;
- compatibility mapping from legacy routes/action IDs to canonical workflows;
- workflow metadata and lifecycle stage envelopes;
- dispatch to separate engines/services.

The orchestrator does not implement one giant AI service. It delegates:

- `quick_explain` to the existing explainer engine;
- `deep_investigate` to the existing investigation engine with lifecycle metadata;
- `decision_support` to a dedicated recommendation wrapper over the explainer prompt path;
- `generate_artifact` to the existing drafting engine;
- `soc_briefing` to existing briefing service/job contracts only from explicit briefing routes;
- `repo_assistant` to existing repo assistant service only from explicit repo routes.

## Request Envelope

All canonical workflow calls use a small shared envelope:

```json
{
  "workflow": "auto",
  "prompt": "What should I do about this alert?",
  "surface": "alert_details",
  "context_type": "alert",
  "entity": {"alert_id": 1001, "source_ip": "203.0.113.77"},
  "context": {},
  "artifact": {"type": "incident_note"},
  "tool_policy": {"max_tool_calls": 5, "time_window_hours": 24},
  "client_request_id": "optional-client-id"
}
```

Only `workflow`, `context_type`, and either `prompt` or workflow-specific payload are required at the envelope level. Workflow engines keep their existing stricter validation. Client-supplied `model`, `profile`, `timeout`, `provider`, and mutation fields are ignored for routing and cannot affect execution.

## Response Envelope

Canonical responses add a consistent workflow envelope around existing payloads:

```json
{
  "status": "success",
  "workflow": "decision_support",
  "classification": {
    "requested_workflow": "auto",
    "classified_workflow": "decision_support",
    "confidence": "high",
    "reason": "Prompt asks what action the analyst should choose."
  },
  "lifecycle": {"mode": "sync", "stage": "complete", "stages": []},
  "result": {},
  "metadata": {}
}
```

Compatibility routes continue returning their legacy body shape, but include canonical `workflow` and `classification` metadata where practical.

## Auto-Routing

`workflow=auto` may classify only to:

- `quick_explain`
- `deep_investigate`
- `decision_support`
- `generate_artifact`

It must never silently route to `soc_briefing`, `repo_assistant`, `/ai/actions/preview`, or `/ai/actions/confirm`.

Classification is deterministic and auditable. Low confidence defaults to `quick_explain` unless the prompt clearly requests a forbidden or ambiguous capability, in which case the orchestrator returns `chooser_required` with allowed workflow options.

## Workflow Contracts

### Quick Explain

- Context: `context_type`, optional `entity`, optional bounded `context`, prompt up to the existing explain limit.
- Output: concise explanation, evidence/limitations when available, legacy explain payload compatibility.
- Validation: existing context builder validation and explain action allowlist.
- Failure: insufficient context returns successful degraded response with missing context reason; provider errors preserve existing status.
- Budget/profile: `fast_triage`, existing profile prompt/output limits.
- Lifecycle: synchronous.
- Latency target: p50 under 3s, p95 under 8s when the configured local model is warm.

### Deep Investigate

- Context: domain object or workspace context plus bounded tool policy.
- Output: analysis with support, contradiction/benign possibilities, missing evidence, confidence, citations/tool evidence, read-only next steps.
- Validation: existing investigation planner/context/tool validation.
- Failure: returns degraded/partial/failed statuses without claiming unavailable evidence was checked.
- Budget/profile: `guided_analysis`, existing guided prompt/output limits.
- Lifecycle: polling-capable. Initial implementation may complete synchronously but must expose truthful stages: `gathering_context`, `retrieving_related_evidence`, `querying_approved_tools`, `preparing_evidence`, `generating_analysis`, `validating_response`, `complete`.
- Latency target: first lifecycle state under 1s; completion target under 45-90s depending on local model/tool latency.

### Decision Support

- Context: same as explain/investigation depending on surface.
- Output: recommendation (`block`, `monitor`, `escalate`, `ignore`, or `gather_more_evidence`), reasoning, confidence, prerequisites, risks, alternatives, and missing evidence.
- Validation: rejects artifact types and mutation/confirmation fields.
- Failure: degrades to `gather_more_evidence` when evidence is insufficient.
- Budget/profile: `guided_analysis`.
- Lifecycle: synchronous.
- Latency target: p50 under 6s, p95 under 15s.

### Generate Artifact

- Context: `artifact.type`, context type/entity, instruction/prompt.
- Output: existing strict structured draft schema plus workflow metadata.
- Validation: existing draft schemas and exactly one bounded repair attempt.
- Failure: unsupported type, invalid context, parse failure, validation failure, or insufficient context preserve existing draft failure statuses.
- Budget/profile: `guided_analysis`.
- Lifecycle: synchronous.
- Latency target: p50 under 8s, p95 under 20s.

### SOC Briefing

- Context: explicit SOC briefing route/job only; schedule/window/run context.
- Output: existing structured briefing sections, evidence refs, delivery status, and lifecycle.
- Validation: existing briefing controls, worker readiness, RBAC, and integration guards.
- Failure: existing blocked/partial/failed lifecycle states.
- Budget/profile: `deep_briefing`.
- Lifecycle: existing job polling/control lifecycle.
- Latency target: job-based, not interactive.

### Repo Assistant

- Context: explicit repo route only, super-admin, natural-language repo question, optional refresh.
- Output: cited answer, retrieval metadata, insufficient-evidence behavior.
- Validation: existing repo evidence and citation validation.
- Failure: existing insufficient evidence/provider failure statuses.
- Budget/profile: `developer_assistant`.
- Lifecycle: synchronous.
- Latency target: p50 under 8s, p95 under 20s without index refresh.

## Compatibility

Legacy routes remain available:

- `/ai/explain` maps action IDs to `quick_explain` or `decision_support`.
- `/ai/chat` maps to `quick_explain` unless classification clearly chooses another allowed normal workflow.
- `/ai/drafts` maps to `generate_artifact`.
- `/ai/investigations` maps to `deep_investigate`.
- `/ai/repo/chat` remains explicit `repo_assistant`.
- SOC briefing routes remain explicit `soc_briefing`.
- `/ai/actions/preview` and `/ai/actions/confirm` remain outside generation workflows.

## Non-Goals

- No frontend button removal or redesign.
- No SSE/WebSockets.
- No model installation, runtime configuration, migrations, deployment, VM access, commit, or push.
