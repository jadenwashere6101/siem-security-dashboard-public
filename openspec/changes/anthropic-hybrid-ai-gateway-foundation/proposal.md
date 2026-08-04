## Why

Local Ollama remains appropriate for bounded, simpler AI workloads, but the existing local planner models do not meet the reasoning and latency requirements of the validated Anakin planning contract. The provider-neutral AI Gateway already reserves an Anthropic provider slot, but it lacks a real adapter, profile-owned provider selection, durable paid-usage controls, and runtime administration needed to enable hybrid inference safely.

## What Changes

- Add Anthropic as a first-class AI provider through the existing `AiProvider` abstraction while leaving Ollama behavior unchanged.
- Extend backend-owned AI profiles to select both provider and model, with the gateway remaining the only routing authority and clients unable to choose either.
- Route `agentic_planning` proposal and repair calls to Anthropic while preserving Ollama-only assignments for `fast_triage`, `guided_analysis`, `deep_briefing`, and `developer_assistant`.
- Preserve planner-owned language understanding, strict validation, one-repair limit, workflow orchestration, evidence grounding, and async execution boundaries.
- Add gateway-owned daily paid-API budget enforcement, provider/token/cost/latency accounting, UTC-day lazy reset, and fail-closed accounting behavior.
- Add PostgreSQL-backed runtime gateway policy using the established detection and pfSense configuration patterns, including super-admin RBAC, immediate effect, validation, audit logging, `updated_by`, and `updated_at`.
- Extend `/ai/status` with sanitized provider/profile routing, readiness, and budget observability.
- Require browser-path production acceptance and an explicit forced-budget-exhaustion scenario before hybrid inference is accepted.

## Capabilities

### New Capabilities

- `anthropic-hybrid-ai-gateway`: Anthropic provider execution, paid-usage accounting and budget enforcement, runtime gateway administration, sanitized observability, and hybrid acceptance requirements.

### Modified Capabilities

- `ai-gateway-foundation`: Extend provider-neutral routing from global local-first fallback to backend-owned profile provider selection with paid-use enforcement.
- `ai-model-profile-routing`: Add provider ownership and explicit provider/model assignments to every approved AI profile.
- `anakin-agentic-analyst-planner`: Replace the planner profile's local-provider requirement with Anthropic execution while preserving the existing plan, validation, repair, and orchestration contracts.

## Impact

- Backend: AI provider/config/profile/gateway/readiness models, planner integration metadata, startup validation, runtime configuration services, accounting persistence, audit integration, and focused acceptance coverage.
- API/UI: additive sanitized `/ai/status` fields and a super-admin runtime gateway administration surface; clients still cannot influence routing.
- Database: future implementation will require additive durable runtime-policy and usage-accounting persistence; credentials remain environment-only.
- Runtime: the backend and relevant workers require protected Anthropic credentials and consistent shared configuration. Existing Ollama/Mini-PC paths remain supported and unchanged for their assigned profiles.
- Deployment: specification only in this change-creation task; future implementation and production rollout require separate authorization and the documented Mac-to-VM acceptance process.
