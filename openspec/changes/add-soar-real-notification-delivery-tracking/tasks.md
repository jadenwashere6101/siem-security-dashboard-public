# Tasks: SOAR Real Notification Delivery Tracking

## Design review
- [ ] Confirm this change is design/spec only.
- [ ] Confirm no schema changes are made in this change.
- [ ] Confirm no delivery persistence implementation is added in this change.
- [ ] Confirm default integration mode remains simulation.
- [ ] Confirm real Slack and Teams remain staging-controlled by existing readiness guardrails.
- [ ] Confirm firewall, email, generic webhook, PagerDuty, blocklist, and remediation paths remain out of scope.
- [ ] Confirm ingest, detection, and correlation remain untouched.

## Future implementation planning
- [ ] Inspect current adapter result shape for Slack and Teams.
- [ ] Inspect `steps_log` adapter output and playbook execution detail APIs.
- [ ] Inspect existing audit log helper patterns.
- [ ] Inspect integration circuit breaker metadata shape.
- [ ] Inspect playbook execution reliability metadata and manual retry controls.
- [ ] Decide the additive schema for immutable `notification_delivery_attempts` or equivalent.
- [ ] Decide whether to reserve a pre-dispatch record before provider calls to reduce delivery-vs-execution mismatch.
- [ ] Define provider-neutral status and failure classification enums.
- [ ] Define correlation id generation that never derives from provider secrets.
- [ ] Define idempotency and dedupe group key generation.
- [ ] Define safe payload fingerprinting without storing raw payloads.
- [ ] Define redaction before persistence, audit, API serialization, and UI rendering.
- [ ] Define linkage to playbook executions, step indexes, alerts, incidents, and approval requests.
- [ ] Define retention and future archive boundaries.

## Suggested future schema tasks
- [ ] Add an additive immutable delivery attempt table.
- [ ] Add indexes for provider/mode/status/time-window queries.
- [ ] Add indexes for playbook execution, incident, approval, correlation id, and dedupe group lookups.
- [ ] Add a uniqueness strategy for idempotency keys that detects duplicates without hiding history.
- [ ] Add safe JSON metadata for provider-neutral and provider-specific safe fields.
- [ ] Ensure schema cannot require webhook URLs, tokens, headers, raw payloads, or raw provider responses.
- [ ] Ensure failed, timed-out, ambiguous, duplicate-blocked, and circuit-blocked attempts are retained.

## Suggested future backend behavior
- [ ] Record immutable simulation delivery attempts for Slack and Teams notification steps.
- [ ] Record future real delivery attempts for Slack and Teams only behind staging guardrails.
- [ ] Label every attempt with `mode`, `simulated`, `executed`, provider, action, and status.
- [ ] Record requested, started, completed, duration, and timeout metadata.
- [ ] Record safe timeout/failure classifications.
- [ ] Record circuit breaker state before dispatch.
- [ ] Record circuit-blocked attempts without provider calls.
- [ ] Record config-blocked attempts without provider calls.
- [ ] Record duplicate-blocked attempts without deleting prior attempts.
- [ ] Record retry visibility metadata without starting retries.
- [ ] Link manual follow-up attempts through `retry_of_delivery_attempt_id`.
- [ ] Keep read APIs and metrics strictly read-only.
- [ ] Ensure provider read/status/history APIs never call adapter `execute()`.

## Suggested read APIs
- [ ] Design `GET /notifications/deliveries` with filters for provider, mode, status, time range, incident id, approval id, execution id, dedupe group, and correlation id.
- [ ] Design `GET /notifications/deliveries/<id>` for one immutable delivery attempt.
- [ ] Design `GET /playbook-executions/<id>/deliveries`.
- [ ] Design `GET /incidents/<id>/deliveries`.
- [ ] Design `GET /approvals/<id>/deliveries`.
- [ ] Design `GET /metrics/notifications`.
- [ ] Confirm all read APIs are authenticated and role-aligned with analyst/super_admin visibility.
- [ ] Confirm read APIs do not mutate stale state, trigger retries, probe providers, or call adapters.

## Suggested UI visibility areas
- [ ] Show delivery attempts in `PlaybooksPanel` execution detail.
- [ ] Show notification delivery history in `IncidentsPanel` detail/timeline.
- [ ] Show approval-related delivery attempts in `ApprovalsPanel`.
- [ ] Show recent provider delivery summaries in `IntegrationStatusPanel`.
- [ ] Show aggregate notification delivery metrics in `PlaybookMetricsPanel` or a future notification metrics panel.
- [ ] Keep all UI visibility read-only for this phase.
- [ ] Do not add send, retry, replay, test-connection, run-now, daemon, or scheduler controls.

## Metrics planning
- [ ] Count delivery attempts by provider.
- [ ] Count delivery attempts by simulation vs real mode.
- [ ] Count delivery attempts by status.
- [ ] Count success, failure, timeout, and ambiguous outcomes.
- [ ] Count circuit-blocked attempts.
- [ ] Count duplicate-blocked attempts.
- [ ] Count retry-eligible attempts.
- [ ] Count manual follow-up attempts.
- [ ] Count provider outage classifications.
- [ ] Count delivery attempts linked to incidents and approvals.
- [ ] Confirm metrics are read-only and do not probe providers or update circuit state.

## Safety test requirements for future implementation
- [ ] Test delivery records are immutable and append-only.
- [ ] Test simulation attempts are recorded without network calls.
- [ ] Test real Slack/Teams attempts require staging guardrails and mocked network in automated tests.
- [ ] Test webhook URLs, headers, tokens, raw payloads, raw provider responses, and unsafe exception strings are never persisted or returned.
- [ ] Test duplicate logical sends are detectable through idempotency/dedupe metadata.
- [ ] Test duplicate-blocked attempts remain visible.
- [ ] Test timeout and ambiguous outcomes remain visible.
- [ ] Test circuit-open/unknown/invalid state records blocked attempts and does not call providers.
- [ ] Test retry metadata does not create autonomous retries.
- [ ] Test read APIs never call providers.
- [ ] Test metrics APIs never call providers.
- [ ] Test delivery records link to playbook executions, incidents, alerts, and approvals where available.
- [ ] Test partial linkage is visible when full linkage is unavailable.
- [ ] Test no queue redesign, daemon, scheduler, replay engine, ingest, detection, or correlation behavior changes occur.

## Stop conditions
- [ ] Stop if implementation requires autonomous retries.
- [ ] Stop if implementation requires daemon or scheduler behavior.
- [ ] Stop if implementation requires queue redesign or a replay engine.
- [ ] Stop if implementation requires real firewall execution.
- [ ] Stop if implementation adds PagerDuty, email, or generic webhook delivery.
- [ ] Stop if implementation requires frontend changes in the persistence slice.
- [ ] Stop if implementation calls providers from read APIs or metrics.
- [ ] Stop if secrets, webhooks, tokens, headers, raw payloads, raw provider responses, or unsafe exception strings must be stored.
- [ ] Stop if failed or ambiguous deliveries can be hidden or overwritten.
- [ ] Stop if ingest, detection, or correlation changes are needed.

## Future archive planning
- [ ] Keep archive behavior out of the first delivery tracking implementation unless separately approved.
- [ ] Define archive by age/time window, not by success/failure status alone.
- [ ] Preserve correlation id, provider, mode, status, linkage ids, timestamps, failure classification, idempotency key, and dedupe group.
- [ ] Preserve failed, timed-out, ambiguous, duplicate-blocked, and circuit-blocked history.
- [ ] Avoid background archive jobs until daemon/scheduler policy is separately approved.
