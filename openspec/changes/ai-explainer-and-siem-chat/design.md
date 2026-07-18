## Context

Phase 1A adds `core/ai` with `AiGateway`, provider-neutral config, local-first routing, standardized metadata, and `GET /ai/status`. Phase 1B must build on that contract, not redesign provider routing.

Current backend read paths already expose the required SIEM data:

- Alerts: `routes/alerts_events_routes.py` exposes `/alerts`, `/alerts/summary`, `/alerts/<id>`, `/alerts/<id>/why-fired`, `/alerts/<id>/related-events`, `/recon-activities`, `/recon-activities/<id>`, `/recon-activities/<id>/related-events`, and `/events/search`.
- Incidents: `routes/incident_routes.py` exposes `/incidents`, `/incidents/<id>`, and `/incidents/<id>/timeline`; `build_readonly_incident_timeline()` is explicitly read-only.
- Source IP context: `routes/source_ip_context_routes.py` aggregates alerts, incidents, queue, blocklist, reputation, internet-noise, playbook executions, returning-attacker, campaign, and response-outcome context behind `/source-ip-context`.
- Response registry: `routes/response_registry_routes.py` exposes read endpoints for list/detail and a separate mutation command endpoint that Phase 1B must not call.
- Detection metadata: `routes/severity_response_matrix_routes.py`, `/alerts/<id>/why-fired`, alert payload intelligence, and detection simulator explainability components provide canonical detection explanation sources.
- Dashboard context: `frontend/src/services/alertsService.js` already loads `/alerts/summary` and `/alerts` with active filters; `App.js` owns the current visible dashboard filters and selected alert state.

Current frontend patterns are component-local async state, `buildSiemPath` service modules, shared error parsing in `utils/apiResponse.js`, master/detail panes, alert side panel, dark inline styles/CSS modules, and focused Jest/RTL tests. Phase 1B should follow those patterns and add shared AI components instead of duplicating loading/error/metadata UI in each workspace.

## Goals / Non-Goals

**Goals:**

- Add read-only contextual explanations for dashboard graphs, alerts, incidents, source IPs, recon activity, response registry records, and detection evidence.
- Add floating general SIEM chat for natural questions about the current visible SIEM context.
- Centralize context building under `core/ai` so prompts are grounded in canonical SIEM data paths and size limits are consistent.
- Reuse `AiGateway.generate()` and return Phase 1A provider/model/cost/latency/fallback metadata to the frontend.
- Provide shared analyst-facing AI response UI for loading, retry, cancel, dismiss, stale-response protection, failure states, and metadata display.
- Keep chat history client-session-only for Phase 1B.
- Preserve RBAC, read-only behavior, no direct provider DB access, no shell access, no production writes, and no background inference.

**Non-Goals:**

- Repo-aware development assistant.
- Phase 3 AI tools or multi-step tool calling.
- Draft generation, action execution, approval-gated actions, SOAR execution, alert/incident/status mutation, registry command execution, or database writes.
- Persisted AI chat history, model memory, vector stores, embeddings, fine-tuning, streaming responses, or schema migrations.
- Broad UI redesign outside the required AI entry points and shared response presentation.
- Working paid-provider adapter if Phase 1A still only has placeholder paid wiring; Phase 1B must surface blocked/unavailable states clearly.

## Decisions

### Reuse Phase 1A gateway as the only inference boundary

Phase 1B SHALL call `AiGateway.generate(AiGatewayRequest(...))` from a new backend service. Routes and context builders must not call Ollama, OpenAI, Anthropic, or provider clients directly.

Rationale: Phase 1A already owns provider neutrality, local-first routing, fallback policy, timeout handling, and metadata. Reusing it prevents a second cost/routing implementation.

Alternative considered: frontend calls provider endpoint directly. Rejected because it bypasses RBAC, context filtering, source attribution, cost policy, and secret controls.

### Add centralized context builder and explainer service under `core/ai`

Add:

- `core/ai/context_builder.py`: validates context type/ids, fetches canonical SIEM context, normalizes it into bounded sections, attaches source references, and reports insufficiency/truncation.
- `core/ai/explainer_service.py`: builds the system/user prompt from the normalized context and question/action, calls `AiGateway`, and maps the gateway response to the API response contract.

Provider implementations must not receive database connections or know how SIEM data is fetched.

Rationale: this keeps route handlers thin and keeps source grounding consistent across contextual buttons and floating chat.

