# Tasks: Response Outcome Backend APIs

Status: Complete. All tasks are checked and this child change completes the delegated Phase 6 backend API contract work for parent roadmap `clarify-soar-response-outcomes`.

## 1. Planning and Route Confirmation

- [x] 1.1 Confirm this child change references parent roadmap `openspec/changes/clarify-soar-response-outcomes` and implements only remaining Phase 6 backend API contract work after alert APIs.
- [x] 1.2 Confirm alert list/detail response_outcome work is already complete and is not reimplemented in this child change.
- [x] 1.3 Inspect backend route decorators and record any missing route from the requested scope as skipped/deferred rather than creating a new endpoint.
- [x] 1.4 Confirm no migrations are required.
- [x] 1.5 Confirm no frontend work is required.

## 2. Shared Backend API Helpers

- [x] 2.1 Reuse `core/soar_response_outcomes.py` helpers for canonical serialization and latest-outcome reads.
- [x] 2.2 Add narrowly scoped bulk helper(s) only where needed to avoid N+1 queries for list endpoints.
- [x] 2.3 Ensure `response_outcome` keys are always present on updated entity payloads and set to `null` when canonical outcomes do not exist.
- [x] 2.4 Preserve all existing legacy fields and response shapes.

## 3. Route Updates

- [x] 3.1 Response log API: identify the existing response log route or embedded payload; add canonical outcome linkage where a route exists, or document as deferred if no route exists.
- [x] 3.2 SOAR queue API in `routes/admin_routes.py`: update `/admin/soar/queue/status`, `/admin/soar/queue/recent`, and `/admin/soar/queue/<queue_id>` additively.
- [x] 3.3 Playbook execution API in `routes/playbook_routes.py`: update `/playbook-executions` and `/playbook-executions/<execution_id>` with execution-level and detail timeline/step outcome payloads.
- [x] 3.4 Approval API in `routes/approval_routes.py`: update `/approvals`, `/approvals/<approval_id>`, and `/approvals/<approval_id>/decision` additively.
- [x] 3.5 Notification delivery API in `routes/notification_delivery_routes.py`: update `/notification-deliveries` and `/notification-deliveries/<attempt_id>` additively.
- [x] 3.6 Incident API in `routes/incident_routes.py`: update `/incidents`, `/incidents/<incident_id>`, and `/incidents/<incident_id>/timeline` additively.
- [x] 3.7 Source-IP context API in `routes/source_ip_context_routes.py`: add recent canonical outcomes and grouped outcome counts to `/source-ip-context`.
- [x] 3.8 Attack Map/source-IP popup backend route: no dedicated backend route exists; popup data is derived from existing alert/event/source-IP context APIs, so this item is skipped/deferred without creating a new endpoint.
- [x] 3.9 Blocklist API in `routes/blocklist_routes.py`: update `/blocked-ips` and related returned blocklist payloads with tracking-only provenance or `response_outcome`.
- [x] 3.10 Metrics/SOC aggregation in `routes/metrics_routes.py`: update `/metrics/playbooks`, `/metrics/notifications`, `/metrics/incidents`, and `/metrics/approvals` with canonical outcome count fields; do not add a new SOC route.

## 4. Contract Tests

- [x] 4.1 Add/extend response log API contract tests if an existing route is found; otherwise add documentation-only confirmation in implementation notes.
- [x] 4.2 Add/extend SOAR queue API contract tests.
- [x] 4.3 Add/extend playbook execution API contract tests.
- [x] 4.4 Add/extend approval API contract tests.
- [x] 4.5 Add/extend notification delivery API contract tests.
- [x] 4.6 Add/extend incident list/detail/timeline API contract tests.
- [x] 4.7 Add/extend source-IP context API contract tests.
- [x] 4.8 Add/extend Attack Map/source-IP popup backend API contract tests only if a dedicated route exists; skipped because no dedicated backend route exists.
- [x] 4.9 Add/extend blocklist API contract tests.
- [x] 4.10 Add/extend metrics route contract tests for canonical outcome aggregation fields.
- [x] 4.11 Add regression coverage that updated read routes do not mutate state or call worker/adapter execution paths.

## 5. Verification

- [x] 5.1 Run targeted route/API contract tests for every updated endpoint.
- [x] 5.2 Run targeted tests for `core/soar_response_outcomes.py` helper additions if any.
- [x] 5.3 Run OpenSpec validation for `add-response-outcome-backend-apis`.
- [x] 5.4 Run `git diff --check`.
- [x] 5.5 Confirm no frontend files, migrations, runtime behavior beyond read serialization, or unrelated parent roadmap files were changed.
