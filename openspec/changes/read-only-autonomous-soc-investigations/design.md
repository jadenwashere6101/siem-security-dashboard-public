## Context

`scheduled-soc-briefing-runtime` provides PostgreSQL-backed schedules, windows, jobs, leases, isolated runs, durable run steps, briefing lifecycle rows, service identity, heartbeat, and failure states. It deliberately stops before autonomous evidence collection or briefing content generation.

The repository already has request-scoped AI investigation code, an `AiGateway`, fixed SOC read-tool definitions, a local SOC tool executor, redaction helpers, and AI drafting/action boundaries. This change turns those existing pieces into a scheduled, read-only investigation engine that can run inside the briefing worker without widening authority.

## Goals / Non-Goals

**Goals:**

- Run a bounded read-only investigation for each claimed scheduled briefing run.
- Build deterministic investigation plans for alerts, incidents, recon activity, monitored indicators, source IPs, response registry entries, and related evidence.
- Execute only approved SOC read tools locally under `scheduled_soc_briefing_worker`.
- Deduplicate already-investigated entities and evidence bundles for the same or recent schedule windows.
- Generate structured advisory briefing content and persist it in existing briefing lifecycle records.
- Persist tool calls, sanitized inputs, evidence references, timing, status, errors, and concise decision summaries.
- Handle disabled, local-only unavailable, provider timeout, budget-exhausted, partial, and failed states explicitly.

**Non-Goals:**

- Briefing history UI, Slack delivery, Mini PC/Ollama setup, model selection policy changes, paid-provider fallback policy, draft generation, SOAR execution, approval decisions, incident/note mutations, direct database access by the AI model, provider-side tool execution, shell/file/subprocess/eval/exec, or hidden chain-of-thought storage.

## Decisions

1. Add a scheduled investigation engine, not a new scheduler.

The phase-one worker remains responsible for due schedules, job claiming, leases, heartbeats, stale recovery, and graceful shutdown. After it creates an isolated run, it calls a new engine such as `core/ai/soc_briefing_investigation_engine.py`. The engine returns a persisted outcome before the lease owner completes the job.

Alternative: add a separate autonomous worker. Rejected because it would duplicate leases, heartbeat, catch-up, and failure recovery.

2. Use deterministic local planning before any model call.

The engine creates an investigation manifest from the schedule window and due candidates: new/recent alerts, open/incidental incidents, recon activity, monitored indicators, response registry records, source IP context, and related evidence. Planning is rule-bound and non-recursive. The model may summarize or rank already-collected evidence, but it cannot request tools directly or expand the plan.

Alternative: let the model plan tool calls. Rejected because provider-side or raw prompt-to-tool execution would weaken existing safety boundaries.

3. Collect evidence through one bounded SOC read-tool pass.

The engine reuses `core/ai/soc_tools.py` and `core/ai/soc_tool_executor.py`. Tool names and arguments are validated before execution; limits are capped by existing tool definitions and stricter scheduled budgets. Each tool call is recorded as a run step with sanitized arguments, source references, truncation metadata, latency, status, and errors.

4. Persist deduplication keys locally.

Deduplication is based on deterministic keys stored in run/step/briefing metadata or a narrow additive table if implementation cannot query metadata safely. Keys include schedule id, window end, entity type, entity id or normalized indicator, evidence fingerprint, and investigation profile. Recent successful or partial advisory results suppress duplicate investigation while preserving a skipped step with reason `duplicate_recent_investigation`.

5. Treat budgets as hard stop conditions.

Default implementation budgets should be configuration-backed and testable: maximum runtime, maximum entities per run, maximum tool calls, maximum rows per tool, maximum evidence reference count, maximum prompt evidence characters, maximum prompt tokens, maximum completion tokens, and maximum estimated cost. Exceeding a budget produces `partial` or `budget_exhausted`, never an unbounded loop.

6. Use the AI Gateway only for bounded synthesis.

The prompt includes sanitized evidence summaries, source references, required JSON output schema, read-only policy, and budget metadata. The request uses existing gateway timeout and mode handling. Paid fallback is blocked for scheduled autonomous work unless a future explicit policy permits it. Provider responses must be parsed as data; invalid JSON or schema violations produce failed or partial outcomes.

7. Store structured briefing content, not UI state.

The engine writes `soc_briefings.sections` and related run metadata with consistent sections: `alerts_reviewed`, `dismissed_low_priority_findings`, `escalations`, `critical_findings`, `evidence`, and `recommendations`. Content is advisory, concise, source-referenced, and contains no hidden chain-of-thought.

8. Fail closed on persistence and audit failures.

Run, step, briefing, and audit persistence failures abort the active job transaction where possible and surface explicit failure codes. Slack failure remains out of scope and cannot affect saved briefings in this change.

## Risks / Trade-offs

- [Evidence gaps] Some desired recon or monitored-indicator views may not yet have dedicated SOC read tools. Mitigation: use existing approved read tools first and add only read-only tool definitions with bounded limits if required.
- [Metadata dedup queries] JSON metadata dedup can be awkward and slow. Mitigation: prefer deterministic indexed columns already available; add a narrow additive dedup table only if tests show it is necessary.
- [Provider formatting drift] Models can return malformed JSON. Mitigation: validate schema, persist the raw failure metadata safely, and fall back to deterministic partial summaries from collected evidence.
- [Sensitive evidence] Tool data may include internal details. Mitigation: use existing redaction helpers, evidence references, prompt compaction, and local-only behavior by default.

## Migration Plan

Mac AI implementation updates source, tests, and docs only. Any schema change must be additive and limited to investigation deduplication or briefing metadata indexes. VM AI later applies the approved commit and any migration through the existing deployment workflow only after explicit commit/push/deploy authorization.

Rollback disables or reverts the investigation engine invocation while leaving the phase-one scheduled runtime intact. Existing briefing/run/step rows remain preserved for audit history.

## Open Questions

- Exact default budgets should be finalized during implementation against existing runtime configuration patterns.
- If monitored indicators lack enough read-only coverage, implementation should add the smallest bounded SOC read tool rather than bypassing the executor.
