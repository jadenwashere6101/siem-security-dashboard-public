## 1. Audit And Contract Alignment

- [x] 1.1 Re-read AGENTS.md and `docs/mac-vm-source-of-truth-policy.md` before implementation work.
- [x] 1.2 Confirm the implemented Phase 1A-5 AI contracts in `core/ai`, `routes/ai_routes.py`, `frontend/src/services/aiService.js`, and AI UI components.
- [x] 1.3 Trace the advanced investigation flow end to end: UI action -> frontend AI service -> AI route -> planner/service -> context builder -> read-tool executor -> gateway/drafting service -> response -> UI state.
- [x] 1.4 Confirm no direct DB, shell, file, VM, migration, deployment, commit, push, unsupported tool, or production mutation path is reachable from the planner.

## 2. Backend Planner And Investigation Contracts

- [x] 2.1 Add `core/ai/investigation_models.py` with run, step, routing profile, draft policy, observability, and result dataclasses.
- [x] 2.2 Add `core/ai/investigation_planner.py` with fixed workflow templates, allowed step validation, maximum depth/tool-call limits, stopping conditions, retry policy, and loop prevention.
- [x] 2.3 Add automatic draft eligibility policy for only `incident_note`, `investigation_checklist`, `escalation_summary`, and `response_recommendation`.
- [x] 2.4 Add complexity classification for `simple`, `standard`, and `advanced` routing profiles using prompt/tool/source/draft/timeout/provider-readiness inputs.
- [x] 2.5 Add evidence validation helpers for source-id matching, read-only markers, role restrictions, redaction, truncation, and prompt budget checks.

## 3. Backend Orchestration

- [x] 3.1 Add `core/ai/investigation_service.py` to orchestrate context building, read-tool planning/execution, evidence validation, correlation, response-plan generation, optional automatic draft generation, cancellation/timeout handling, partial results, and metadata aggregation.
- [x] 3.2 Reuse `build_ai_context()`, `execute_tool_plan()`, `tool_summary_for_prompt()`, `AiGateway.generate()`, and `create_draft()` rather than duplicating SIEM read or draft logic.
- [x] 3.3 Keep provider adapters unchanged except for minimal metadata/capability hints if required; planner ownership must remain outside providers.
- [x] 3.4 Preserve existing gateway fallback behavior for disabled, local-only, ask-before-paid-fallback, automatic fallback, timeout, unavailable, incapable, and failed states.
- [x] 3.5 Ensure failed, partial, timeout, cancelled, and insufficient-context runs still return safe observability metadata.

## 4. API Layer

- [x] 4.1 Add a thin authenticated route, preferably `POST /ai/investigations`, protected by existing analyst/super-admin RBAC.
- [x] 4.2 Add progress/cancel endpoints only if the implementation chooses server-tracked or streaming investigation runs; otherwise rely on request abort and stale-state handling.
- [x] 4.3 Keep route logic limited to auth, JSON parsing, service call, and JSON serialization.
- [x] 4.4 Do not add schema migrations or persisted investigation history unless a separate storage decision is explicitly made.

## 5. Frontend Analyst Experience

- [x] 5.1 Extend `frontend/src/services/aiService.js` with advanced investigation request and cancellation helpers.
- [x] 5.2 Create `AiInvestigationPanel.js` or a clearly separated investigation mode inside `AiResponsePanel.js`.
- [x] 5.3 Show ordered progress, evidence sources, correlation findings, recommendations, transient drafts, failures, partial results, cancellation, stale-context state, provider/model/cost/token/latency/fallback metadata, and no-production-change labels.
- [x] 5.4 Add guided investigation entry points only where existing contextual AI actions already exist: alert, incident, source IP/recon, response registry, and dashboard surfaces.
- [x] 5.5 Ensure recommendations and drafts do not look like production actions; action preview controls must continue to call only `/ai/actions/preview` and `/ai/actions/confirm`.

## 6. Backend Verification

- [x] 6.1 Add focused tests for workflow templates, allowed steps, depth bounds, loop prevention, stopping conditions, and unsupported/mutation-step rejection.
- [x] 6.2 Add focused tests for tool-call ordering, max call limits, argument validation, source-id matching, redaction, truncation, forbidden audit-log handling, and partial-result behavior.
- [x] 6.3 Add focused tests for cancellation, timeout, retry behavior, provider disabled/unavailable/fallback-blocked states, and no fabricated conclusions.
- [x] 6.4 Add focused tests proving automatic drafts remain unpersisted and unapplied and are generated only for allowed policies.
- [x] 6.5 Add focused tests proving production actions still require existing preview/confirm and that planner code cannot call mutation helpers directly.
- [x] 6.6 Add focused tests for routing profile classification and aggregate provider/model/token/cost/latency/fallback observability.

