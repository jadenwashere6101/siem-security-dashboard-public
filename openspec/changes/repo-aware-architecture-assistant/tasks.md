## 1. Scope And Dependency Confirmation

- [x] 1.1 Re-read `AGENTS.md`, `docs/mac-vm-source-of-truth-policy.md`, the AI roadmap, and the completed Phase 1A/1B OpenSpecs before implementation.
- [x] 1.2 Confirm the implementation reuses `AiGateway`, `AiGatewayRequest`, AI metadata, and Phase 1B response display patterns rather than redesigning provider routing or analyst chat.
- [x] 1.3 Confirm implementation scope excludes analyst triage, SOC tool execution, fine-tuning, vector DB setup, shell execution, database access by the assistant, file writes by the assistant, autonomous cleanup, commits, pushes, VM work, deployment, and production mutation.

## 2. Source Policy And Trust Rules

- [x] 2.1 Create `core/ai/repo_sources.py` with trust-tier definitions for Tier 0 policy, Tier 1 current implementation, Tier 2 active specs/current docs, and Tier 3 historical/context-only sources.
- [x] 2.2 Implement allowlisted include patterns for current source, tests, schemas, migrations, active OpenSpecs, accepted specs, current docs, and selected runbooks.
- [x] 2.3 Implement exclusion patterns for `.git`, caches, build artifacts, `node_modules`, generated Sonar JSON/CSV, screenshots/images, `.env*`, private keys, logs, runtime artifacts, and oversized files.
- [x] 2.4 Add conflict-priority helpers proving Tier 0 policy beats lower-tier docs, current source beats planning docs for implemented behavior, and active/accepted specs beat archived specs.
- [x] 2.5 Add historical-labeling behavior for archived OpenSpecs, VM handoffs, internal AI notes, old roadmaps, decomposition plans, and cleanup plans.

## 3. Repository Index And Retrieval

- [x] 3.1 Create `core/ai/repo_index.py` with repository-root validation that only indexes files under the Mac source-of-truth repository.
- [x] 3.2 Implement deterministic file scanning without shell commands or background jobs.
- [x] 3.3 Implement chunking by headings/functions/classes where practical and bounded line windows otherwise.
- [x] 3.4 Attach chunk metadata including path, line start/end, trust tier, source kind, current/historical label, mtime, size, and content hash.
- [x] 3.5 Implement lexical/path/symbol scoring with boosts for Tier 0/Tier 1, exact file names, function/class names, route names, and OpenSpec capability names.
- [x] 3.6 Implement an in-process index cache keyed by path, mtime, size, and content hash, with explicit request refresh support.
- [x] 3.7 Return retrieval metadata for indexed file count, matched chunk count, refresh state, and excluded-match summaries without exposing excluded file contents.

## 4. Repo Assistant Service

- [x] 4.1 Create `core/ai/repo_assistant_service.py` with request validation for message, bounded client history, and optional refresh.
- [x] 4.2 Build a repo-assistant prompt that includes the safety preamble, retrieved snippets only, source metadata, and instructions to answer only with supplied evidence.
- [x] 4.3 Invoke `AiGateway.generate()` with repo-assistant request metadata and preserve provider/model/latency/cost/fallback metadata in responses.
- [x] 4.4 Return `insufficient_evidence=true` without gateway invocation when no allowed current evidence is retrieved.
- [x] 4.5 Validate model citations against the retrieved chunk set and fail closed with a grounding error when citations are missing or invalid.
- [x] 4.6 Redact sensitive values and ensure prompt construction excludes secret-bearing files and paths.
- [x] 4.7 Ensure service logging uses only safe metadata and never logs prompt text, chat history, retrieved file contents, credentials, or credential-bearing URLs.

## 5. Routes And Access Control

- [x] 5.1 Extend `routes/ai_routes.py` with thin `GET /ai/repo/status` and `POST /ai/repo/chat` routes or add a separate AI repo blueprint if that better preserves route clarity.
- [x] 5.2 Protect repo-assistant routes with existing `login_required` and `super_admin_required`.
- [x] 5.3 Validate JSON request bodies and return safe `400` errors for malformed payloads, oversized messages, or malformed history.
- [x] 5.4 Return structured normal AI states for disabled, unavailable, timeout, fallback-blocked, confirmation-required, configuration-error, failed, insufficient-evidence, and grounding-failure responses.
- [x] 5.5 Prove routes do not call database connections, mutation helpers, shell commands, commit/push/deployment helpers, or VM access paths.

