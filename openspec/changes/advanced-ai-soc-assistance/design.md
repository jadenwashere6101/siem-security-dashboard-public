## Context

The current AI architecture has the right safety boundaries for Phase 6:

- `core/ai/gateway.py`, `providers.py`, `models.py`, and `config.py` own provider-neutral routing, local-first behavior, fallback states, latency, token estimates, and cost metadata.
- `core/ai/context_builder.py` centralizes grounded SIEM context for alerts, incidents, source IPs, recon activity, dashboard, response registry, detection, and general chat.
- `core/ai/soc_tools.py` and `soc_tool_executor.py` define and execute the fixed read-only tool allowlist with role checks, bounded limits, source metadata, redaction, and mutation-tool rejection.
- `core/ai/explainer_service.py` currently performs one deterministic tool-planning pass plus one final answer pass for chat/explain.
- `core/ai/draft_schemas.py` and `drafting_service.py` generate transient review-only drafts with explicit labels: AI-generated, read-only, not persisted, not applied, and requiring review before future application.
- `core/ai/action_schemas.py` and `action_service.py` keep production mutations behind preview, explicit confirmation, RBAC, idempotency, audit, and existing helper dispatch.
- `routes/ai_routes.py` is a thin authenticated route layer. `frontend/src/services/aiService.js` and `frontend/src/components/AiResponsePanel.js` already display AI answers, tool evidence, drafts, metadata, stale states, and approval-gated action review.

Phase 6 should compose these pieces. It should not add an autonomous agent, provider-side tool callbacks, direct database access, shell access, background telemetry analysis, or AI-controlled SOAR approval/blocking.

## Architecture Findings

The existing gateway is provider-neutral enough to reuse, but it has only generic `text_generation` capability and per-response metadata. Phase 6 needs a small routing extension so services can declare complexity inputs and expected capabilities without moving planning into provider adapters.

The existing SOC read-tool executor is already bounded and read-only. It lacks a higher-level workflow run contract that records ordered steps, validates step outputs before later steps consume them, and reports partial progress to the analyst.

Drafting is already separated from execution. Automatic drafting can reuse `create_draft()` only for narrow alert types and must keep the same transient, not-applied labels. The current frontend shows one action candidate for incident-note drafts; Phase 6 must not add automatic confirmation or auto-submit behavior.

Approval-gated actions already provide the production mutation boundary. Phase 6 recommendations and drafts may point analysts toward existing preview/confirm flows, but must not approve, block, retry, resume, or execute anything itself.

## Goals / Non-Goals

Goals:

- Provide guided multi-step investigation workflows for explicit analyst requests.
- Chain only existing read-only SOC tools through a bounded planner service.
- Correlate evidence across alerts, incidents, source-IP context, related events, response registry, audit metadata when authorized, and playbook execution history.
- Produce suggested response plans that distinguish evidence, uncertainty, recommended next steps, and required human confirmation.
- Automatically generate transient drafts only for narrow, high-context alert types.
- Add complexity-based model routing inputs and complete per-response and per-investigation observability.
- Give analysts visible progress, cancellation, partial results, evidence citations, recommendations, drafts, and failure states.

Non-goals:

- Autonomous SOC engine, background analysis, continuous telemetry monitoring, scheduled AI investigations, or silent token usage.
- Arbitrary planner, recursive agent loops, unrestricted tools, provider-owned tool execution, direct SQL, shell/file access, VM access, migrations, commits, pushes, deployments, or external writes.
- AI-controlled SOAR approval, blocking, retrying, resuming, abandoning, execution gating, or production decision making.
- Mandatory paid providers, speculative provider integrations, vector stores, fine-tuning, broad UI redesign, or refactoring unrelated workflows.

## Planner Ownership

Create a planner/workflow service under `core/ai`, for example `investigation_planner.py` and `investigation_service.py`.

The planner service owns:

- workflow templates and allowed step order;
- tool selection;
- tool-call depth and per-step budgets;
- validation of every tool output before later steps consume it;
- grounding/source citation assembly;
- recommendation and automatic-draft decisions;
- aggregate cost/latency/fallback observability;
- cancellation and partial-result classification.

