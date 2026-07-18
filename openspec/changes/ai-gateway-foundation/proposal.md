## Why

The AI roadmap needs a safe backend foundation before analyst-facing explainers, floating chat, or SOC tools are added. Today the SIEM has good patterns for Flask routes, RBAC, audit helpers, and provider adapters, but no AI-specific gateway that can enforce local-first routing, disabled mode, timeouts, provider neutrality, request metadata, and read-only behavior.

## What Changes

- Add an additive backend AI gateway foundation for on-demand inference requests.
- Define provider-neutral configuration for `disabled`, `local_only`, `ask_before_paid_fallback`, and `automatic_fallback` modes.
- Define a local-first provider routing contract with capability checks, bounded timeouts, and clear failure behavior.
- Define provider request/response metadata including provider, model, latency, estimated tokens, estimated cost, fallback path, and read-only outcome state.
- Define a backend status/readiness surface for AI configuration and provider availability without exposing secrets.
- Establish repository layout and dependency boundaries for future AI phases.
- Preserve existing detection, correlation, SOAR, ingestion, alert, incident, RBAC, audit, and integration behavior.
- Exclude analyst UI, contextual AI buttons, floating chat behavior, prompt templates, context builders, read-only SOC tools, drafting, approval-gated actions, and autonomous behavior.

## Capabilities

### New Capabilities

- `ai-gateway-foundation`: Provider-neutral, local-first, read-only AI gateway foundation with configuration, routing, capability detection, timeout/fallback behavior, secret-safe metadata, and status/readiness contracts.

### Modified Capabilities

(none)

## Impact

- Backend: new AI gateway/service/provider modules, one thin authenticated status route, provider configuration loader, metadata models, and focused tests.
- Frontend: none in Phase 1A except no-op compatibility; analyst UI belongs to Phase 1B.
- Database: no schema migration expected; Phase 1A should not persist AI request history unless implementation finds an existing safe audit path is needed for status-only evidence.
- Runtime: no autonomous analysis, no background jobs, no production writes, no direct database access by AI providers, and no required paid provider.
- Deployment: source-only backend addition after future implementation; no VM work during spec creation.
