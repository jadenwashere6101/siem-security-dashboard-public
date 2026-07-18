## 1. Contract And Source Mapping

- [x] 1.1 Create the canonical SOC read-tool definitions under `core/ai`, including names, schemas, roles, limits, source metadata rules, and read-only markers.
- [x] 1.2 Map each tool to the canonical existing read path for alerts, events, source IP context, incidents, playbook executions, audit log, and response registry context.
- [x] 1.3 Add argument validators for ids, IP addresses, status/severity filters, time windows, limits, and unsupported tool names.
- [x] 1.4 Add secret-redaction handling for tool arguments, tool results, prompt evidence, response serialization, and logs.

## 2. Backend Executor

- [x] 2.1 Implement the centralized read-only tool executor with max-call, per-tool-limit, time-window, latency, truncation, and source-attribution enforcement.
- [x] 2.2 Reuse or narrowly extract existing read-only helpers for tool implementations without duplicating canonical query logic.
- [x] 2.3 Enforce analyst/super-admin access for SOC tools and super-admin-only access for `read_audit_log`.
- [x] 2.4 Ensure unsupported, malformed, excessive, forbidden, and mutation-like tool requests fail closed before any helper is called.
- [x] 2.5 Ensure providers never receive database handles, cursors, credentials, raw exceptions, or direct data-access capabilities.

## 3. AI Service Integration

- [x] 3.1 Extend the existing Phase 1B chat/explain service flow to accept explicit tool-assisted requests without replacing the existing response contract.
- [x] 3.2 Implement bounded tool planning using either validated gateway JSON planning or deterministic routing, with no recursive tool loops.
- [x] 3.3 Build final prompts from current SIEM context plus bounded tool evidence using supplied-evidence-only instructions.
- [x] 3.4 Return tool execution summaries, sources, truncation, read-only state, and Phase 1A gateway metadata in API responses.
- [x] 3.5 Preserve disabled, unavailable, timeout, fallback-blocked, invalid-plan, insufficient-context, and no-evidence states as safe structured responses.

## 4. Frontend Integration

- [x] 4.1 Extend `frontend/src/services/aiService.js` request/response handling for optional tool-assisted SIEM AI requests.
- [x] 4.2 Extend shared AI display utilities and `AiResponsePanel` to show read-only tool usage, statuses, source counts, truncation, provider/model, latency, and cost metadata.
- [x] 4.3 Preserve existing cancellation, retry, stale-response, dismissal, responsive layout, and role-gated analyst UI behavior.
- [x] 4.4 Confirm Phase 2 repo assistant remains separate from analyst SOC AI surfaces.

## 5. Backend Verification

- [x] 5.1 Add focused tests for all supported tool definitions, schemas, limits, source metadata, and unsupported-tool rejection.
- [x] 5.2 Add focused tests proving each tool calls its canonical read helper/path and returns bounded source-attributed evidence.
- [x] 5.3 Add regression tests proving mutation helpers for alert status, notes, playbook execution actions, registry commands, approval actions, blocklist changes, migrations, shell/file operations, and direct provider DB access are not called.
- [x] 5.4 Add RBAC tests for analyst-accessible tools, super-admin-only `read_audit_log`, unauthorized requests, and insufficient-role requests.
- [x] 5.5 Add tests for invalid tool plans, malformed arguments, excessive limits, truncation, insufficient evidence, provider disabled/unavailable states, and secret-safe logging/serialization.
- [x] 5.6 Run focused backend tests for Phase 1A/1B AI contracts and the new SOC read-tool tests.
- [x] 5.7 Run `python3 -m py_compile` for new and modified Python modules.

## 6. Frontend Verification

- [x] 6.1 Add focused service/component tests for tool-assisted request payloads, response rendering, tool status display, truncation display, retry, cancellation, and stale-response handling.
- [x] 6.2 Add focused tests confirming repo-assistant UI/service paths remain separate from analyst SIEM chat.
- [x] 6.3 Run focused Phase 3 frontend tests.
- [x] 6.4 Run `cd frontend && npm run build`.
- [ ] 6.5 Perform focused manual browser verification of the affected AI chat/explain surfaces, tool metadata display, loading/error states, cancellation, stale-response behavior, and responsive layout when local data/setup supports it.

## 7. Final Validation

- [x] 7.1 Review the final implementation for unnecessary abstraction, duplicated query logic, unsafe tool paths, dead/debug code, secret exposure, and UI wording that implies actions were taken.
- [x] 7.2 Run `git diff --check`.
- [x] 7.3 Run `openspec validate soc-assistant-read-tools --strict`.
- [x] 7.4 Confirm no commit, push, VM access, deployment, migration, or production mutation occurred during implementation unless separately authorized.