Alternative considered: each route/component builds its own prompt context. Rejected because it duplicates truncation, attribution, and read-only guard logic.

### Supported context types and canonical source paths

Phase 1B SHALL support these `context_type` values:

| Context type | Required identifier/input | Canonical backend source |
| --- | --- | --- |
| `alert` | `alert_id` | `/alerts/<id>` logic, alert payload intelligence, `/alerts/<id>/why-fired` when available, `/alerts/<id>/related-events` with small limit |
| `incident` | `incident_id` | `get_incident_detail()` and `build_readonly_incident_timeline()` |
| `source_ip` | `source_ip` | existing `/source-ip-context` aggregation logic, preferably moved/reused through helper functions rather than HTTP self-calls |
| `recon_activity` | `activity_id` | `get_recon_activity_detail()` and related-events logic with small limit |
| `dashboard` | active dashboard filters and visible summary payload | `/alerts/summary` data, current visible filters, top IPs, timeline, map markers, and recent alert rows already loaded by the dashboard |
| `response_registry` | `registry_id` | `get_registry_detail()` only; never `/response-registry/commands` |
| `detection` | `alert_id` or `rule_id` | `/alerts/<id>/why-fired`, alert detection metadata, and severity/response matrix where relevant |
| `general` | question plus visible context | current visible UI context supplied by frontend plus optional bounded backend enrichment by ids/IPs |

The implementation should prefer extracting existing route internals into reusable read-only helpers only where necessary. Do not create duplicate SQL copies if a clean helper already exists. If a helper currently lives in a route module, moving it into `core` is acceptable only for Phase 1B context reuse.

### Context limits, attribution, and insufficient-context behavior

The context builder SHALL apply fixed safety limits:

- Maximum prompt/context payload: use Phase 1A `AI_MAX_PROMPT_CHARS` as the final prompt guard.
- Per-section defaults: recent alerts 10, related events 15, timeline entries 30, source-IP outcomes 10, recon related events 15, registry history/detail sections bounded by existing service limits.
- Time windows: use the current visible dashboard filters when supplied; otherwise default general/dashboard summaries to the active app default operational scope and dashboard timeline range.
- Truncation: include `truncated=true`, per-section `omitted_count` where known, and a short `truncation_reason`.
- Source attribution: every context section includes `source_type`, `source_path` or helper name, `record_ids`, and `generated_at` when available.

If required identifiers are missing, records are not found, RBAC prevents access, or the gathered context is too thin, the service SHALL return a structured insufficient-context response without inventing facts. If the gateway is disabled/unavailable, preserve the gateway status and metadata.

### Backend API contract

Extend `routes/ai_routes.py` with two POST routes:

- `POST /ai/explain`
- `POST /ai/chat`

Both routes SHALL use `login_required` and `analyst_or_super_admin_required`, accept JSON only, validate input, call a service, and return JSON. They must not open DB connections except through the context builder/service layer, and they must not mutate data.

`POST /ai/explain` request:

```json
{
  "context_type": "alert",
  "action": "explain_alert",
  "question": "Why is this important?",
  "context": {
    "alert_id": 123,
    "source_ip": "203.0.113.10",
    "visible_filters": {}
  }
}
```

`POST /ai/chat` request:

```json
{
  "message": "What changed in the last hour?",
  "visible_context": {
    "active_section": "dashboard",
    "selected_alert_id": 123,
    "selected_incident_id": null,
    "source_ip": "203.0.113.10",
    "dashboard_filters": {},
    "dashboard_summary": {}
  },
  "client_history": [
    {"role": "user", "content": "What am I looking at?"}
  ]
}
```

Response shape:

```json
{
  "status": "success",
  "answer": "...",
  "insufficient_context": false,
  "context": {
    "context_type": "alert",
    "sources": [],
    "truncated": false,
    "omitted_count": 0
  },
  "metadata": {
    "provider": "ollama",
    "model": "llama3",
    "mode": "local_only",
    "status": "success",
    "read_only": true,
    "latency_ms": 1200,
    "estimated_prompt_tokens": 500,
    "estimated_completion_tokens": 120,
    "estimated_cost_usd": 0,
    "local_request": true,
    "paid_request": false,
    "fallback_attempted": false,
    "fallback_reason": null,
    "error_code": null
  },
  "error": null
}
```