## 6. Developer UI Surface

- [x] 6.1 Create `frontend/src/services/repoAssistantService.js` with repo status/chat requests using `buildSiemPath`, included credentials, abort signals, and shared JSON error parsing.
- [x] 6.2 Create `frontend/src/components/RepoArchitectureAssistantPanel.js` as a separate super-admin-only developer panel, not part of the floating SIEM chat.
- [x] 6.3 Display answer text, citations, trust/freshness labels, retrieval metadata, provider/model/latency/cost metadata, loading, retry, cancel, dismiss, and safe failure states.
- [x] 6.4 Modify `frontend/src/App.js` only as needed to expose the panel to authenticated super administrators and hide it from analysts/viewers.
- [x] 6.5 Reuse `AiResponsePanel` or shared display helpers where practical without coupling repo answers to SIEM visible-context chat.

## 7. Focused Documentation Corrections

- [x] 7.1 Review included docs for stale content that would materially confuse repo retrieval.
- [x] 7.2 Add only narrow historical/stale markers or index corrections when required by retrieval safety.
- [x] 7.3 Do not rewrite broad handoffs, archived specs, generated reports, or unrelated documentation.

## 8. Backend Tests

- [x] 8.1 Add tests for allowlisted source inclusion and excluded secret/runtime/generated/build/cache paths.
- [x] 8.2 Add tests for trust-tier conflict behavior using Tier 0 policy, current source, active specs, archived specs, and known stale docs.
- [x] 8.3 Add tests for chunk metadata, line ranges, source kind, historical/current labels, and index freshness refresh behavior.
- [x] 8.4 Add tests for lexical retrieval of representative questions: detection rules location, incident state flow, playbook update routes, relevant files for a feature, and project policy questions.
- [x] 8.5 Add service tests for grounded prompt construction, gateway metadata preservation, insufficient evidence without provider call, invalid citation fail-closed behavior, and secret-safe logging.
- [x] 8.6 Add route tests for unauthenticated, analyst, viewer, and super-admin access behavior.
- [x] 8.7 Add read-only regression tests proving repo-assistant requests do not call DB connections, shell commands, file write helpers, commit/push helpers, VM/deployment helpers, or production mutation paths.

## 9. Frontend Tests

- [x] 9.1 Add repo assistant service tests for request payloads, credentials, abort signals, response parsing, and error handling.
- [x] 9.2 Add component tests for super-admin visibility, analyst/viewer hidden state, loading, success, citations, trust labels, metadata, retry, cancel, dismiss, insufficient evidence, and grounding failure.
- [x] 9.3 Add an affected `App.js` test proving the repo assistant panel is separate from Phase 1B floating SIEM chat and does not appear for non-super-admin users.

## 10. Verification

- [x] 10.1 Run focused backend tests for repo source policy, indexing, retrieval, service, routes, RBAC, citations, freshness, and read-only safety.
- [x] 10.2 Run Python compilation for new and modified backend modules.
- [x] 10.3 Run focused frontend service/component tests for the repo assistant UI.
- [x] 10.4 Run `cd frontend && npm run build` because this phase adds a super-admin UI surface.
- [x] 10.5 Run `git diff --check`.
- [x] 10.6 Run `openspec validate repo-aware-architecture-assistant --strict`.
- [x] 10.7 Review the complete diff for unrelated changes, debug output, commented-out code, generated artifacts, secret exposure, broad doc rewrites, schema changes, background jobs, shell execution, file mutation paths, VM/deployment work, and analyst-chat scope drift.

## 11. Handoff

- [x] 11.1 Report canonical and excluded repository sources implemented.
- [x] 11.2 Report citation/freshness behavior and representative questions verified.
- [x] 11.3 Report any stale docs intentionally marked or left unchanged.
- [x] 11.4 Confirm no commit, push, VM access, deployment, migration, production mutation, or paid-provider setup occurred unless separately authorized.
- [x] 11.5 State whether VM sync is required after implementation review.
