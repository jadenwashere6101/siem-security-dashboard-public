## Why

Phase 1A created the backend AI gateway foundation, but analysts still have no safe way to ask for explanations about alerts, incidents, source IPs, recon activity, dashboard trends, response records, or the current SIEM view. Phase 1B turns that gateway into an on-demand, read-only analyst assistant while keeping existing SIEM APIs and detection logic as the source of truth.

## What Changes

- Add centralized backend context building for supported SIEM context types: alert, incident, source IP, recon activity, dashboard, response registry, detection explanation, and general visible SIEM chat.
- Add read-only AI explanation/chat API endpoints that reuse the Phase 1A `AiGateway` contract and return provider/model/cost/latency/fallback metadata.
- Add grounded insufficient-context behavior so the assistant clearly says when available SIEM data is incomplete instead of inventing facts.
- Add frontend AI entry points in existing analyst surfaces: dashboard, alert detail, incident detail, source-IP context, recon activity, response registry, and floating SIEM chat.
- Add a shared response experience for loading, retry, cancellation, dismissal, stale-response handling, metadata display, and disabled/unavailable/fallback failure states.
- Add focused backend, frontend service, and component tests proving the feature is read-only, source-of-truth grounded, RBAC-protected, and usable across responsive layouts.
- Exclude repo-aware development assistance, AI tools, drafting, approval-gated actions, autonomous analysis, direct database access by providers, schema migrations, and broad UI redesign.

## Capabilities

### New Capabilities

- `ai-explainer-and-siem-chat`: Read-only, source-grounded AI explanations and general SIEM chat using existing SIEM data paths and the Phase 1A AI gateway.

### Modified Capabilities

(none)

## Impact

- Backend: add AI context-building and explainer service modules under `core/ai`, extend `routes/ai_routes.py` with thin authenticated read-only endpoints, and add focused backend tests.
- Frontend: add an AI service module, shared AI response/chat components, contextual buttons in existing dashboard/detail/workspace components, and focused component/service tests.
- API: introduce read-only authenticated AI explanation/chat request and response contracts; no production mutation endpoints.
- Database: no schema migration expected; chat history is client-session state only for Phase 1B.
- Runtime: AI remains on-demand; no background jobs, autonomous analysis, shell access, direct provider database access, or mandatory paid provider.