Provider adapters remain limited to `supports()`, `readiness()`, and `generate()`. They receive bounded prompts and return text. They never receive tool handles, database handles, service objects, shell/file handles, approval callbacks, or mutation callbacks.

The planner may use deterministic templates first. If model-assisted planning is used later, the generated plan must be parsed as structured JSON and validated against the same allowlist before execution. Invalid plans fail closed or fall back to deterministic templates.

## Workflow Design

Add a request-scoped `InvestigationRun` contract:

- `run_id`: client/server generated opaque id.
- `status`: `queued`, `running`, `cancelled`, `success`, `partial`, `timeout`, `failed`, `insufficient_context`.
- `workflow_type`: `alert_investigation`, `incident_investigation`, `source_ip_investigation`, `recon_cluster_investigation`, `response_registry_review`, or `dashboard_anomaly_review`.
- `context_snapshot`: bounded context ids and source metadata, not raw secret-bearing evidence.
- `steps`: ordered `InvestigationStepResult` records.
- `recommendations`: suggested response plans only.
- `drafts`: optional transient draft responses.
- `observability`: aggregate provider/model/token/cost/latency/fallback/tool-call metadata.
- `labels`: `read_only=true`, `writes_performed=false`, `production_action_required_for_changes=true`.

Allowed step types:

- `build_context`: call `build_ai_context()`.
- `plan_read_tools`: deterministic or validated model plan.
- `execute_read_tool`: call `execute_tool_plan()` or a single validated tool from the existing allowlist.
- `validate_evidence`: confirm result shape, status, source metadata, truncation, role allowance, redaction, and expected identifiers.
- `correlate_evidence`: call the gateway to summarize only supplied context/tool evidence.
- `suggest_response_plan`: call the gateway or deterministic formatter to produce analyst next steps, prerequisites, risks, and confirmation requirements.
- `generate_transient_draft`: call `create_draft()` only for allowed draft policies.
- `finalize_summary`: assemble cited results, incomplete states, and metadata.

No other step types are allowed in Phase 6.

Default bounds:

- Maximum workflow depth: 8 total steps.
- Maximum SOC read-tool calls per investigation: 7 total, with no more than 5 in one planning pass.
- Maximum planning passes: 1.
- Maximum final/correlation generations: 2.
- Maximum automatic drafts per investigation: 1.
- Maximum per-tool rows: reuse the existing 25-row cap or a stricter tool cap.
- Default broad-search window: 24 hours, maximum 168 hours.
- Default total investigation timeout: 45 seconds.
- Default per-provider generation timeout: reuse gateway provider timeouts; workflow must stop before exceeding the total budget.
- Default per-tool execution budget: 5 seconds when practical; failed tools return partial metadata instead of blocking the run indefinitely.

Stopping conditions:

- step budget exhausted;
- tool-call budget exhausted;
- total timeout reached;
- cancellation requested;
- no meaningful context or tool evidence;
- validation failure on evidence needed for the next step;
- provider disabled/unavailable/fallback blocked;
- all planned questions answered with cited evidence.

Retries:

- Provider retry is at most one retry for transient timeout/unavailable states when budget remains and the retry does not trigger paid fallback without existing policy permission.
- Read-tool retry is at most one retry for transient internal failure when the tool is read-only, idempotent, and budget remains.
- Validation, RBAC, unsupported tool, mutation-like tool, stale context, and insufficient-context failures are not retried automatically.

Partial behavior:

- If one non-critical tool fails but other evidence is valid, return `partial` with the failed step, missing evidence, and safe recommended manual next checks.
- If a critical identifier lookup fails, return `insufficient_context` or `not_found` without generating unsupported conclusions.
- If a draft cannot be generated, keep the investigation summary and mark the draft step failed or skipped.

Cancellation:

- Frontend uses `AbortController` for request cancellation.
- Backend should check a request-scoped cancellation flag where practical for streaming/progress implementations. For non-streaming initial implementation, aborted client requests must not persist runs or continue into production actions.
- Cancelled runs return or render `cancelled`/`incomplete` and preserve any already-visible read-only evidence without implying completion.

