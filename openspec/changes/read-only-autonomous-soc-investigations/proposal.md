## Why

The scheduled SOC briefing runtime can now create durable read-only jobs, runs, steps, and briefing lifecycle records, but it intentionally does not investigate evidence or generate briefing content. This change adds the advisory investigation engine that runs inside that runtime while preserving all AI, SOC tool, audit, and production-action boundaries.

## What Changes

- Add a read-only autonomous investigation engine invoked by the scheduled SOC briefing worker after a job is claimed and an isolated run exists.
- Reuse the existing AI Gateway and bounded SOC read tools to investigate new alerts, incidents, recon activity, monitored indicators, and related evidence.
- Add deterministic planning and deduplication so the engine avoids re-investigating the same schedule window, entity, or evidence bundle unnecessarily.
- Persist bounded investigation results, safe evidence references, tool-call audit records, concise decision summaries, and structured briefing content into the runtime tables created by `scheduled-soc-briefing-runtime`.
- Define completion states for successful, partial, skipped, blocked, failed, provider-unavailable, provider-timeout, and budget-exhausted investigations.
- Preserve read-only advisory behavior: no model-generated SQL, no direct model database access, no provider-side tool execution, no shell/file/subprocess/eval/exec, no production mutations, no SOAR execution, no Slack delivery, no paid fallback without explicit policy, and no hidden chain-of-thought storage.

Out of scope: briefing history UI, Slack delivery, Mini PC/Ollama setup, model selection policy changes, draft generation, approval decisions, production actions, direct AI database access, and additional scheduling/runtime tables beyond narrow additive metadata if implementation proves necessary.

## Capabilities

### New Capabilities

- `read-only-autonomous-soc-investigations`: Scheduled read-only investigation planning, bounded SOC read-tool evidence collection, AI Gateway briefing-content generation, deduplication, advisory result persistence, audit logging, and degraded-state handling.

### Modified Capabilities

- None.

## Impact

- Expected backend areas: `core/ai/soc_briefing_worker.py`, `core/ai/soc_briefing_runtime_store.py`, new investigation engine/service modules under `core/ai/`, existing `core/ai/gateway.py`, `core/ai/investigation_service.py`, `core/ai/soc_tools.py`, `core/ai/soc_tool_executor.py`, and audit helpers.
- Expected persistence impact: reuse `soc_briefing_runs`, `soc_briefing_run_steps`, and `soc_briefings`; any migration must be additive, narrow, and only for investigation metadata or deduplication indexes not already present.
- Expected tests: focused unit and integration tests for planning, deduplication, budget enforcement, read-tool allowlisting, provider disabled/unavailable outcomes, persistence failures, audit records, and absence of mutation paths.
- Expected docs: narrow updates to scheduled briefing runtime docs, AI architecture documentation, verification checklist, and VM handoff/runbook notes for the new advisory investigation phase.
