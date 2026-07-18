## 1. Scope And Dependency Confirmation

- [x] 1.1 Re-read `AGENTS.md`, `docs/mac-vm-source-of-truth-policy.md`, the AI roadmap, and the Phase 1A `ai-gateway-foundation` OpenSpec before implementation.
- [x] 1.2 Confirm Phase 1A gateway files exist and reuse `AiGateway`, `AiGatewayRequest`, `AiGatewayResponse`, and metadata models rather than redesigning provider routing.
- [x] 1.3 Confirm implementation scope excludes repo assistance, AI tools, drafts, actions, autonomous behavior, direct provider DB access, shell access, schema migrations, broad UI redesign, commits, pushes, VM work, and deployment.

## 2. Backend Context Builder

- [x] 2.1 Create `core/ai/context_builder.py` with supported `context_type` validation for `alert`, `incident`, `source_ip`, `recon_activity`, `dashboard`, `response_registry`, `detection`, and `general`.
- [x] 2.2 Implement alert context using canonical alert detail data, alert intelligence, why-fired evidence when available, and bounded related events.
- [x] 2.3 Implement incident context using canonical incident detail and read-only incident timeline data.
- [x] 2.4 Implement source-IP context using the existing source-IP aggregation path without duplicating unrelated logic.
- [x] 2.5 Implement recon activity context using canonical recon activity detail and bounded related events.
- [x] 2.6 Implement dashboard context using current visible filters, summary metrics, timeline, top IPs, map markers, and bounded recent alerts.
- [x] 2.7 Implement response registry context using canonical registry detail and explicitly excluding registry command execution.
- [x] 2.8 Implement detection context using why-fired evidence, alert detection metadata, and severity/response matrix data where available.
- [x] 2.9 Add source attribution, generated timestamps, record ids, truncation state, omitted counts where known, and insufficient-context reasons to context payloads.
- [x] 2.10 Enforce per-section limits and final prompt/context size limits using Phase 1A configuration.

## 3. Backend Explainer Service

- [x] 3.1 Create `core/ai/explainer_service.py` to validate requests, call the context builder, construct bounded supplied-context-only prompts, invoke `AiGateway.generate()`, and map responses.
- [x] 3.2 Ensure prompts instruct the model to use only supplied SIEM context, identify uncertainty, avoid invented facts, and recommend analyst next steps without claiming actions were taken.
- [x] 3.3 Return structured insufficient-context responses without invoking the gateway when required context is missing, not found, inaccessible, or too thin to answer safely.
- [x] 3.4 Preserve Phase 1A metadata for provider, model, mode, status, latency, token estimates, cost, local/paid flags, fallback state, and error code.
- [x] 3.5 Ensure expected gateway states such as disabled, unavailable, timeout, fallback blocked, confirmation required, configuration error, and failed are returned as normal AI response states for UI rendering.

## 4. Backend Routes And Safety

- [x] 4.1 Extend `routes/ai_routes.py` with thin authenticated `POST /ai/explain` and `POST /ai/chat` routes.
- [x] 4.2 Protect both routes with `login_required` and `analyst_or_super_admin_required`.
- [x] 4.3 Validate JSON request bodies and return safe `400` errors for unsupported context types, invalid actions, missing identifiers, oversized messages, or malformed history.
- [x] 4.4 Return `404` for missing canonical alert, incident, recon activity, or registry records.
- [x] 4.5 Keep route logging secret-safe and avoid logging prompt text, chat history, raw context payloads, API keys, or credential-bearing URLs.
- [x] 4.6 Verify AI routes do not call mutation helpers or write database state.

## 5. Frontend Service Layer

- [x] 5.1 Create `frontend/src/services/aiService.js` with `getAiStatus()`, `requestAiExplanation()`, and `sendSiemChatMessage()` using `buildSiemPath`, included credentials, JSON parsing, and consistent error handling.
- [x] 5.2 Add request shaping helpers that preserve current visible context snapshots without including secrets or unrelated UI state.
- [x] 5.3 Add focused service tests for success, disabled/unavailable responses, validation errors, abort behavior, and error message parsing.

## 6. Shared AI UI Components

- [x] 6.1 Create `frontend/src/components/AiAssistantButton.js` for compact contextual actions with accessible labels, disabled state, loading state, and consistent styling.
- [x] 6.2 Create `frontend/src/components/AiResponsePanel.js` for answer text, source list, metadata, insufficient-context copy, disabled/unavailable/timeout/fallback states, retry, cancel, dismiss, and stale markers.
- [x] 6.3 Create `frontend/src/components/FloatingSiemChat.js` with client-session-only history, bounded submitted history, current visible context snapshots, cancellation, retry, dismiss/minimize behavior, and responsive layout.
- [x] 6.4 Add `frontend/src/utils/aiDisplay.js` if shared provider/cost/status labels are needed to avoid duplicating UI copy.
- [x] 6.5 Add focused component tests for loading, success, metadata display, failure states, retry, cancel, dismissal, stale response handling, keyboard accessibility, and responsive-safe rendering.