HTTP status should remain `200` for expected AI availability states such as disabled, unavailable, timeout, blocked fallback, confirmation required, and insufficient context so the UI can render a normal AI panel state. Use `400` for invalid JSON/input, `401/403` via existing auth/RBAC, `404` for missing requested canonical records, and `500` only for unexpected server errors.

### Prompt and answer constraints

The service prompt SHALL instruct the model:

- Use only the supplied SIEM context.
- Say what is known, what is uncertain, and what to investigate next.
- Do not claim to have checked data that is not in the supplied context.
- Do not recommend or imply autonomous production changes.
- Do not output commands that mutate production.
- Label recommendations as analyst next steps, not actions taken.

Prompt templates may live in `core/ai/explainer_service.py` unless implementation needs a small `core/ai/prompts.py`. Do not create a broad prompt-template framework in Phase 1B.

### Chat history ownership

Chat history SHALL be owned by the frontend in component state for Phase 1B. It SHALL reset on logout/browser refresh and SHALL NOT be persisted to the database or local storage. The backend may accept a bounded `client_history` array to preserve conversational context, but must truncate it and treat it as untrusted user input.

Rationale: client-session-only history delivers useful chat without schema work, retention questions, privacy surprises, or memory semantics.

Alternative considered: persist chat history server-side. Rejected for Phase 1B because it requires schema, retention, audit, and privacy decisions that are not necessary for first useful read-only assistance.

### Frontend service and shared UI

Add:

- `frontend/src/services/aiService.js`: `getAiStatus()`, `requestAiExplanation()`, and `sendSiemChatMessage()` using `buildSiemPath`, credentials, and `parseJsonResponse`.
- `frontend/src/components/AiAssistantButton.js`: compact contextual action button with disabled/loading states.
- `frontend/src/components/AiResponsePanel.js`: shared answer panel/drawer content with answer, sources, metadata, retry, cancel, dismiss, stale marker, and failure-state copy.
- `frontend/src/components/FloatingSiemChat.js`: global floating chat anchored in `App.js` while authenticated.
- Optional `frontend/src/utils/aiDisplay.js`: maps gateway statuses to analyst-facing labels and cost/provider text if that avoids duplicating strings.

Do not redesign the app shell. Use existing dark theme, button, panel, master/detail, and async-state conventions.

### Contextual button placement

Add buttons where the analyst is already looking at the relevant context:

- Dashboard: near summary/chart headers, with actions `Ask AI about this graph` and `Explain anomaly`.
- Alert details: inside `AlertDetailsPanel` near the top summary/evidence area, with `Explain this alert`, `Why is this important?`, and `Recommend investigation`.
- Incident detail: in `IncidentsPanel` detail pane header/actions, with `Summarize incident` and `Recommend next steps`.
- Source IP: in `SourceIpContext` header, with `Explain this IP`, `Is this reconnaissance?`, and `Summarize activity`.
- Recon activity: in the SOC command center recon detail/list context, with `Explain campaign` and `Investigate this cluster`.
- Response registry: in the selected registry detail area, with `Explain this response`.
- Floating chat: visible for authenticated analyst/super-admin users across SIEM workspaces and seeded with current visible context from `App.js`.

For viewer/unauthorized users, AI entry points must be hidden or disabled consistently with backend RBAC.

### Loading, cancellation, stale responses, and navigation

Every AI request from the frontend SHALL:

- Use `AbortController` for cancellation and route/selection changes.
- Track a request id or equivalent guard so stale responses cannot overwrite newer context.
- Show loading text that identifies the context being explained.
- Preserve the current UI state while the AI request is pending.
- Allow dismissal of the AI panel/chat response.
- Provide retry for failed/disabled/unavailable/timeout/fallback-blocked responses without duplicating the original context incorrectly.
- Mark stale responses if the selected alert/incident/source/registry record changed before the response returned.

### Failure-state UX

The shared response UI SHALL map Phase 1A statuses to clear analyst-facing states:

- `disabled`: AI is disabled by configuration.
- `provider_unavailable`: configured provider cannot be reached or is missing config.
- `provider_timeout`: provider timed out; analyst can retry.
- `fallback_blocked`: paid fallback is not enabled/configured.
- `fallback_requires_confirmation`: paid fallback would be needed but cannot run automatically in this mode.
- `configuration_error`: AI configuration failed closed.
- `failed`: unexpected AI failure.
- insufficient context: SIEM data was not enough to answer safely.

Local responses show no API cost. Paid responses, when future adapters exist, show estimated cost from metadata.

### Read-only guarantees

