## Context

The SIEM backend is a Flask application that registers feature-specific blueprints in `siem_backend.py`. Routes are thin when the codebase is at its best: they apply `login_required` plus role decorators from `core.auth`, parse request input, call `core` or `engines` helpers, serialize JSON, and fail closed on exceptions. Sensitive actions use `core.audit_helpers.log_audit_event`, and database access flows through `core.db.get_db_connection`.

The closest existing provider pattern is the notification integration layer. `integrations/base_integration.py`, `integrations/integration_registry.py`, and the Slack/Teams/Email/Webhook adapters show useful conventions: provider registries, safe readiness metadata, explicit simulation/real modes, timeout env vars, fail-closed guard checks, circuit-breaker status, and secret-redacted logging. The SOAR action adapter layer under `integrations/soar_adapters/` also shows a config dataclass plus registry/factory pattern. Phase 1A should reuse those ideas but not reuse the SOAR modules directly, because AI inference is an analyst-assistant capability, not a SOAR action or notification delivery path.

Current configuration is mostly environment-driven. `siem_backend.py` contains small helpers such as `env_first()` and `env_csv()`, while adapter modules load their own env vars. Existing runtime code avoids printing secrets and reports presence/readiness instead of values. Phase 1A should follow that pattern.

## Goals / Non-Goals

**Goals:**

- Add an on-demand, provider-neutral AI gateway foundation.
- Support `disabled`, `local_only`, `ask_before_paid_fallback`, and `automatic_fallback` modes.
- Attempt a local provider first when capable, with bounded timeouts and clear fallback behavior.
- Add provider capability/readiness checks that are secret-free and safe to expose to authorized users.
- Return standardized request metadata for provider, model, latency, token estimate, cost estimate, fallback path, and outcome.
- Keep all Phase 1A behavior read-only and non-autonomous.
- Provide one clean backend home for future AI code so later phases do not scatter provider logic across routes.

**Non-Goals:**

- Analyst UI, contextual AI buttons, floating chat UX, frontend components, or visual design.
- Alert/incident/source/recon/registry context builders.
- Prompt templates or AI explanation content.
- Read-only SOC tools such as `search_alerts` or `get_incident_timeline`.
- Drafting, approval-gated actions, direct production writes, SOAR actions, shell access, direct database access by providers, or autonomous background analysis.
- Adding a schema migration by default.
- Making any paid AI provider mandatory.

## Decisions

### Create a dedicated `core/ai` backend package

Implement Phase 1A in a new backend package:

- `core/ai/__init__.py`
- `core/ai/config.py`
- `core/ai/models.py`
- `core/ai/providers.py`
- `core/ai/gateway.py`
- `core/ai/readiness.py`

Add one thin route module:

- `routes/ai_routes.py`

Register the blueprint in `siem_backend.py`.

Rationale: `core` is where reusable business services live, and `routes` is where Flask entrypoints live. A dedicated `core/ai` package keeps AI provider logic out of existing alert, incident, integration, and SOAR modules. This mirrors the existing clean split between `routes/integration_routes.py` and `integrations/*`, but avoids coupling AI inference to notification/SOAR semantics.

Alternative considered: place AI providers under `integrations/`. Rejected because existing `integrations` code is tied to SOAR notifications and real/simulation action execution. AI inference has different modes (`disabled`, `local_only`, fallback consent), metadata, and future context-building needs.

### Use environment-backed config with one dataclass loader

Add an `AiGatewayConfig` dataclass loaded from env vars in `core/ai/config.py`.

Planned env vars:

| Env var | Purpose | Default |
| --- | --- | --- |
| `AI_GATEWAY_MODE` | `disabled`, `local_only`, `ask_before_paid_fallback`, `automatic_fallback` | `disabled` |
| `AI_LOCAL_PROVIDER` | local provider key, initially `ollama` | `ollama` |
| `AI_LOCAL_BASE_URL` | local inference endpoint, e.g. Mini PC Ollama URL | empty |
| `AI_LOCAL_MODEL` | default local model | empty |
| `AI_LOCAL_TIMEOUT_SECONDS` | local provider timeout | `10` |
| `AI_PAID_PROVIDER` | optional paid provider key, initially `openai` or `anthropic` | empty |
| `AI_PAID_MODEL` | optional paid model | empty |
| `AI_PAID_TIMEOUT_SECONDS` | paid provider timeout | `20` |
| `AI_PAID_FALLBACK_ENABLED` | allows automatic paid fallback only when mode permits | `false` |
| `AI_MAX_PROMPT_CHARS` | maximum request prompt/input size for Phase 1A smoke requests | `12000` |