## 7. Contextual Entry Points

- [x] 7.1 Add dashboard AI actions near relevant dashboard metrics/chart headers without changing the dashboard layout beyond the new AI controls.
- [x] 7.2 Add alert detail AI actions in `AlertDetailsPanel` for explaining the alert, importance, and investigation recommendations.
- [x] 7.3 Add incident detail AI actions in `IncidentsPanel` for summarizing incidents and recommending next steps.
- [x] 7.4 Add source-IP AI actions in `SourceIpContext` for explaining IPs, reconnaissance assessment, and activity summary.
- [x] 7.5 Add recon activity AI actions in `SocCommandCenter` where recon activity context is visible.
- [x] 7.6 Add response registry AI action in `ResponseRegistryPanel` for explaining the selected response record.
- [x] 7.7 Add floating SIEM chat to `App.js` for authenticated analyst/super-admin users and pass active section, visible dashboard filters/summary, selected alert, incident, source IP, recon, and registry context where available.
- [x] 7.8 Hide or disable AI entry points for unauthenticated or viewer users consistently with backend RBAC.

## 8. Backend Tests

- [x] 8.1 Add context-builder tests for every supported context type and canonical source path.
- [x] 8.2 Add context limit/truncation/source-attribution tests.
- [x] 8.3 Add insufficient-context tests for missing identifiers, not-found records, empty context, and oversized prompt construction.
- [x] 8.4 Add explainer-service tests proving Phase 1A gateway metadata is preserved and expected gateway failure states are mapped safely.
- [x] 8.5 Add route tests for authentication, RBAC, validation, not-found, successful explanation, successful chat, disabled AI, timeout/unavailable/fallback states, and secret-safe errors.
- [x] 8.6 Add read-only regression tests or mocks proving AI endpoints do not call mutation helpers, shell commands, provider direct DB access, registry commands, alert/incident mutations, SOAR actions, ingest, or migrations.

## 9. Frontend Tests

- [x] 9.1 Add AI service tests for request payloads, credentials, abort signals, response parsing, and error handling.
- [x] 9.2 Add shared AI button/response panel/chat tests for success, loading, retry, cancel, dismiss, stale responses, metadata, source display, insufficient context, and gateway failure states.
- [x] 9.3 Add affected component tests for dashboard, alert detail, incidents, source-IP context, recon activity, response registry, and floating chat visibility/behavior.
- [x] 9.4 Add tests proving chat history is component state only and not written to local storage or sent unbounded.

## 10. Manual UI Verification

- [ ] 10.1 Run the frontend locally and visually verify dashboard AI controls, loading, response, retry, cancel, dismiss, metadata, and responsive behavior.
- [ ] 10.2 Verify alert detail, incident detail, source-IP context, recon activity, and response registry AI entry points in normal analyst workflows.
- [ ] 10.3 Verify floating chat across navigation, scroll, selected-context changes, stale-response handling, minimized/dismissed state, and mobile/narrow layout.
- [ ] 10.4 Verify disabled, unavailable, timeout, fallback-blocked, confirmation-required, and insufficient-context states are understandable to an analyst.

## 11. Final Verification

- [x] 11.1 Run focused backend tests covering AI context builder, explainer service, routes, RBAC, metadata, and read-only safety.
- [x] 11.2 Run Python compilation for all new and modified backend modules.
- [x] 11.3 Run focused frontend service/component tests covering all affected AI UI paths.
- [x] 11.4 Run `npm run build` in `frontend` because Phase 1B changes analyst-facing UI.
- [x] 11.5 Run `git diff --check`.
- [x] 11.6 Run `openspec validate ai-explainer-and-siem-chat --strict`.
- [x] 11.7 Review the complete diff for unrelated changes, debug output, commented-out code, duplicate context logic, secret exposure, accidental mutation paths, broad UI redesign, schema changes, deployment changes, and unintended generated files.

## 12. Handoff

- [x] 12.1 Document that Phase 2 repo assistance, Phase 3 tools, Phase 4 drafting, Phase 5 actions, and Phase 6 autonomy/planning require separate OpenSpec changes.
- [x] 12.2 Report exact automated test, build, OpenSpec validation, `git diff --check`, and manual browser verification results.
- [x] 12.3 Confirm no commit, push, VM access, deployment, schema migration, or production mutation occurred unless separately authorized.
- [x] 12.4 Report that VM sync is required after implementation review because this phase changes backend and frontend runtime behavior.
