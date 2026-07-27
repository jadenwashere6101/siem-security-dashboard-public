## Context

`scheduled-soc-briefing-runtime` created durable schedules, windows, jobs, runs, run steps, briefing lifecycle rows, and worker health. `read-only-autonomous-soc-investigations` added bounded evidence collection and structured briefing content in `soc_briefings`. The remaining gap is analyst access and optional delivery: analysts need to browse, filter, read, and trust saved briefings, while Slack summaries remain a best-effort notification layer.

This change should not alter the scheduler, job leases, investigation planning, evidence collection, or model/provider behavior. It exposes and delivers already-persisted briefing content.

## Goals / Non-Goals

**Goals:**

- Provide durable briefing history list and detail APIs.
- Add analyst UI for briefing history, lifecycle/status visibility, structured content, evidence references, search, filters, and pagination.
- Track optional Slack summary delivery state, attempts, retries, errors, idempotency, and audit records.
- Enforce RBAC consistently: analysts and super admins can read briefings; delivery controls follow existing notification/admin policy boundaries.
- Sanitize Slack summaries so external delivery contains concise status, top findings, and a SIEM direction/link, not raw sensitive evidence.
- Keep saved briefing persistence independent from Slack delivery.
- Define retention behavior and degraded/offline/provider-unavailable display semantics.

**Non-Goals:**

- Teams delivery, investigation changes, scheduler/worker lease changes, Mini PC/Ollama setup, model selection, production mutations, SOAR execution, approval decisions, draft generation, direct provider-side tools, or new AI prompts.

## Decisions

1. Use `soc_briefings` as the history source of truth.

List/detail APIs read from `soc_briefings` joined to `soc_briefing_runs`, `soc_briefing_schedules`, and `soc_briefing_schedule_windows`. Run steps are exposed only through bounded detail sections or a separate diagnostic field so detail responses remain predictable. This avoids duplicating briefing content in another history table.

Alternative: create a separate history table. Rejected because `soc_briefings` already has lifecycle, content, summary, sections, evidence references, schedule, window, and run links.

2. Add a narrow delivery ledger if existing notification delivery rows cannot represent briefing delivery idempotently.

Delivery needs a durable key such as `briefing_id + channel + summary_fingerprint`, lifecycle status, attempt count, next retry time, last error, and provider metadata. If `notification_delivery_attempts` can safely support briefing IDs and idempotency, extend it additively; otherwise create `soc_briefing_delivery_attempts`. Either path must preserve existing alert/incident notification semantics.

3. Keep Slack delivery asynchronous or worker-owned, never request-thread critical.

Briefing generation and saved history are already durable. Slack summary delivery may run as a bounded post-briefing worker phase or a separate bounded delivery helper invoked by the existing worker/timer. API reads must not send Slack. Manual retry controls may enqueue or mark delivery for retry, but they must not mutate briefing content.

4. Use idempotency and backoff for delivery.

Each delivery attempt uses a deterministic idempotency key. Duplicate worker invocations reuse the existing delivery record or record duplicate-suppressed status. Retry uses bounded exponential backoff with maximum attempts; exhausted delivery becomes `failed` while the briefing remains `success` or `partial` according to content state.

5. UI is a SIEM operational workspace, not a landing page.

The first screen should be the actual briefing history: dense list/table, filters, status facets, search, pagination, and a detail pane/page. Detail view presents sections consistently, distinguishes saved content status from delivery status, and makes degraded states explicit.

6. Slack summaries are sanitized and concise.

Slack payloads include briefing type, generated time/window, content status, at most a few high-level findings/recommendations, and a SIEM link or direction. They must not include raw tool output, secrets, hidden chain-of-thought, unbounded evidence rows, or sensitive internal details beyond the configured notification policy.

7. Retention is explicit but destructive cleanup is not automatic unless already supported.

The UI/API should report retention expectations. Implementation may add retention configuration and indexes, but automatic deletion requires careful ownership and can be deferred unless an existing cleanup pattern supports it safely. Historical briefing/audit evidence should remain at least 180 days by default.

## Risks / Trade-offs

- [Delivery table choice] Reusing `notification_delivery_attempts` may require additive columns; a new table adds another history surface. Mitigation: choose the smallest schema that preserves idempotency and existing notification semantics.
- [Slack failure confusion] Analysts may conflate delivery failure with briefing failure. Mitigation: separate content lifecycle badges from delivery status in API and UI.
- [Sensitive external content] Briefing sections may contain internal evidence references. Mitigation: build Slack summaries from sanitized allowlisted fields, not raw sections.
- [UI scope creep] A rich workspace could grow into schedule management. Mitigation: this phase is history/detail/delivery status only; schedule editing remains out of scope.

## Migration Plan

Mac AI implementation adds any required additive delivery tracking columns/table/indexes, backend routes/services, frontend workspace components, tests, and docs. VM AI later applies the approved commit and migrations through the documented deployment workflow only after explicit commit/push/deploy authorization.

Rollback disables the UI route/nav entry and Slack delivery trigger while preserving briefing and delivery rows for audit history. Additive delivery records remain in place unless a separate approved rollback migration exists.

## Open Questions

- Exact Slack link format depends on the deployed frontend route shape and base URL configuration.
- Whether to extend `notification_delivery_attempts` or add `soc_briefing_delivery_attempts` should be settled during implementation by inspecting the current notification schema and tests narrowly.