## Evidence Validation And Grounding

Every tool result consumed by a later step must pass validation:

- status is `success` or explicitly accepted partial/truncated state;
- `read_only=true`;
- source metadata is present for non-empty evidence;
- expected ids match the current context snapshot, such as alert id, incident id, registry id, or source IP;
- evidence is redacted through existing AI redaction helpers;
- serialized evidence remains within prompt budget;
- forbidden or super-admin-only results are excluded for analyst users;
- mutation-like tool names or unknown fields are rejected before execution.

Final answers, correlations, recommendations, and drafts must cite source metadata from `AiContextSource` and `SocToolSource`. If evidence is missing or truncated, the analyst-facing result must say what was unavailable and avoid claiming that the assistant checked data that was not supplied.

## Guided Workflows

Alert investigation:

1. Build alert context.
2. Read alert detail and related events.
3. If a source IP exists, read source-IP context and bounded alert search.
4. Correlate with incidents, playbook executions, and response registry when present.
5. Suggest a response plan and optionally generate one allowed transient draft.

Incident investigation:

1. Build incident context.
2. Read incident timeline.
3. Search related alerts and source-IP context when identifiers are present.
4. Include playbook executions and response outcomes.
5. Summarize timeline, evidence gaps, recommended next steps, and optional transient incident-note draft.

Source-IP investigation:

1. Build source-IP context.
2. Search alerts, related events, incidents, response registry, and playbook executions for that IP.
3. Correlate returning-attacker, campaign, internet-noise, reputation, blocklist tracking, and outcome evidence.
4. Recommend analyst next steps without selecting or executing containment.

Recon cluster investigation:

1. Build recon activity context.
2. Read related events and source-IP context for bounded representative IPs only.
3. Correlate campaign membership, alert history, and incident eligibility.
4. Recommend escalation or monitoring criteria.

Response registry review:

1. Build registry context.
2. Read registry detail, related source-IP context, playbooks, and audit metadata only when authorized.
3. Explain current disposition versus requested action and actual outcome.
4. Recommend review steps without executing registry commands.

Dashboard anomaly review:

1. Build visible dashboard context.
2. Search bounded recent alerts/events matching visible filters.
3. Correlate top contributing source IPs and incidents.
4. Summarize likely drivers, uncertainty, and drill-down recommendations.

## Automatic Draft Boundaries

Automatic draft generation is allowed only when an explicit analyst investigation request targets a concrete alert/incident/source/recon object and the planner has enough validated evidence. It is not allowed for free-form general chat without a concrete target.

Allowed automatic draft policies:

- `incident_note` for high or critical alerts that are already linked to an incident, because the output is review text and the current Phase 5 boundary already supports preview/confirm for incident notes.
- `investigation_checklist` for high or critical alerts, source-IP investigations, recon clusters, and incidents, because it is read-only analyst guidance.
- `escalation_summary` for critical incidents or critical alerts with correlated incident evidence, because it is handoff text and remains transient.
- `response_recommendation` for high or critical alerts/incidents/source-IP context when response registry or playbook execution evidence exists, because it describes options and required approvals without executing.

Automatic drafting is not allowed for `detection_rule_change` or `playbook_draft` in Phase 6 because those can resemble production configuration changes and should remain explicit analyst-requested drafts. Automatic drafting is also skipped when evidence is insufficient, the workflow is partial due to critical failures, the gateway is disabled, provider output validation fails, or the selected target type is unsupported.

Automatic drafting does not mean automatic execution. Draft responses keep `persisted=false`, `applied=false`, and `approval_required_before_apply=true`. Any later production change still requires the existing `/ai/actions/preview` and `/ai/actions/confirm` path, role checks, exact payload review, idempotency, stale-source checks, and audit logging.

## Complexity-Based Routing

Add a small `AiRoutingProfile` or equivalent metadata object owned by the planner/gateway service boundary. Inputs:

- workflow type;
- context type;
- estimated prompt tokens;
- estimated tool evidence tokens;
- number of planned tool calls;
- number of successful/failed/truncated sources;
- draft requested/automatic draft eligible;
- structured-output need;
- local provider readiness and model name;
- fallback mode and paid fallback permission;
- remaining timeout budget.

Profiles:

- `simple`: no tools or one small context, no draft, concise answer.
- `standard`: bounded tool use, one final answer, no complex draft.
- `advanced`: multi-tool correlation, structured recommendation, or transient draft generation.

Routing behavior:

- Always prefer local provider when configured and capable.
- If complexity exceeds local capability or local provider times out, apply existing `local_only`, `ask_before_paid_fallback`, and `automatic_fallback` policy.
- `ask_before_paid_fallback` returns a clear confirmation-required state; it does not silently call a paid provider.
- `automatic_fallback` can use paid fallback only when current gateway configuration already allows it.
- If no provider can safely handle the selected profile within budget, return partial/failed state with evidence gathered so far and no fabricated conclusion.

Observability metadata:

- Per response: provider, model, mode, status, latency, prompt tokens, completion tokens, estimated cost, local/paid flag, fallback attempted/reason, error code.
- Per investigation: run status, workflow type, routing profile, planned/actual step counts, tool call counts/statuses, source counts, truncation, total latency, aggregate prompt/completion tokens, aggregate estimated cost, fallback path, retry count, timeout/cancellation state, automatic draft policy decision, and draft validation state.

## Analyst Experience

Reuse existing AI entry points and response panels where practical, adding a guided investigation view only if `AiResponsePanel` would become overloaded.

The analyst must see:

- live or staged progress by step name and status;
- read-only label and no-production-change state;
- evidence sources and citation counts;
- tool failures, forbidden tools, truncation, and omitted counts;
- recommendation cards that distinguish next checks from production actions;
- transient drafts with AI-generated/not-saved/not-applied labels;
- exact provider/model/cost/latency/fallback metadata;
- cancellation, retry, dismiss, stale-context, and incomplete-result states;
- a clear path to existing approval-gated action preview only when a valid draft/action candidate exists.

The UI must not imply that remediation, blocking, approval, playbook execution, registry command execution, or incident mutation occurred unless the existing confirmed action endpoint returns that outcome.

## File-Level Implementation Plan

Expected backend files:

- Create `core/ai/investigation_models.py` for run, step, routing profile, observability, and acceptance-state dataclasses.
- Create `core/ai/investigation_planner.py` for workflow templates, allowed step validation, automatic draft policy, and complexity classification.
- Create `core/ai/investigation_service.py` for orchestration across context builder, read-tool executor, gateway, drafting service, cancellation, partial results, and metadata aggregation.
- Modify `core/ai/models.py` only for small routing/observability metadata fields if necessary.
- Modify `core/ai/gateway.py` only to accept optional routing metadata/capability hints while preserving provider separation.
- Modify `routes/ai_routes.py` to add thin investigation run/progress/cancel endpoints, or one non-streaming `POST /ai/investigations` endpoint for the first implementation.
- Add `tests/test_ai_advanced_soc_assistance.py` and focused updates to existing AI tests only where contracts are intentionally reused.

Expected frontend files:

- Modify `frontend/src/services/aiService.js` to add investigation request/cancel helpers.
- Create `frontend/src/components/AiInvestigationPanel.js` or extend `AiResponsePanel.js` with a clearly separated investigation mode.
- Modify contextual AI entry-point components only to expose guided investigation actions where current Phase 1B actions already exist.
- Add or update focused tests for investigation progress, evidence, drafts, failure, cancellation, stale state, and metadata display.

## Acceptance Criteria

- Phase 6 runs only after an explicit authenticated analyst or super-admin request.
- Planner logic is separate from provider adapters.
- Only allowed step types and existing read-only SOC tools can run.
- Maximum depth, tool-call count, timeout, retry, and prompt-size limits are enforced.
- Tool outputs are validated before later steps consume them.
- Final answers, correlations, recommendations, and drafts are grounded in returned sources.
- Automatic drafts are limited to the allowed policies and remain transient, unpersisted, and unapplied.
- No production action occurs without existing explicit preview/confirm.
- Complexity routing reports inputs, selected profile, provider/model, fallback behavior, cost, tokens, and latency.
- Analyst UI clearly shows progress, evidence, recommendations, drafts, failures, partial results, cancellation, and metadata.
- Deterministic detections, existing correlation, RBAC, audit, idempotency, protected-target checks, fail-closed guards, and outcome labels are preserved.

