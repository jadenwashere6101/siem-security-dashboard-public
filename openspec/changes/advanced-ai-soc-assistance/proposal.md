## Why

Phases 1A-5 established safe on-demand AI assistance, read-only SOC tools, transient drafts, and explicit approval-gated actions, but analysts still have to manually sequence deeper investigations and correlate evidence across several SIEM surfaces. Phase 6 adds guided multi-step SOC assistance that remains bounded, source-cited, interruptible, and human-controlled.

## What Changes

- Add an `advanced-ai-soc-assistance` capability for guided investigation runs that coordinate existing SIEM context, fixed read-only tools, recommendations, and selected automatic draft generation.
- Introduce a planner-owned workflow service that is separate from provider adapters and never grants providers direct database, shell, file, SOAR, or mutation access.
- Define allowed workflow steps, maximum tool-call depth, timeout budgets, cancellation, retries, stopping conditions, partial-result behavior, loop prevention, and validation between steps.
- Extend model routing metadata so each response and investigation reports provider, model, token estimate, estimated cost, latency, complexity inputs, fallback path, and failure state.
- Add analyst-facing progress, evidence, recommendation, draft, failure, cancellation, and incomplete-result states using existing AI UI patterns.
- Keep automatic drafts transient and unapplied; production actions continue to require the existing explicit preview/confirm boundary.
- Preserve deterministic detections, correlation engines, RBAC, audit logging, idempotency, protected-target checks, fail-closed provider guards, and simulated-vs-real outcome labeling.

## Capabilities

### New Capabilities

- `advanced-ai-soc-assistance`: Guided, bounded, source-grounded SOC investigation workflows with safe tool chaining, correlation summaries, suggested response plans, narrowly scoped automatic draft generation, complexity-based model routing metadata, and analyst-visible observability.

### Modified Capabilities

- None. Phase 6 reuses existing AI gateway, explainer/chat, SOC read tools, drafting, and approval-gated action capabilities without changing their standalone contracts.

## Impact

- Expected backend implementation areas: `core/ai/*` for planner/workflow/routing metadata extensions, `routes/ai_routes.py` for thin run/progress/cancel endpoints, existing read-tool and drafting services, and focused AI tests.
- Expected frontend implementation areas: `frontend/src/services/aiService.js`, `frontend/src/components/AiResponsePanel.js` or a sibling investigation panel, existing contextual AI entry points, and focused component/service tests.
- No paid provider is mandatory. No schema migration is required unless implementation chooses durable investigation run history; the preferred design keeps runs request/session scoped.
- Specs/docs/tests alone do not require VM sync. Runtime implementation later will require VM sync only after review, commit/push authorization, and a separate deployment task.
