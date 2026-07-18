## Context

Phase 1A provides `core/ai` with provider-neutral gateway routing, local-first mode, bounded provider timeouts, standardized metadata, and `GET /ai/status`. Phase 1B adds `POST /ai/explain`, `POST /ai/chat`, `core/ai/context_builder.py`, `core/ai/explainer_service.py`, shared frontend AI components, and a client-session-only SIEM chat. Phase 2 adds a separate super-admin repo assistant and must remain separate from analyst SOC investigation.

The current SIEM already has the read paths Phase 3 needs:

- Alerts/events/recon: `routes/alerts_events_routes.py` exposes `/alerts`, `/alerts/<id>`, `/alerts/<id>/related-events`, `/alerts/<id>/why-fired`, `/events/search`, `/recon-activities`, and recon detail/related-events logic.
- Incidents: `routes/incident_routes.py` exposes `/incidents`, `/incidents/<id>`, and `/incidents/<id>/timeline`; `build_readonly_incident_timeline()` is explicitly read-only and `core.incident_store` owns incident detail/list helpers.
- Source IP: `routes/source_ip_context_routes.py` owns the canonical source-IP aggregation for alerts, incidents, queue, blocklist, reputation, playbook executions, returning attacker, campaigns, internet-noise, and response outcomes.
- Playbooks/responses: `core.playbook_store.list_playbook_executions()` and `routes/playbook_routes.py` expose execution read paths; `core.indicator_response_registry.get_registry_detail()` and response registry GET routes expose registry context while `/response-registry/commands` is a mutation path and must remain excluded.
- Audit log: `routes/admin_routes.py` exposes `/admin/audit-log` under `super_admin_required`.

Phase 3 should let the AI investigate by calling a small fixed set of read tools through existing service/helper paths. It must not create raw DB access for providers, shell execution, autonomous background runs, write tools, drafts, or approval-gated actions.

## Goals / Non-Goals

**Goals:**

- Define one canonical read-tool contract for Phase 3 SOC investigation tools.
- Add a central backend tool registry/executor that validates schemas, applies RBAC-aware policy, enforces limits, calls canonical read helpers, and returns source-attributed evidence.
- Extend the existing Phase 1B SIEM chat/explainer service so tool-assisted investigation is available only for explicit analyst AI requests.
- Preserve Phase 1A gateway metadata and Phase 1B grounded response behavior.
- Make tool execution bounded, deterministic, secret-safe, and auditable enough for read-only traceability without logging prompt/evidence contents.
- Add focused tests that prove supported tools work, unsupported/mutation tools are rejected, and no production-write helpers are called.

**Non-Goals:**

- A general-purpose agent framework or arbitrary tool plugin system.
- Direct database access from AI providers or model-selected SQL.
- Shell access, file access, repo assistant retrieval, VM access, deployment, migrations, commits, pushes, or production mutation.
- Draft generation, alert/incident/registry changes, SOAR approval, blocklist changes, playbook execution creation/retry/abandon/resume, or autonomous background analysis.
- New paid-provider adapter work.
- Broad UI redesign or new analyst workflow separate from the existing SIEM AI chat/response surface.

## Decisions

### Add a fixed Phase 3 read-tool contract under `core/ai`

Create a canonical contract in `core/ai/soc_tools.py` or a small package `core/ai/soc_tools/` if implementation needs separation:

- `SocToolDefinition`: name, description, input schema, output source type, minimum role, max result count, timeout/limit policy, and canonical source helper.
- `SocToolRequest`: tool name, validated arguments, request id/turn id, actor role, and parent AI context metadata.
- `SocToolResult`: status, data, sources, truncated flag, omitted count, error code, latency, and read-only marker.
- `SocToolExecutionSummary`: ordered tool calls, statuses, source counts, truncation, and refusal reasons.

The initial supported tool names are exactly:

