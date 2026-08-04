# Anthropic Provider Foundation

## Phase 2 state

Anthropic is implemented behind the existing AI Gateway abstraction and is the backend-owned provider assignment for `agentic_planning`. `fast_triage`, `guided_analysis`, `deep_briefing` (including scheduled SOC Briefings), and `developer_assistant` remain explicitly assigned to Ollama.

Phase 2 keeps Anthropic paid execution feature-disabled until Phase 3 adds transactional budget authorization. `local_only` blocks the Anthropic planner profile without substituting Ollama, and normal source-loaded configuration cannot make a paid request in this phase.

## Environment configuration

Anthropic credentials are process-environment secrets. They must never be stored in PostgreSQL, source control, frontend state, logs, audit details, or API responses.

```dotenv
AI_ANTHROPIC_ENABLED=false
ANTHROPIC_API_KEY=
AI_ANTHROPIC_MODEL=
AI_ANTHROPIC_TIMEOUT_SECONDS=20
ANTHROPIC_API_VERSION=2023-06-01
```

- `AI_ANTHROPIC_ENABLED` defaults to `false`. Invalid boolean values fail startup validation.
- `ANTHROPIC_API_KEY` has no source default and is required only when Anthropic configuration is explicitly enabled.
- `AI_ANTHROPIC_MODEL` has no source default; it is the backend-owned model for the Anthropic `agentic_planning` profile and must be an approved provider model identifier when enabled.
- `AI_ANTHROPIC_TIMEOUT_SECONDS` is bounded to a positive value and defaults to 20 seconds.
- `ANTHROPIC_API_VERSION` defaults to the non-secret version header shown above and must use `YYYY-MM-DD` format.

Enabling provider configuration makes sanitized readiness and the profile assignment observable; it does not enable paid execution. `anthropic_routing_enabled` remains a source-controlled false guard and is not an environment switch in this phase.

## Readiness and safety

`/ai/status` includes an Anthropic provider row even when no Anthropic configuration exists. Phase 1 readiness is configuration-only and performs no provider network request or generation. It reports provider/model, configuration state, missing environment-variable names, and credential presence as a boolean. It never returns the key, authorization headers, prompts, provider response bodies, or provider endpoints.

Local-only backend and worker startup remains valid without Anthropic credentials. If `AI_ANTHROPIC_ENABLED=true`, backend and worker startup fails closed when the key, model, timeout, or API version is missing or invalid.

## No paid calls in Phase 2

Provider generation and routing tests use mocked transports/providers and fake credentials. The gateway ignores legacy global paid-provider settings for routing and blocks Anthropic execution at the Phase 2 feature guard. Operators must not assume that provider readiness or the `agentic_planning` assignment enables production inference.
