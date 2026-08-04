## Context

The AI Gateway foundation already defines a provider-neutral `AiProvider` contract, an Ollama adapter, four gateway modes, normalized response metadata, readiness reporting, and a single routing authority. AI model profiles add backend-owned semantic selection of model, timeout, prompt budget, output budget, and temperature. The Anakin planner adds a strict proposal/validation/one-repair/orchestration boundary in which the model owns language understanding and the server owns safety validation and execution.

Production evidence supports keeping those boundaries while changing the inference placement: local Ollama is suitable for bounded workflows, while complex `agentic_planning` requires Anthropic. This change therefore extends the three active OpenSpec changes rather than replacing them. It adds a provider adapter and policy/accounting services behind the gateway, not a second routing path.

The gateway runs in Flask web processes and relevant workers, so paid-use enforcement and runtime policy cannot depend on process-local memory. PostgreSQL is the shared source for runtime policy and usage accounting. Anthropic credentials remain process secrets loaded from the environment. The Mac repository remains the source of truth; VM deployment and production acceptance occur only in a separately authorized implementation phase under `docs/mac-vm-source-of-truth-policy.md`.

## Goals / Non-Goals

**Goals:**

- Add Anthropic through the existing provider protocol without changing Ollama behavior.
- Make provider and model selection explicit, exhaustive, backend-owned, and profile-specific.
- Keep the gateway as the sole routing and paid-use authority.
- Enforce a shared daily UTC spending cap before every Anthropic request, including repair.
- Record provider, model, tokens, cost, latency, status, and repair linkage for paid requests.
- Provide validated, audited, immediately effective runtime policy using established admin configuration patterns.
- Extend `/ai/status` with sanitized readiness, routing, mode, and budget information.
- Preserve planner semantics, validation, repair, orchestration, evidence, security, and asynchronous worker boundaries.

**Non-Goals:**

- Redesigning `AiProvider`, the planner contract, validators, workflow orchestration, or the async job model.
- Allowing browsers, callers, prompts, or planner output to select providers or models.
- Adding deterministic conversational interpretation, keyword routing, or server-owned language understanding.
- Storing API keys, credential-bearing endpoints, or other secrets in PostgreSQL, logs, audit records, status output, or frontend state.
- Introducing autonomous inference, production mutation, direct provider database access, or direct provider tool execution.
- Implementing a generalized billing platform, quota product, or new fallback decision engine.

## Decisions

### 1. Anthropic is an additive `AiProvider`

The Anthropic adapter SHALL implement the existing provider identity, capability, readiness, and generation operations. The provider factory/registry remains the construction point, and the gateway remains the only consumer allowed to select a provider. Provider-specific request translation, response parsing, usage extraction, error classification, and bounded readiness checks stay inside the adapter.

The adapter is configured by environment-held credentials and validated non-secret settings. `ANTHROPIC_API_KEY` is never persisted. When an effective profile or mode requires Anthropic, startup validation must reject missing credentials, invalid model/pricing settings, or an unusable provider configuration. Ollama-only operation does not require Anthropic configuration and retains its existing behavior.

Changing the common provider interface is not planned. If implementation discovers an unavoidable contract gap, it must first demonstrate that the concern cannot be represented in normalized generation metadata or a provider-private helper, then update this design and affected specs before code proceeds.

Alternatives rejected: a planner-owned Anthropic client would bypass gateway policy and accounting; an Anthropic-specific route would give clients a provider choice; placing credentials in runtime configuration would violate the existing secrets boundary.

### 2. Profiles own provider/model intent; the gateway enforces it

The profile registry gains a trusted provider assignment alongside the existing model and generation controls. The invocation inventory remains the mapping from workflow to profile. The initial routing table is exhaustive:

| Profile | Provider class | Paid fallback |
| --- | --- | --- |
| `fast_triage` | Ollama | prohibited |
| `agentic_planning` | Anthropic | direct paid use subject to mode and budget |
| `guided_analysis` | Ollama | prohibited |
| `deep_briefing` | Ollama | prohibited |
| `developer_assistant` | Ollama | prohibited |

Clients continue to submit semantic actions and context, not a provider, model, profile, timeout, or budget. The backend resolves the workflow to a profile, and the gateway resolves that trusted profile to its provider/model. Provider selection cannot occur in Flask routes, planner services, workers, or frontend services.

Existing gateway modes remain the outer authorization boundary:

- `disabled` permits no provider execution.
- `local_only` permits only Ollama-assigned profiles and blocks Anthropic-assigned profiles without rerouting them.
- `ask_before_paid_fallback` never makes an unconfirmed Anthropic call; an Anthropic-assigned request reports that paid confirmation is required through the established gateway state.
- `automatic_fallback` permits unattended Anthropic execution only for a profile explicitly assigned to Anthropic and only after configuration and budget authorization. It does not make Ollama-only profiles eligible for paid fallback.

The name `automatic_fallback` is retained for compatibility even though it becomes the mode that authorizes an explicit paid profile assignment. This change does not create a new gateway mode. Routing failure never causes an Anthropic planner call to switch silently to Ollama.

Alternatives rejected: local-first planner execution repeats the measured latency/capability problem; client selection weakens policy control; capability guessing at runtime makes routing nondeterministic and difficult to audit.

### 3. Planner repair stays within its current boundary

`agentic_planning` proposal generation uses its configured Anthropic provider and model. The server performs the existing strict structural, semantic, evidence, tool, RBAC, and policy validation. An invalid proposal is eligible for at most one repair call using that same Anthropic assignment.

Repair receives the invalid candidate plus machine-readable validation errors through the existing bounded repair contract and must preserve already valid decisions where possible. It is a distinct gateway request with its own budget authorization, request record, token/cost/latency accounting, and linkage to the initial attempt. If the remaining budget cannot authorize repair, the gateway does not call Anthropic, the planner returns the existing graceful invalid-plan failure path, and no weaker model is tried. Provider failure, timeout, or malformed repair output likewise does not introduce another repair or provider switch.

Alternatives rejected: local repair can silently change semantic decisions and has weaker demonstrated reasoning; multiple repairs make spend and latency unbounded; server-side semantic repair would move language understanding out of the planner.

### 4. Paid accounting and budget enforcement are gateway-owned and shared

Every paid generation attempt, including repair, passes through one gateway accounting boundary. Before a provider call, the gateway calculates a conservative maximum request cost from the selected provider/model pricing policy, estimated input tokens, and maximum output tokens. In one PostgreSQL transaction it lazily establishes the current UTC usage day, applies the configured daily cap, and reserves enough remaining budget for the request. If configuration, pricing, usage state, or the transaction cannot be read safely, or the reservation would exceed the cap, the paid call is blocked.

After the call, reported provider usage is normalized and the reservation is reconciled to actual or best available estimated token/cost values. If actual usage cannot be obtained, the conservative reserved amount remains charged so an uncertainty cannot allow overspend. Each attempt records provider, model, profile, timestamps, latency, input/output/total tokens or estimates, estimated/actual cost classification, status, and correlation/repair identity. Accounting data is shared across Gunicorn processes and workers; process-local counters are not authoritative.

The UTC reset is lazy: the first budget-controlled request after the UTC date changes atomically advances or creates the active daily accounting period before authorization. No scheduler is required. The cap is never treated as advisory. Budget rejection is a typed, observable gateway outcome, and Anthropic is never called after rejection. When durable runtime configuration is invalid or unreadable, the gateway's effective mode becomes `local_only` and uses only validated source-controlled local defaults; if those local defaults are also invalid, the effective mode becomes `disabled`. Paid accounting failure likewise closes all paid routing while valid local-only requests continue. Status reports the effective fail-closed mode and configuration-error state.

Alternatives rejected: post-call-only accounting can exceed the cap; in-memory counters diverge across workers; a midnight job creates an unnecessary operational dependency; provider-side billing dashboards are too delayed to authorize individual requests.

### 5. Runtime policy follows existing durable admin patterns

Gateway mode, profile routing policy, daily spending cap, enabled state, and non-secret provider/model/pricing policy are PostgreSQL-backed runtime settings. Implementation SHALL copy the existing `detection_config` and pfSense runtime configuration lifecycle: source-controlled safe defaults, schema-backed overrides, strict backend validation, super-admin-only mutation, `updated_by`, `updated_at`, sanitized old/new audit details, and reads that take effect without service restart.

Credentials remain environment-only and are excluded from the runtime payload and persistence model. Frontend administration is a view/edit surface over backend policy; it is not a routing authority. Invalid or unreadable runtime policy forces the effective mode to `local_only` using validated source-controlled local defaults, or to `disabled` if those defaults are invalid. Immediate effect may use direct reads or a bounded/version-aware cache, but stale process-local configuration cannot authorize spend after a policy reduction.

Alternatives rejected: environment-only policy requires restarts for operational controls; frontend-owned settings are forgeable; storing credentials beside runtime policy expands secret exposure.