- `search_alerts`
- `get_alert_detail`
- `get_related_events`
- `get_source_ip_context`
- `search_incidents`
- `get_incident_timeline`
- `list_playbook_executions`
- `read_audit_log`
- `get_response_registry_context`

Rationale: the roadmap names these tools explicitly. A fixed registry gives immediate value and prevents Phase 3 from becoming a speculative tool framework. New tools can be added later by adding a definition and tests.

Alternative considered: let model output arbitrary endpoint URLs. Rejected because it would bypass schema validation, result limits, source attribution, and mutation-path filtering.

### Centralize execution in a single read-only executor

Add `core/ai/soc_tool_executor.py` or equivalent. Routes do not execute tools directly; `explainer_service` delegates to the executor when tool-assisted mode is needed. The executor SHALL:

- validate tool names and arguments against the canonical definitions;
- reject any tool not in the allowlist;
- enforce max calls per AI request, per-tool result limits, and safe time windows;
- call existing read helpers or extracted read-only helper functions;
- attach source metadata for every result;
- classify failures as validation, not found, forbidden, unavailable, timeout, truncated, or failed;
- never pass database handles, raw cursor objects, credentials, or internal exceptions to AI providers.

Default bounds:

- max tool calls per AI request: 5;
- max result rows per tool call: 25 unless the existing source path has a stricter limit;
- default time window for broad searches: last 24 hours when no narrower visible context is supplied;
- max serialized tool-evidence chars: governed by `AI_MAX_PROMPT_CHARS` with Phase 1B lower-priority truncation.

Rationale: one executor is easier to test and audit than placing tool execution inside each route or frontend component.

Alternative considered: execute tools in the frontend through existing services. Rejected because the backend must validate tool usage, apply RBAC, and construct a single grounded prompt without trusting client-side tool results.

### Reuse canonical read helpers; extract narrowly only when needed

Each tool maps to current read behavior:

| Tool | Canonical source |
| --- | --- |
| `search_alerts` | alert list filter/query helpers behind `/alerts` in `routes/alerts_events_routes.py` |
| `get_alert_detail` | `/alerts/<id>` alert payload logic plus response outcome/intelligence helpers |
| `get_related_events` | `/alerts/<id>/related-events`, recon related-events logic, and `/events/search` filtering semantics |
| `get_source_ip_context` | existing `/source-ip-context` aggregation helpers |
| `search_incidents` | `core.incident_store.list_incidents()` and `/incidents` filters |
| `get_incident_timeline` | `core.incident_store.get_incident_detail()` plus `build_readonly_incident_timeline()` and outcome timeline entries |
| `list_playbook_executions` | `core.playbook_store.list_playbook_executions()` plus existing execution serialization/outcome enrichment |
| `read_audit_log` | `/admin/audit-log` semantics; super-admin only |
| `get_response_registry_context` | `core.indicator_response_registry.get_registry_detail()` and safe list/detail helpers, never command execution |

If current route code hides useful read logic in Flask request handlers, implementation may extract small helper functions into `core` or route-local helpers. It must not duplicate complex SQL when a helper already exists.

### Tool-assisted prompting remains model-mediated but bounded

Phase 3 may use a simple two-step service flow:

1. Ask the AI gateway to propose a small JSON tool plan from the user question and current context.
2. Validate and execute the requested tools.
3. Ask the AI gateway for the final answer using only the original context plus tool results.

If the local model cannot produce valid JSON plans reliably, implementation may use deterministic keyword routing for the initial Phase 3 tool plan, as long as the same canonical executor and response contract are used. This is not a scope expansion because the value is safe read-tool execution, not model autonomy.

The service must not loop indefinitely. No recursive tool calls are allowed. A single request may have one planning pass and one final-answer pass, or a deterministic tool plan plus one final-answer pass.

### Extend Phase 1B response contract without replacing it

`POST /ai/chat` and `POST /ai/explain` should remain the analyst entry points. Add optional request fields such as:

```json
{
  "use_tools": true,
  "tool_policy": {
    "max_tool_calls": 5,
    "time_window_hours": 24
  }
}
```