## Focused Verification

Backend:

- Unit tests for workflow template validation, allowed step set, maximum depth, loop prevention, and unsupported/mutation step rejection.
- Unit tests for tool ordering, max tool calls, per-tool validation, source-id matching, redaction, truncation, and partial-result behavior.
- Tests for cancellation/timeout handling, no automatic retry on validation/RBAC failures, and bounded retry on transient read/provider failures.
- Tests proving no direct DB handles, shell/file access, mutation helpers, approval decisions, SOAR execution, registry commands, migrations, commits, pushes, deployments, or VM operations are reachable from the planner.
- Tests for automatic draft eligibility and skip reasons; generated drafts remain `persisted=false` and `applied=false`.
- Tests for production actions still requiring `/ai/actions/preview` and `/ai/actions/confirm`.
- Tests for complexity profile selection, fallback state preservation, aggregate cost/token/latency metadata, and provider disabled/unavailable states.

Frontend:

- Service tests for investigation request/cancel behavior and response parsing.
- Component tests for progress, evidence citations, recommendation display, automatic draft labels, partial failures, stale context, cancellation, retry, and metadata.
- Role-focused tests for audit evidence visibility and action-preview availability.

Manual:

- Browser verification of alert, incident, source-IP/recon, response registry, and dashboard guided investigation entry points.
- Visual review in dark theme for immediately noticeable progress, evidence, draft, failure, and incomplete states.
- Manual confirmation that no UI copy implies production remediation unless a confirmed action result says so.

Commands before handoff:

- Focused backend tests for the touched AI modules.
- Focused frontend tests for the touched AI UI/service modules.
- `npm run build` for UI implementation.
- `python3 -m py_compile` for touched Python modules.
- `git diff --check`.
- `openspec validate advanced-ai-soc-assistance --strict`.

## Risks / Trade-offs

- Planner scope creep: fixed workflow templates, fixed step types, no recursive loops, and explicit non-goals keep Phase 6 bounded.
- Local model weakness: deterministic planning and validation allow safe partial results without requiring paid providers.
- Evidence overrun: per-tool caps, prompt limits, truncation metadata, and source summaries keep prompts bounded.
- UI ambiguity: progress, read-only labels, and explicit outcome vocabulary prevent recommendations from looking like actions.
- Cost surprise: local-first routing and existing fallback policy prevent mandatory or silent paid usage.
- False confidence: insufficient-context and partial states must be first-class outcomes, not hidden warnings.

## Scope Exclusions

- Autonomous agent framework.
- New provider adapters or mandatory paid AI setup.
- Direct DB, shell, file, VM, migration, deployment, commit, push, or background telemetry access.
- New write tools, registry commands, SOAR approval/blocking/retry/resume/abandon actions, or playbook execution.
- Automatic detection-rule or playbook drafts.
- Automatic persistence, application, approval, confirmation, or execution of any draft or response plan.
- Broad frontend redesign or unrelated backend refactors.

## Future Phase Dependencies

- Durable investigation history, shared team annotations, streaming server-side progress, and persisted draft libraries require separate specs because they introduce storage, retention, audit, and privacy decisions.
- Additional automatic draft types require explicit alert-type policy, validation schemas, and UI review requirements.
- Real paid provider implementation or model-specific cost tables require separate provider specs unless already available through the gateway.
- AI-assisted SOAR orchestration, if ever desired, requires a separate autonomous-action safety spec and must not reuse Phase 6 investigation completion as approval.

## VM Sync Required After Implementation

Yes. This spec creation is Mac-only and needs no VM sync. A future implementation will change backend and frontend runtime behavior, so VM sync will be required only after review, commit/push authorization, and a separate deployment request.