## 7. Frontend Verification

- [x] 7.1 Add service tests for investigation request, cancellation, failure parsing, and metadata parsing.
- [x] 7.2 Add component tests for progress states, evidence citation display, recommendation separation, automatic draft labels, failure/partial/cancelled states, stale-context handling, and metadata visibility.
- [x] 7.3 Add role-focused tests for forbidden evidence and action-preview affordances.
- [x] 7.4 Run manual browser verification of affected alert, incident, source-IP/recon, response registry, and dashboard workflows in dark theme.
- [x] 7.5 Confirm a human analyst can immediately see the guided investigation improvement and distinguish read-only AI output from production actions.

## 8. Final Validation And Handoff

- [x] 8.1 Run focused backend tests for touched AI modules.
- [x] 8.2 Run focused frontend tests for touched AI services/components.
- [x] 8.3 Run `python3 -m py_compile` for touched Python files.
- [x] 8.4 Run `npm run build` for frontend implementation.
- [x] 8.5 Run `git diff --check`.
- [x] 8.6 Run `openspec validate advanced-ai-soc-assistance --strict`.
- [x] 8.7 Document implementation verification, manual browser findings, remaining risks, and VM handoff needs.

## Implementation Verification Evidence

- Backend tests: `.venv/bin/python -m pytest tests/test_ai_advanced_soc_assistance.py tests/test_ai_explainer_and_chat.py tests/test_soc_assistant_read_tools.py tests/test_ai_drafting_assistant.py tests/test_ai_approval_gated_actions.py` passed with 45 passed, 6 skipped for unavailable PostgreSQL integration fixtures, and 1 existing Flask-Limiter in-memory warning.
- Frontend tests: `npm test -- --runInBand --watchAll=false src/services/aiService.test.js src/components/AiResponsePanel.test.js src/components/AlertDetailsPanel.test.js src/components/IncidentsPanel.test.js src/components/DashboardMetricsAi.test.js src/components/DashboardVisualsAi.test.js src/components/SourceIpContext.test.js src/components/ResponseRegistryPanel.test.js src/components/SocCommandCenter.test.js` passed with 102 passed. Existing React async `act(...)` warnings appeared in incident/source-IP tests.
- Python compile: `python3 -m py_compile core/ai/investigation_models.py core/ai/investigation_planner.py core/ai/investigation_service.py routes/ai_routes.py tests/test_ai_advanced_soc_assistance.py` passed.
- Frontend production build: `cd frontend && npm run build` passed.
- Repository checks: `git diff --check` passed.
- OpenSpec validation: `openspec validate advanced-ai-soc-assistance --strict` reported `Change 'advanced-ai-soc-assistance' is valid`; the command also emitted non-fatal PostHog DNS flush errors because network access is restricted.
- Manual browser verification: local headless Chrome screenshots under `/private/tmp/advanced-ai-visual-desktop.png`, `/private/tmp/advanced-ai-visual-mobile.png`, and `/private/tmp/advanced-ai-mobile-panel.png` confirmed dark-theme guided investigation entry points for dashboard, alert, incident, source-IP, and response-registry surfaces; visible review panel progress, source-cited evidence, partial state, read-only/no-production-change labels, transient draft labels, and responsive mobile wrapping. The final targeted Chrome process needed an interrupt after writing the PNG; the log showed Chrome updater/crashpad noise only.

## Scope Exclusions

- No autonomous agent framework, unrestricted planner, recursive model tool loops, direct DB access, shell/file access, VM access, migrations, deployment, commits, pushes, or background telemetry analysis.
- No new production write tools, SOAR approval/blocking/retry/resume/abandon control, response registry commands, playbook execution, or AI-controlled approval/blocking.
- No mandatory paid provider and no speculative provider integrations.
- No automatic detection-rule or playbook drafts.
- No automatic persistence, application, approval, confirmation, or execution of drafts or recommended response plans.

## VM Sync Required After Implementation

Yes. Spec creation alone requires no VM sync. A future implementation changes backend/frontend runtime behavior and will require a separate VM deployment only after review, commit/push authorization, and explicit deployment approval.