Responses extend the existing Phase 1B shape with:

```json
{
  "tools": {
    "used": true,
    "calls": [],
    "sources": [],
    "truncated": false,
    "omitted_count": 0,
    "read_only": true
  }
}
```

Expected AI availability states such as disabled, timeout, fallback blocked, invalid tool plan, insufficient context, and no tool evidence should return structured `200` responses where practical so the existing response panel can render a normal analyst-facing state. Invalid client input remains `400`; auth/RBAC remains existing `401/403`.

Rationale: analysts should not need to learn a second SOC chat UI. The existing UI can show when deeper read tools were used.

### RBAC and audit/read traceability

All Phase 3 SOC tools require authenticated analyst or super-admin access except `read_audit_log`, which requires super-admin. If a mixed tool plan contains `read_audit_log` for an analyst, the executor must reject that tool and continue only if the remaining plan can still answer safely; otherwise return insufficient evidence or forbidden tool status.

Audit logging of the AI read request is optional only if the existing project does not audit read-only views. If added, log only safe metadata: actor, route, tool names, statuses, counts, latency, and error codes. Never log prompt text, chat history, tool result bodies, credentials, source-IP secrets, or full evidence.

### Frontend uses existing AI surfaces

Extend `frontend/src/services/aiService.js` to send `use_tools` when the user asks for deeper investigation or when the relevant contextual action explicitly requires tools. Extend `AiResponsePanel` and related display utilities to show:

- tools used/not used;
- tool names and statuses;
- source counts and truncation;
- read-only label;
- forbidden/insufficient-evidence states.

Do not add a new sidebar section. Keep the repo assistant separate.

## Risks / Trade-offs

- [Model asks for unsafe or unknown tools] -> Validate against the fixed registry and reject unknown or mutation-like tool names before execution.
- [Tool results make prompts too large] -> Enforce per-tool row limits, serialized evidence limits, source summaries, and final prompt guard through Phase 1A `AI_MAX_PROMPT_CHARS`.
- [Existing route logic is not reusable without Flask request state] -> Extract small read-only helpers only where necessary; do not copy broad SQL into AI modules.
- [Analyst role sees super-admin audit data] -> Mark `read_audit_log` super-admin only and test analyst rejection.
- [Tool execution accidentally mutates state] -> Tests mock representative mutation helpers/routes and assert they are not called; executor allowlist contains only GET/read helper mappings.
- [Local models produce invalid tool JSON] -> Service fails safely or uses deterministic routing for initial plans; no autonomous loops.
- [Frontend makes tool use look like action taken] -> UI labels must say read-only investigation/evidence, not execution or remediation.

## Migration Plan

1. Implement backend read-tool definitions, executor, service integration, and focused tests on the Mac repository only.
2. Add narrow helper extraction for canonical read paths only if needed.
3. Extend existing frontend AI request/response components minimally and add focused tests.
4. Run focused backend/frontend tests, Python compilation, frontend build, `git diff --check`, and `openspec validate soc-assistant-read-tools --strict`.
5. No VM work occurs during implementation. Because implementation changes backend and frontend runtime behavior, VM sync will be required later only after review, commit/push authorization, and a separate deployment task.

Rollback is code-only: disable tool-assisted request handling or remove the new tool modules/UI extensions. No database rollback is expected.

## Future Phase Dependencies

Phase 4 drafting can reuse read-tool evidence as grounding for draft recommendations, but draft creation must remain separate from tool execution and must not persist without explicit analyst review.

Phase 5 approval-gated actions can reuse the tool-result source attribution and read-only/mutation vocabulary to show what evidence informed an action, but actions must use separate approval and execution contracts.

Future provider work can improve planning quality, but providers still must not receive direct database handles or mutation capabilities.

## Open Questions

- None blocking. The implementation may choose model-generated JSON planning or deterministic initial routing based on focused reliability tests, provided the canonical executor and fixed tool contract are preserved.
