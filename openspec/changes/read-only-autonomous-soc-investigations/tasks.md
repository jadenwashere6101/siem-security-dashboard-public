## 1. Investigation Engine Structure

- [x] 1.1 Add a scheduled investigation engine module that accepts an already-claimed runtime job/run and returns explicit success, partial, skipped, blocked, failed, provider-unavailable, provider-timeout, budget-exhausted, or persistence-failed outcomes.
- [x] 1.2 Wire the phase-one scheduled briefing worker to invoke the engine only after creating an isolated run and only while holding the matching job lease.
- [x] 1.3 Keep scheduling, catch-up, leases, heartbeat, stale recovery, and systemd behavior owned by the existing runtime.

## 2. Planning and Deduplication

- [x] 2.1 Implement deterministic candidate planning for new alerts, incidents, recon activity, monitored indicators, response registry records, source IP context, and related evidence.
- [x] 2.2 Enforce maximum candidate count and persist skipped candidate reasons.
- [x] 2.3 Implement deterministic deduplication keys for schedule window, entity identity, normalized indicator, evidence fingerprint, and investigation profile.
- [x] 2.4 Add narrow additive migration/index support only if existing run, step, and briefing metadata cannot support efficient deduplication safely.

## 3. Bounded Evidence Collection

- [x] 3.1 Reuse `core/ai/soc_tools.py` and `core/ai/soc_tool_executor.py` for every evidence read.
- [x] 3.2 Validate tool names, arguments, actor role, row limits, pagination, redaction, and read-only labels before execution.
- [x] 3.3 Persist each planned, executed, skipped, failed, and truncated tool call as a durable run step with sanitized inputs, evidence references, timing, status, and error metadata.
- [x] 3.4 Reject unsupported, mutation-like, or over-budget tool calls before execution.

## 4. AI Gateway Synthesis

- [x] 4.1 Build bounded sanitized synthesis prompts from collected evidence references and summaries.
- [x] 4.2 Call the existing AI Gateway only for structured briefing synthesis and never expose tool dispatch, database handles, shell/file access, or approval callbacks to the provider.
- [x] 4.3 Block automatic paid fallback for scheduled autonomous work unless an explicit future policy allows it.
- [x] 4.4 Parse and validate provider output against the structured briefing schema, failing or partially completing clearly on malformed output.

## 5. Briefing Persistence and Audit

- [x] 5.1 Persist structured sections in `soc_briefings`: `alerts_reviewed`, `dismissed_low_priority_findings`, `escalations`, `critical_findings`, `evidence`, and `recommendations`.
- [x] 5.2 Persist partial briefing content when evidence exists but synthesis is degraded or incomplete.
- [x] 5.3 Audit scheduled investigation planning, tool calls, AI synthesis, skipped work, outcomes, timing, errors, sanitized inputs, evidence references, and concise decision summaries.
- [x] 5.4 Abort safely on required run, step, briefing, or audit persistence failure; do not silently continue.

## 6. Safety Boundaries

- [x] 6.1 Prove no model-generated SQL, direct model database access, provider-side tool execution, prompt-to-action execution, SOAR execution, approval decision, incident/note mutation, Slack delivery, shell/file/subprocess/eval/exec, commit, push, deployment, or automatic paid-provider spending path exists.
- [x] 6.2 Keep the scheduled service actor `scheduled_soc_briefing_worker` attributed in run, step, briefing, and audit metadata.
- [x] 6.3 Ensure hidden chain-of-thought and raw secret-bearing prompts are not stored.

## 7. Verification

- [x] 7.1 Add focused tests for lifecycle wiring from claimed job to investigation engine without creating schedules/jobs.
- [x] 7.2 Add tests for deterministic planning, candidate bounds, deduplication suppression, and new-evidence reinvestigation.
- [x] 7.3 Add tests for SOC read-tool allowlisting, role validation, pagination/row limits, truncation, and mutation-like tool rejection.
- [x] 7.4 Add tests for runtime/tool/evidence/token/cost budget exhaustion and partial outcomes.
- [x] 7.5 Add tests for AI Gateway disabled, invalid config, local provider unavailable, provider timeout, paid fallback blocked, malformed provider output, and successful structured synthesis.
- [x] 7.6 Add tests for durable run-step persistence, audit records, briefing persistence, persistence-failure abort behavior, and run-state isolation.
- [x] 7.7 Run focused py_compile, backend tests, migration/schema tests if a migration is added, `git diff --check`, and `openspec validate read-only-autonomous-soc-investigations --strict`.

## 8. Documentation

- [x] 8.1 Update scheduled briefing runtime documentation with the new investigation-engine phase and its degraded states.
- [x] 8.2 Update AI architecture documentation for scheduled read-only gateway synthesis and no provider-side tools.
- [x] 8.3 Update the verification checklist and VM handoff/runbook notes for implementation and deployment ownership.
