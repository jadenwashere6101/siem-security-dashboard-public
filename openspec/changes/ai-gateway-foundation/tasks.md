## 1. Scope Confirmation

- [x] 1.1 Re-read the roadmap, `AGENTS.md`, and `docs/mac-vm-source-of-truth-policy.md` before implementation and confirm Phase 1A remains backend foundation only.
- [x] 1.2 Confirm the implementation does not add analyst UI, contextual AI buttons, floating chat, context builders, prompt templates, SOC tools, drafting, approval actions, autonomous analysis, schema migrations, VM work, deployment, commits, or pushes unless separately requested.
- [x] 1.3 Re-check current route, service, RBAC, logging, and integration-provider patterns before editing the referenced files.

## 2. AI Package And Configuration

- [x] 2.1 Create `core/ai/__init__.py` and keep AI gateway internals isolated from alert, incident, detection, SOAR, and notification modules.
- [x] 2.2 Add `core/ai/config.py` with an `AiGatewayConfig` dataclass and env-backed loader for gateway mode, local provider, local endpoint/model/timeout, optional paid provider/model/timeout, paid fallback enablement, and max prompt characters.
- [x] 2.3 Validate invalid or unsafe config values fail closed using disabled/configuration-error behavior and safe timeout defaults.
- [x] 2.4 Ensure secret-bearing provider values are never serialized in config/readiness responses or logs.

## 3. Models And Metadata

- [x] 3.1 Add `core/ai/models.py` with typed request, response, provider readiness, capability result, and request metadata objects.
- [x] 3.2 Define the standard status vocabulary: `disabled`, `success`, `provider_unavailable`, `provider_timeout`, `provider_incapable`, `fallback_requires_confirmation`, `fallback_blocked`, `configuration_error`, and `failed`.
- [x] 3.3 Ensure every gateway response includes provider/model/mode/status/read-only/latency/token-estimate/cost-estimate/local-paid/fallback/error metadata.
- [x] 3.4 Ensure local provider responses always report zero estimated API cost and `paid_request=false`.

## 4. Providers And Readiness

- [x] 4.1 Add `core/ai/providers.py` with a small provider interface covering provider key, capability check, readiness, and generation.
- [x] 4.2 Implement a disabled provider that makes no external calls and returns safe disabled/unavailable metadata.
- [x] 4.3 Implement an Ollama local provider using the configured endpoint/model with bounded timeout handling and normalized errors.
- [x] 4.4 Add only minimal paid-provider readiness or placeholder wiring unless a real paid provider can be implemented without mandatory new SDK dependencies.
- [x] 4.5 Add `core/ai/readiness.py` or equivalent helper to produce secret-free gateway and provider readiness payloads for routes and tests.

## 5. Gateway Routing

- [x] 5.1 Add `core/ai/gateway.py` with an `AiGateway` service that accepts injected config/providers for tests and uses env-loaded defaults at runtime.
- [x] 5.2 Enforce disabled mode by returning a clear disabled response without contacting any provider.
- [x] 5.3 Enforce local-first routing whenever execution is allowed and the local provider is configured, reachable, and capable.
- [x] 5.4 Enforce `local_only` behavior by never calling paid providers when local execution fails.
- [x] 5.5 Enforce `ask_before_paid_fallback` behavior by returning `fallback_requires_confirmation` without making a paid provider call.
- [x] 5.6 Enforce `automatic_fallback` behavior by calling a paid provider only when mode, explicit fallback enablement, provider configuration, and provider capability all allow it.
- [x] 5.7 Classify unavailable, timeout, incapable, blocked fallback, configuration, and unexpected provider failures into the standard status vocabulary.

## 6. Route Integration And Access Control

- [x] 6.1 Add `routes/ai_routes.py` with a thin `GET /ai/status` endpoint that uses existing Flask blueprint conventions.
- [x] 6.2 Protect the AI status endpoint with existing `login_required` and `analyst_or_super_admin_required` behavior.
- [x] 6.3 Register the AI blueprint in `siem_backend.py` without changing unrelated route registration behavior.
- [x] 6.4 Keep status/readiness logging secret-free and avoid audit events for status-only reads unless existing project conventions require them.
- [x] 6.5 If implementation adds a narrow smoke-generation endpoint, make it authenticated, read-only, bounded, secret-safe, non-SIEM-contextual, and audited only with safe metadata.

## 7. Focused Tests

- [x] 7.1 Add configuration tests proving defaults are disabled, invalid modes fail closed, timeout defaults are bounded, paid providers are optional, and secrets are not serialized.
- [x] 7.2 Add provider/readiness tests proving readiness reports missing/configured/unavailable/timeout states without exposing credentials or credential-bearing URLs.
- [x] 7.3 Add gateway-routing tests for disabled mode, local success, local-only local failure, ask-before paid fallback, automatic fallback blocked, automatic fallback allowed, provider timeout, and provider incapability.
- [x] 7.4 Add route tests proving unauthenticated requests are rejected, insufficient roles are rejected, and analyst/super-admin users receive sanitized AI status.
- [x] 7.5 Add regression tests or mocks proving provider execution does not mutate alerts, incidents, SOAR state, configuration, detections, or the database.

## 8. Implementation Verification

- [x] 8.1 Run focused backend tests covering AI config, providers/readiness, gateway routing, and AI status routes.
- [x] 8.2 Run Python compilation or equivalent syntax validation for all new/modified backend modules.
- [x] 8.3 Run the relevant broader backend test subset if shared auth, route registration, or config helpers are touched.
- [x] 8.4 Run the applicable backend build/startup validation for the modified Flask app.
- [x] 8.5 Run `git diff --check`.
- [x] 8.6 Run `openspec validate ai-gateway-foundation --strict`.
- [x] 8.7 Review the complete diff for unrelated changes, debug output, commented-out code, secret exposure, accidental UI changes, schema changes, VM/deployment changes, and out-of-scope behavior.

## 9. Future Phase Guardrails

- [x] 9.1 Document in the implementation handoff that Phase 1B should reuse the gateway, config, readiness, RBAC, metadata, and fallback vocabulary for analyst-facing explainers and chat.
- [x] 9.2 Document that later context builders, prompt templates, read-only SOC tools, drafting, and approval-gated actions must be proposed in separate OpenSpec changes.
- [x] 9.3 Confirm VM sync remains outside Phase 1A implementation unless the user explicitly requests deployment later.