### 6. Status extends the existing endpoint philosophy

The authenticated `/ai/status` response remains a thin, read-only, sanitized view. It adds provider readiness, active provider/model per profile, effective gateway mode, the current UTC budget period, cap, used and remaining accounting amounts, and token/cost usage with an explicit provenance classification. Token or cost values are labeled `provider_reported` only when that exact value is returned by the provider; derived or reserved values remain labeled `estimated` and are never represented as actual billed usage. It reports configured, disabled, unavailable, timeout, incapable, budget-blocked, and ready states without making a billable generation request.

Readiness combines provider-private checks with gateway policy state. Phase 1 Anthropic readiness is explicitly configuration-only because the selected API has no non-generation health operation appropriate for this foundation. It validates enabled state, credential presence, model/capability configuration, timeout, and API version without network traffic; later normalized generation outcomes can provide execution health after routing is separately enabled. Status and logs expose missing variable names and error categories, never secret values, authorization headers, credential-bearing endpoints, raw prompts, or sensitive response content.

Alternatives rejected: a new Anthropic status route fragments the provider-neutral contract; returning raw provider errors risks credential or endpoint disclosure.

### 7. Acceptance follows the real execution paths

Mac AI implementation and focused tests precede any VM work. Acceptance must cover web and worker invocation paths, profile routing, all four modes, Ollama-only continuity, Anthropic planner proposal/repair, shared accounting, UTC rollover, audit records, redaction, and concurrent budget authorization. Browser-path production acceptance must exercise the analyst-visible Anakin flow through the deployed frontend/backend boundary.

A controlled acceptance case must set remaining budget below the conservative authorization required by the next Anthropic call. It verifies that no provider call occurs, the gateway returns the typed budget outcome, usage does not silently exceed the cap, status reports the exhaustion, the planner degrades gracefully without local-model substitution, and Ollama-only workflows continue according to mode.

## Risks / Trade-offs

- [Existing mode names imply fallback rather than direct paid assignment] → Document the mode/profile interaction explicitly and test all combinations; do not add an implicit fifth mode.
- [Concurrent web and worker requests can race the cap] → Use transactional PostgreSQL authorization/reservation, never process-local check-then-write logic.
- [Provider token counts or prices can be missing or stale] → Validate pricing policy, reserve conservatively, identify estimates, and retain the reservation when reconciliation is uncertain.
- [Runtime reductions can be bypassed by stale caches] → Require request-time or version-aware policy evaluation before each paid authorization.
- [Anthropic errors may leak secrets or sensitive endpoints] → Normalize provider errors at the adapter boundary and apply existing redaction to API, logs, audit, and status output.
- [Hybrid routing could weaken planner validation] → Change only provider/model assignment; keep validators, repair count, workflow ownership, evidence rules, and execution boundaries unchanged.
- [A local fallback may appear operationally attractive during failure] → Treat planner provider failure and insufficient repair budget as graceful terminal planning outcomes, not permission to switch models.
- [Startup fail-closed behavior could unnecessarily disrupt local workflows] → Require Anthropic configuration only when effective policy enables an Anthropic profile; otherwise retain the valid Ollama-only startup path.
- [Status readiness checks could add spend or latency] → Use bounded non-generation checks and cached health where appropriate; never perform paid generation for status.

## Migration Plan

1. Implement and test the Anthropic adapter, secret validation, readiness normalization, and provider registration with the gateway still disabled or local-only.
2. Add provider-owned profiles and the exhaustive routing inventory while retaining Ollama assignments except for a feature-disabled `agentic_planning` Anthropic path.
3. Add durable usage accounting, transactional budget authorization, UTC lazy rollover, repair accounting, and sanitized telemetry before any paid profile is enabled.
4. Add durable runtime policy administration, super-admin RBAC, audit history, immediate-effect reads, and the `/ai/status` extensions.
5. Enable hybrid routing in a controlled Mac environment, run focused and full regression gates, then perform separately authorized VM preflight/deployment and browser-path production acceptance.

Rollback disables paid routing through runtime mode/profile policy, preserving Ollama-only profiles. Schema additions remain additive so rollback does not require destructive data removal. Credential removal follows the documented secret-management path after paid routing is disabled. Any production rollback or deployment requires explicit authorization.

## Open Questions

- Which Anthropic model identifier and validated input/output pricing values will be approved at implementation start? They must be configuration, not hard-coded client choices.
- Which existing super-admin settings screen is the best host for the gateway policy controls after current UI topology is re-verified?