The loader SHALL normalize invalid modes to `disabled` or return a config error that fails closed. Secret-bearing provider API keys are checked only by name/presence in provider-specific implementations and are never returned in readiness responses.

Alternative considered: put AI config into Flask `app.config` only. Rejected because existing runtime/deployment conventions are env-driven and tests can patch env vars directly. Route code may still copy sanitized config into response payloads.

### Define a small provider interface and registry

Add an `AiProvider` protocol/base class in `core/ai/providers.py` with:

- `provider_key`
- `supports(request) -> AiCapabilityResult`
- `readiness(config) -> AiProviderReadiness`
- `generate(request, config) -> AiProviderResponse`

Add concrete providers:

- `DisabledAiProvider`: always safe, returns disabled/unavailable without external calls.
- `OllamaProvider`: local HTTP provider using the configured endpoint and timeout.
- `StubPaidProvider` or placeholder paid provider wiring only when implementation can do so without adding mandatory external dependencies. If OpenAI/Anthropic clients are not already dependencies, Phase 1A may model paid provider readiness/config without implementing real paid calls.

Rationale: Phase 1A needs provider neutrality and local-first routing immediately, but it does not need every future provider. The interface should be small and testable. Provider implementations must return normalized metadata so later UI work can display provider/model/cost consistently.

Alternative considered: one gateway function with `if provider == ...` branches. Rejected because it would make later OpenAI/Anthropic/local additions touch central routing code too often and create avoidable merge risk.

### Add an `AiGateway` router with local-first behavior

`core/ai/gateway.py` SHALL own routing. It accepts an `AiGatewayRequest` and returns an `AiGatewayResponse`. It SHALL:

1. Load config or accept injected config for tests.
2. Reject immediately in `disabled` mode.
3. Attempt the local provider first when configured, reachable, and capable.
4. If local is unavailable, timed out, or incapable, evaluate fallback policy.
5. Use paid fallback only when the mode and config explicitly allow it.
6. Return a clear failure response when no provider can run.

`ask_before_paid_fallback` SHALL NOT automatically call a paid provider in Phase 1A. It SHALL return a response indicating paid fallback is available but requires explicit analyst confirmation in a later phase. This preserves predictable spend until Phase 1B/UI owns the confirmation interaction.

`automatic_fallback` MAY call a paid provider only when `AI_PAID_FALLBACK_ENABLED=true` and the paid provider is configured. If no real paid provider implementation is added in Phase 1A, it SHALL return `fallback_blocked` rather than pretending a paid call occurred.

Rationale: this matches the roadmap's local-first/cost-control policy while avoiding hidden paid spend.

### Standardize metadata and outcome vocabulary

`core/ai/models.py` SHALL define dataclasses or typed dicts for:

- `AiGatewayRequest`
- `AiGatewayResponse`
- `AiProviderReadiness`
- `AiRequestMetadata`
- `AiCapabilityResult`

Metadata SHALL include:

- `provider`
- `model`
- `mode`
- `status`
- `read_only`
- `latency_ms`
- `estimated_prompt_tokens`
- `estimated_completion_tokens`
- `estimated_cost_usd`
- `local_request`
- `paid_request`
- `fallback_attempted`
- `fallback_reason`
- `error_code`

Statuses SHALL distinguish at least:

- `disabled`
- `success`
- `provider_unavailable`
- `provider_timeout`
- `provider_incapable`
- `fallback_requires_confirmation`
- `fallback_blocked`
- `configuration_error`
- `failed`

Token and cost values may be estimates. Local requests SHALL report `estimated_cost_usd=0` and `paid_request=false`.

### Add only status/readiness API in Phase 1A

Add `GET /ai/status` in `routes/ai_routes.py`, protected by `login_required` and `analyst_or_super_admin_required`. It SHALL return sanitized AI gateway config/readiness and no secret values.

Do not add a general prompt endpoint unless implementation needs a narrow smoke endpoint to verify routing. If a smoke endpoint is added, it must be explicitly test-only or authenticated read-only, accept only a bounded synthetic input, and must not consume SIEM context. The preferred Phase 1A implementation is status/readiness plus unit-tested gateway routing.

