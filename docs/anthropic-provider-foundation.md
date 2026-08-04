# Anthropic Provider Foundation

## Phase 3 state

Anthropic is implemented behind the existing AI Gateway abstraction and is the backend-owned provider assignment for `agentic_planning`. `fast_triage`, `guided_analysis`, `deep_briefing` (including scheduled SOC Briefings), and `developer_assistant` remain explicitly assigned to Ollama.

Phase 3 permits Anthropic paid execution only after validated environment configuration and transactional PostgreSQL budget authorization. `local_only` blocks the Anthropic planner profile without substituting Ollama, and every paid request attempt fails closed before provider contact when accounting or budget authorization is unavailable.

## Environment configuration

Anthropic credentials are process-environment secrets. They must never be stored in PostgreSQL, source control, frontend state, logs, audit details, or API responses.

```dotenv
AI_ANTHROPIC_ENABLED=false
ANTHROPIC_API_KEY=
AI_ANTHROPIC_MODEL=
AI_ANTHROPIC_TIMEOUT_SECONDS=20
ANTHROPIC_API_VERSION=2023-06-01
AI_ANTHROPIC_DAILY_BUDGET_USD=
AI_ANTHROPIC_INPUT_COST_PER_MILLION_TOKENS=
AI_ANTHROPIC_OUTPUT_COST_PER_MILLION_TOKENS=
```

- `AI_ANTHROPIC_ENABLED` defaults to `false`. Invalid boolean values fail startup validation.
- `ANTHROPIC_API_KEY` has no source default and is required only when Anthropic configuration is explicitly enabled.
- `AI_ANTHROPIC_MODEL` has no source default; it is the backend-owned model for the Anthropic `agentic_planning` profile and must be an approved provider model identifier when enabled.
- `AI_ANTHROPIC_TIMEOUT_SECONDS` is bounded to a positive value and defaults to 20 seconds.
- `ANTHROPIC_API_VERSION` defaults to the non-secret version header shown above and must use `YYYY-MM-DD` format.
- The daily cap and both per-million-token prices must be positive validated values before paid routing can be enabled. They are non-secret Phase 3 environment policy; Phase 4 will move non-secret runtime policy into PostgreSQL administration.

Paid execution is enabled only when provider configuration, pricing, the daily cap, gateway mode, and transactional PostgreSQL authorization all succeed. No standalone routing environment switch can bypass accounting.

## Runtime administration in Phase 4

The backend reads the single-row `ai_gateway_config` policy before each gateway request. With no override row, validated source configuration remains effective. A valid override can change gateway mode, preferred Anthropic model, daily paid budget, and whether Anthropic routing is requested without restarting web or worker services.

This follows the existing detection and pfSense configuration lifecycle: an additive PostgreSQL table, whole-policy backend validation, direct request-time reads, `updated_by`, `updated_at`, super-admin-only `GET` and `PATCH` at `/admin/ai-gateway-config`, and existing-format audit events containing sanitized old/new non-secret values and request context. No frontend configuration UI is added in this phase.

Invalid or unavailable runtime policy fails closed to effective `local_only` with Anthropic routing disabled. If validated local configuration is unavailable, effective mode becomes `disabled`. `/ai/status` reports requested and effective sanitized runtime policy so operators can distinguish an applied override from default, invalid, or unavailable configuration.

The runtime table and API never accept or return API keys, provider endpoints, prompts, completions, or evidence. Anthropic credentials remain environment-only, and model pricing rates remain under the existing Phase 3 environment configuration until separately authorized scope changes them.

## Readiness and safety

`/ai/status` includes an Anthropic provider row even when no Anthropic configuration exists. Phase 1 readiness is configuration-only and performs no provider network request or generation. It reports provider/model, configuration state, missing environment-variable names, and credential presence as a boolean. It never returns the key, authorization headers, prompts, provider response bodies, or provider endpoints.

Local-only backend and worker startup remains valid without Anthropic credentials. If `AI_ANTHROPIC_ENABLED=true`, backend and worker startup fails closed when the key, model, timeout, API version, daily cap, or pricing is missing or invalid.

## Paid-call safety in Phase 3

Tests use mocked transports/providers and fake credentials. Every paid proposal and repair reserves shared daily budget before provider invocation and settles an independent sanitized attempt afterward. Accounting failure or budget exhaustion blocks provider contact. Prompts, evidence, credentials, authorization headers, and provider endpoints are never persisted in accounting.