Backend context building may use `core.db.get_db_connection()` through existing helpers, but provider classes must never receive DB handles. AI endpoints must not call mutation routes/services including alert status updates, notes, manual execution, registry commands, approval actions, playbook execution creation, blocklist changes, ingest, or migrations. Tests must enforce this boundary with mocks for representative mutation helpers.

### File-level implementation plan

Expected backend files:

- Modify `core/ai/models.py` only if small request/context metadata models are needed.
- Create `core/ai/context_builder.py`.
- Create `core/ai/explainer_service.py`.
- Modify `routes/ai_routes.py`.
- Modify route/core modules only if extracting existing read-only helpers is necessary.
- Add `tests/test_ai_explainer_context_builder.py`, `tests/test_ai_explainer_routes.py`, and focused gateway integration tests if needed.

Expected frontend files:

- Create `frontend/src/services/aiService.js` and `frontend/src/services/aiService.test.js`.
- Create `frontend/src/components/AiAssistantButton.js`.
- Create `frontend/src/components/AiResponsePanel.js` and tests.
- Create `frontend/src/components/FloatingSiemChat.js` and tests.
- Modify `frontend/src/App.js`.
- Modify `frontend/src/components/DashboardMetrics.js` and/or `DashboardVisuals.js`.
- Modify `frontend/src/components/AlertDetailsPanel.js`.
- Modify `frontend/src/components/IncidentsPanel.js`.
- Modify `frontend/src/components/SourceIpContext.js`.
- Modify `frontend/src/components/SocCommandCenter.js` for recon entry points.
- Modify `frontend/src/components/ResponseRegistryPanel.js`.
- Create `frontend/src/utils/aiDisplay.js` and tests if status/cost display mapping is shared.

## Risks / Trade-offs

- [Context becomes too large for local models] -> Enforce per-section limits, source summaries, truncation metadata, and Phase 1A max prompt size.
- [AI invents details] -> Prompt must require supplied-context-only answers; service must return insufficient-context when context is missing or too thin.
- [Provider disabled/unavailable creates confusing UX] -> Shared response UI maps gateway statuses to clear, retryable analyst states.
- [Frontend chat gets stale during navigation] -> Use current visible context snapshots, abort/cancel on selection changes, and mark stale responses.
- [Accidental mutation path] -> Keep endpoints read-only, use representative mutation-helper mocks, and prohibit registry command/SOAR/alert status calls.
- [Duplicated context SQL] -> Extract/read existing helper paths only where needed instead of copying route queries.
- [Paid provider placeholder remains] -> Surface fallback blocked/unavailable metadata honestly; real paid-provider adapter belongs to a separate provider spec if needed.

## Migration Plan

1. Implement backend context builder and explainer service on the Mac source-of-truth repository.
2. Extend `routes/ai_routes.py` with read-only POST endpoints and route tests.
3. Add frontend service/shared AI components and contextual entry points.
4. Run focused backend tests, focused frontend service/component tests, frontend production build, Python compilation for backend modules, `git diff --check`, and strict OpenSpec validation.
5. Perform manual browser verification for dashboard, alert detail, incident detail, source-IP context, recon activity, response registry, floating chat, responsive layout, loading/error/retry/cancel/dismiss/stale-response behavior.
6. Commit/push only after explicit user authorization.
7. VM deployment is a separate task after implementation review because this phase changes backend and frontend runtime behavior.

Rollback is code-only unless later implementation unexpectedly introduces a migration, which this spec does not require. Disable runtime AI with `AI_GATEWAY_MODE=disabled` as the first operational fallback.

## Future Phase Dependencies

Phase 2 can reuse shared AI UI patterns only if repo-aware assistance is intentionally exposed inside the product; otherwise it remains separate from analyst SIEM chat.

Phase 3 will reuse `core/ai/context_builder.py` source attribution, size limits, and read-only contracts as the baseline for explicit AI tools.

Phase 4 will reuse the shared response panel patterns but must add draft labeling and validation in a separate spec.

Phase 5 will reuse gateway metadata and analyst-facing status states, but must introduce approval, payload preview, idempotency, and audit requirements separately.

Phase 6 can reuse request cancellation, stale-response handling, provider metadata, and context-source attribution as the base for any future planner layer.

## Open Questions

- None blocking. If Phase 1A paid providers are still placeholders during implementation, Phase 1B must treat paid fallback as unavailable/blocked rather than adding a paid adapter inside this change.