Rationale: analyst-facing AI request UX belongs to Phase 1B. Phase 1A should prove backend wiring without prematurely designing prompts or chat APIs.

### Reuse existing RBAC and logging boundaries

AI status/readiness should use the existing analyst read boundary: `login_required` plus `analyst_or_super_admin_required`. Super-admin-only access is too restrictive for future analyst explainers; viewer access is too broad because AI responses may later include security investigation context.

Logging SHALL use Python logging with secret-free fields. Audit logging is not required for read-only status checks. If implementation adds a smoke generation endpoint, it SHALL write an audit event named `AI_GATEWAY_REQUESTED` only with safe metadata, not prompt text or provider secrets.

Rationale: existing RBAC conventions are adequate and should not be redesigned.

### Keep provider calls bounded and dependency-light

The Ollama provider should use the Python standard library or existing dependency set if practical, with explicit timeout handling. Do not add heavy SDK dependencies for paid providers in Phase 1A unless they are already present or the implementation explicitly justifies them. Provider exceptions SHALL be classified into normalized statuses without leaking raw endpoint URLs that include credentials.

Rationale: Phase 1A is foundation work; dependency sprawl should wait until a concrete provider is needed.

## Risks / Trade-offs

- [Local endpoint is slow or unavailable] -> Route through explicit timeouts, readiness metadata, and fallback policy rather than blocking Flask workers indefinitely.
- [Paid fallback creates unexpected cost] -> Default to `disabled`, require explicit mode plus `AI_PAID_FALLBACK_ENABLED=true`, and make `ask_before_paid_fallback` non-executing in Phase 1A.
- [Provider abstraction becomes overbuilt] -> Keep the interface to readiness, capability check, and generate only; defer tool use, prompt templates, streaming, and advanced routing.
- [Secrets leak through status or logs] -> Return env var names/presence only and test that API keys, base URLs with credentials, and prompt text are not logged or serialized.
- [AI code gets scattered] -> Require the `core/ai` package and thin `routes/ai_routes.py` boundary.
- [Future UI needs are boxed in] -> Return stable metadata and explicit statuses so Phase 1B can render clear analyst-facing disabled/fallback/cost states without changing gateway internals.
- [No real paid provider in Phase 1A disappoints expectations] -> Treat paid provider implementation as optional unless dependency/config readiness is trivial; the required foundation is the routing contract, not paid API consumption.

## Migration Plan

1. Mac AI implements `core/ai` foundation modules, route registration, and focused tests.
2. Mac AI verifies no database/schema migration is introduced.
3. Mac AI runs focused backend tests, Python compilation for new modules, `git diff --check`, and strict OpenSpec validation.
4. After user authorization, the future implementation can be committed and pushed.
5. VM deployment is not part of this spec creation. If implementation adds runtime backend files, VM sync will only be required later when the user explicitly chooses to deploy the backend change.

Rollback is code-only: remove the AI blueprint registration and `core/ai` package, reverting to no AI backend surface. No database rollback is expected.

## Future Phase Dependencies

Phase 1B will reuse:

- `AiGateway` for all explainer and floating-chat inference calls.
- `AiGatewayConfig` and readiness/status data for analyst-facing disabled/unavailable/fallback states.
- `AiRequestMetadata` for provider/model/cost/latency display.
- The route/RBAC pattern from `GET /ai/status`.

Phase 2 will reuse:

- Provider abstraction and metadata for repo-aware assistant responses.
- The same disabled/local/fallback policy so development assistant requests do not create a separate cost model.

Phase 3 will reuse:

- Gateway request/response models for read-only SOC tool responses.
- Capability detection to decide whether a provider can handle larger tool-grounded investigation requests.

Phases 4 and 5 will reuse:

- The metadata and fallback/cost model.
- The read-only boundary vocabulary to distinguish advice/drafts from approved production actions.

Phase 6 will reuse:

- Provider routing, timeout, metadata, and capability checks as the base for any future planner/tool-chaining layer.

## Open Questions

- Which exact local endpoint will be available first: Ollama on Mini PC, Ollama on Mac for development, or a disabled-only initial deployment? The design supports all three through config.
- Should Phase 1A include a narrow authenticated smoke generation endpoint, or should implementation keep generation unit-tested until Phase 1B adds real analyst request surfaces? Preferred answer: no smoke endpoint unless implementation needs it for meaningful integration verification.
