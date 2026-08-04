# Anthropic Provider Foundation

## Phase 1 state

Anthropic is implemented as a provider behind the existing AI Gateway abstraction. Phase 1 does not assign Anthropic to an AI profile, enable paid fallback, or permit normal application routing to Anthropic. All current profiles, including `agentic_planning` and scheduled SOC Briefings, retain their existing Ollama behavior.

Phase 2 is required before any profile can intentionally route through Anthropic. Phase 3 is required before paid execution can be enabled with durable budget enforcement and accounting.

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
- `AI_ANTHROPIC_MODEL` has no source default and must be an approved provider model identifier when enabled.
- `AI_ANTHROPIC_TIMEOUT_SECONDS` is bounded to a positive value and defaults to 20 seconds.
- `ANTHROPIC_API_VERSION` defaults to the non-secret version header shown above and must use `YYYY-MM-DD` format.

Enabling the provider configuration in Phase 1 makes sanitized configuration readiness observable; it does not enable routing. `anthropic_routing_enabled` remains a source-controlled false guard and is not an environment switch in this phase.

## Readiness and safety

`/ai/status` includes an Anthropic provider row even when no Anthropic configuration exists. Phase 1 readiness is configuration-only and performs no provider network request or generation. It reports provider/model, configuration state, missing environment-variable names, and credential presence as a boolean. It never returns the key, authorization headers, prompts, provider response bodies, or provider endpoints.

Local-only backend and worker startup remains valid without Anthropic credentials. If `AI_ANTHROPIC_ENABLED=true`, backend and worker startup fails closed when the key, model, timeout, or API version is missing or invalid.

## No paid calls in Phase 1

Provider generation tests use a mocked local transport and a fake credential. The gateway blocks Anthropic paid fallback even if legacy paid-provider environment settings attempt to select it. Operators must not configure Anthropic as an active paid fallback or assume that provider readiness enables production inference.
