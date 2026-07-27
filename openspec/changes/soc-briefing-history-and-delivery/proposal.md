## Why

The runtime and investigation engine can now persist structured advisory SOC briefings, but analysts still need a durable, searchable SIEM experience to review briefing history and understand delivery status. This final software phase makes saved briefings visible and optionally deliverable without making Slack a dependency for briefing success.

## What Changes

- Add analyst-facing briefing history APIs for listing, filtering, paginating, and reading saved SOC briefings with linked run, schedule, window, evidence, and lifecycle status.
- Add a frontend briefing history workspace or panel that presents structured sections such as alerts reviewed, dismissed/low-priority findings, escalations, critical findings, evidence, and recommendations.
- Add delivery tracking for optional Slack summary notifications, including duplicate delivery prevention, lifecycle states, retry/backoff metadata, failure details, and audit records.
- Enforce RBAC for briefing history and delivery controls while keeping the analyst experience read-only with respect to SOC entities and production actions.
- Sanitize externally delivered Slack summaries and include a link or direction to the full SIEM briefing instead of sending raw evidence.
- Define retention expectations for briefing history, run steps, evidence references, and delivery records.
- Preserve the core invariant: saved briefing persistence succeeds or fails independently from Slack delivery. Slack failure must not lose, invalidate, or block a saved briefing.

Out of scope: Microsoft Teams delivery, new investigation logic, new scheduling logic, production mutations, SOAR execution, model/provider setup, draft generation, approval decisions, and any direct provider/tool execution changes.

## Capabilities

### New Capabilities

- `soc-briefing-history-and-delivery`: Durable briefing history APIs, analyst UI, structured briefing presentation, search/filter/pagination, optional Slack summary delivery, delivery status/retry tracking, RBAC, audit logging, sanitization, and retention behavior.

### Modified Capabilities

- None.

## Impact

- Expected backend areas: new or extended briefing store/service modules, Flask routes for briefing list/detail/delivery status, RBAC decorators, audit helpers, notification/Slack policy integration, and focused API tests.
- Expected frontend areas: SIEM navigation/workspace integration, briefing history list, filters/search/pagination controls, briefing detail presentation, delivery status indicators, and focused component/service tests.
- Expected persistence impact: reuse existing `soc_briefings`, `soc_briefing_runs`, `soc_briefing_run_steps`, schedules, windows, and audit tables; add only narrow delivery tracking tables or indexes if existing notification delivery records cannot model briefing delivery idempotently.
- Expected docs: scheduled briefing runtime docs, Slack/notification runbook notes, verification checklist, and VM handoff documentation.
