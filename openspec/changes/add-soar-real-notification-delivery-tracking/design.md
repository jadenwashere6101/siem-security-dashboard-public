# Design: SOAR Real Notification Delivery Tracking

## Design boundary
This change designs delivery tracking only. It does not implement persistence, change schema, add frontend code, send notifications, create retries, add daemons, redesign queues, or modify ingest/detection/correlation.

The tracking model should apply to:
- current simulation notification attempts.
- future staging-controlled real Slack notification attempts.
- future staging-controlled real Teams notification attempts.

It should not enable:
- real firewall actions.
- real email delivery.
- real generic webhook delivery.
- PagerDuty delivery.
- autonomous retry/replay behavior.
- external delivery guarantees beyond what provider response metadata can safely indicate.

## Core model
Add an immutable delivery-attempt ledger in a future implementation. Each outbound notification attempt should create one append-only record. Records should never be updated to rewrite history; if later state is needed, append a new event or record a linked follow-up attempt.

The delivery ledger is different from playbook execution state:
- playbook execution state answers whether the step runner completed its work.
- delivery attempt state answers what the notification adapter attempted and what the provider/simulation result was.
- a playbook step can succeed while a delivery is simulated, fail while no network call occurred, or be ambiguous after a timeout.

The ledger must make this distinction explicit so operators do not confuse "step executed" with "provider definitely delivered a message".

## Suggested schema direction
Future implementation should use an additive table such as `notification_delivery_attempts`.

Suggested columns:

```text
id SERIAL PRIMARY KEY
delivery_correlation_id VARCHAR(128) NOT NULL
idempotency_key VARCHAR(128) NOT NULL
provider VARCHAR(32) NOT NULL
action VARCHAR(64) NOT NULL
mode VARCHAR(20) NOT NULL
status VARCHAR(32) NOT NULL
execution_id INTEGER REFERENCES playbook_executions(id)
playbook_id VARCHAR(64)
step_index INTEGER
incident_id INTEGER REFERENCES incidents(id)
alert_id INTEGER REFERENCES alerts(id)
approval_request_id INTEGER REFERENCES approval_requests(id)
requested_by_user_id INTEGER REFERENCES users(id)
attempt_number INTEGER NOT NULL DEFAULT 1
dedupe_group_key VARCHAR(128)
retry_of_delivery_attempt_id INTEGER REFERENCES notification_delivery_attempts(id)
requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
started_at TIMESTAMPTZ
completed_at TIMESTAMPTZ
duration_ms INTEGER
timeout_seconds INTEGER
timed_out BOOLEAN NOT NULL DEFAULT FALSE
success BOOLEAN NOT NULL DEFAULT FALSE
simulated BOOLEAN NOT NULL DEFAULT TRUE
executed BOOLEAN NOT NULL DEFAULT FALSE
failure_classification VARCHAR(64)
retry_eligible BOOLEAN NOT NULL DEFAULT FALSE
retry_after_seconds INTEGER
circuit_state VARCHAR(20)
circuit_blocked BOOLEAN NOT NULL DEFAULT FALSE
provider_status_code INTEGER
provider_message_id_hash VARCHAR(128)
payload_fingerprint VARCHAR(128)
safe_summary TEXT
metadata JSONB NOT NULL DEFAULT '{}'
created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
```

Recommended constraints and indexes:
- Unique index on `idempotency_key` for completed or active attempts where safe.
- Index on `(provider, mode, status, created_at)`.
- Index on `(execution_id, step_index)`.
- Index on `incident_id`.
- Index on `approval_request_id`.
- Index on `delivery_correlation_id`.
- Index on `dedupe_group_key`.

The schema should be additive only. Do not store secrets, webhook URLs, request headers, request bodies, response bodies, authorization values, cookies, tokens, or raw provider metadata.

## Status model
Use a provider-independent status set:
- `planned`: record reserved before adapter dispatch, if implementation needs pre-dispatch visibility.
- `skipped`: no dispatch attempted because guardrails, circuit breaker, approval state, or config blocked it.
- `sent_simulated`: simulation completed successfully.
- `sent_real`: real provider accepted the request according to safe response metadata.
- `failed`: provider or adapter returned a known failure.
- `timed_out`: request exceeded timeout and delivery is unknown.
- `ambiguous`: outcome cannot be proven, such as connection interruption after request dispatch.
- `circuit_blocked`: circuit breaker prevented dispatch before network.
- `config_blocked`: missing or unsafe config prevented dispatch.

Do not use provider response alone to imply human-visible delivery. A `sent_real` status means the provider accepted the request or returned a safe success signal; it does not guarantee a human saw the notification.

## Simulation vs real labeling
Each attempt must carry:
- `mode`: effective adapter mode such as `simulation` or `real`.
- `simulated`: boolean.
- `executed`: boolean indicating whether the adapter attempted the meaningful action.
- `provider`: `slack`, `teams`, or future provider names.
- `real_guardrails`: safe metadata under `metadata`, such as staging allowed/configured booleans, never secret values.

Simulation attempts should be recorded with the same linkage and idempotency metadata as real attempts. This lets operators validate history, metrics, dedupe, and UI behavior before real delivery is routine.

## Outbound correlation identifiers
Every delivery attempt should have a stable `delivery_correlation_id` generated before dispatch. It should be safe to show in logs, delivery history, `steps_log`, audit records, and support evidence.

The correlation id should:
- not contain secrets.
- not derive directly from webhook URLs.
- include or derive from safe internal context such as provider, execution id, step index, and a random/UUID suffix.
- appear in adapter result metadata and delivery history.
- be included in provider payload only if it is safe and useful for operator troubleshooting.

Use a separate `idempotency_key` for duplicate detection. Do not rely on correlation id alone for idempotency because retries and follow-up attempts may need distinct correlation IDs while still belonging to the same dedupe group.

## Dedupe and idempotency metadata
Delivery tracking should make duplicate sends detectable, not silently hidden.

Suggested metadata:
- `idempotency_key`: deterministic key for the same provider, action, execution id, step index, destination label, and payload fingerprint.
- `dedupe_group_key`: groups attempts for the same logical notification across retries or manual follow-up.
- `attempt_number`: visible sequence within the dedupe group.
- `retry_of_delivery_attempt_id`: links a manual retry/follow-up to the original attempt.
- `payload_fingerprint`: hash of a sanitized payload representation, not the raw payload.

If a duplicate is detected before dispatch, append a `skipped` or `duplicate_blocked` style record rather than deleting or rewriting the first attempt. Operators should see that duplicate prevention occurred.

## Linkage requirements
Delivery attempts should link to the strongest available internal context:
- `playbook_execution_id`.
- `playbook_id`.
- `playbook_step_index`.
- `incident_id`.
- `alert_id`.
- `approval_request_id` when the delivery is approval-related.
- `requested_by_user_id` for manual operator-triggered paths.
- delivery correlation id in `steps_log` adapter output.
- safe audit event id if audit linkage is implemented.

Missing context should not block recording. A delivery attempt with partial linkage is better than no record, but `metadata.linkage_partial: true` should make the gap visible.

## Delivery timestamps
Record timestamps independently:
- `requested_at`: internal request to attempt delivery was created.
- `started_at`: adapter dispatch started.
- `completed_at`: provider/simulation result became known.
- `duration_ms`: bounded elapsed time.
- `timeout_seconds`: configured timeout for that attempt.

For circuit-blocked, config-blocked, or approval-blocked paths, `started_at` may be null and `completed_at` should reflect when the blocked outcome was recorded.

## Timeout and failure metadata
Failure metadata should be structured and provider-neutral:
- `failure_classification`: `timeout`, `provider_4xx`, `provider_5xx`, `rate_limited`, `network_error`, `invalid_config`, `circuit_open`, `payload_rejected`, `duplicate_blocked`, `unknown`, or similar.
- `retry_eligible`: advisory boolean only.
- `retry_after_seconds`: safe provider hint or internal cooldown, if available.
- `provider_status_code`: numeric code only when safe.
- `provider_error_code`: short allowlisted code only when safe.
- `safe_summary`: short sanitized operator-facing text.

Never store raw exception strings if they can contain URLs, headers, tokens, request bodies, or provider response bodies. Sanitize before persistence.

## Partial delivery failure handling
Partial or ambiguous delivery must be first-class:
- If the request times out before a provider response, status should be `timed_out` or `ambiguous`, not success.
- If connection drops after request dispatch, status should be `ambiguous`.
- If provider returns a success code but no provider message id, status may be `sent_real` with `provider_acknowledgement: accepted_without_id`.
- If provider returns a rate limit, status should be `failed` with `failure_classification: rate_limited` and safe retry metadata.
- If circuit breaker blocks dispatch, status should be `circuit_blocked` and `executed: false`.

Do not automatically retry partial failures. Operators should see ambiguity and decide whether a manual retry is acceptable.

## Circuit-breaker interaction
Delivery tracking should record circuit breaker state before dispatch:
- `circuit_state`: `closed`, `open`, `half_open`, `unknown`, or `invalid`.
- `circuit_blocked`: true when the breaker prevented dispatch.
- `circuit_failure_count`: safe integer in metadata if available.
- `circuit_cooldown_until`: safe timestamp in metadata if available.

When breaker is open, unknown, invalid, or otherwise unsafe, append a blocked delivery record and do not call the provider.

Half-open probe behavior must remain explicit/manual and bounded. A half-open attempt should be easy to distinguish in delivery history so operators can see it was a probe-like delivery and not ordinary steady-state traffic.

## Retry visibility metadata
Retry metadata is visibility only:
- `retry_eligible` explains whether a manual retry might be reasonable.
- `retry_after_seconds` provides a safe advisory delay.
- `max_adapter_attempts` or `remaining_attempts` may be stored in metadata.
- `retry_of_delivery_attempt_id` links manual follow-up attempts.

This design must not create autonomous retries, queue replay, scheduled recovery, hidden loops, or a replay engine. Retry remains explicit/manual and governed by existing playbook controls and future approved designs.

## Safe audit linkage
Delivery records should be linkable from audit events without duplicating sensitive content.

Suggested audit behavior:
- Audit event says a notification delivery attempt was recorded.
- Audit metadata includes delivery attempt id, provider, mode, status, execution id, incident id, approval id, and safe failure classification.
- Audit metadata does not include webhook URLs, request headers, payload bodies, response bodies, tokens, or raw provider metadata.

Delivery history should be the detailed immutable ledger. Audit should point to it and summarize safe facts.

## Operator-visible delivery history
Operators need read-only delivery history before real notifications become routine.

Suggested read APIs:
- `GET /notifications/deliveries`: list with filters for provider, mode, status, time range, incident id, approval id, playbook execution id, dedupe group, and correlation id.
- `GET /notifications/deliveries/<id>`: detail for one delivery attempt with safe metadata.
- `GET /playbook-executions/<id>/deliveries`: deliveries for a playbook execution.
- `GET /incidents/<id>/deliveries`: deliveries related to an incident.
- `GET /approvals/<id>/deliveries`: deliveries related to an approval request.
- `GET /metrics/notifications`: aggregate delivery visibility metrics.

All APIs should be authenticated, read-only, and available to analyst/super_admin roles following current visibility patterns. Viewer access should follow existing security decisions and default to denied if unclear.

No read API should mutate stale state, trigger retries, test connections, probe providers, or call adapters.

## Suggested UI visibility areas
Future frontend work should show delivery history in existing operational views:
- `PlaybooksPanel`: delivery attempts for selected execution/step.
- `IncidentsPanel`: notification delivery history in incident detail/timeline.
- `ApprovalsPanel`: approval-related notification attempts.
- `IntegrationStatusPanel`: recent provider delivery status summaries and circuit-blocked counts.
- `PlaybookMetricsPanel` or a new notification metrics panel: aggregate delivery health.

UI should be read-only for this phase. Do not add send, retry, replay, test-connection, or run-now controls as part of delivery history visibility.

## Visibility-oriented metrics
Suggested metrics:
- total delivery attempts by provider.
- attempts by mode: simulation vs real.
- attempts by status.
- success/failure/timeout/ambiguous counts.
- circuit-blocked counts.
- duplicate-blocked counts.
- retry-eligible counts.
- manual retry/follow-up counts via `retry_of_delivery_attempt_id`.
- provider outage classification counts.
- recent 24-hour delivery activity.
- delivery attempts linked to approvals.
- delivery attempts linked to incidents.

Metrics must be read-only and must not probe providers or alter circuit breaker state.

## Retention expectations
Delivery history should be retained long enough for operational review, smoke-test evidence, incident reconstruction, and audit correlation.

Suggested policy:
- Keep recent detailed delivery attempts online for a configurable window such as 90 days.
- Keep aggregate metrics longer where useful.
- Archive older detailed records into a safe archive table or external archival process only after a separate approved design.
- Never archive secrets because secrets should never be stored.
- Preserve immutable history semantics during archive; do not collapse failures in a way that hides duplicates or ambiguous outcomes.

## Recommended future archive boundaries
Archive should be a separate future change. Boundaries:
- Add archive/read-only migration plan only after delivery tracking is implemented and stable.
- Archive detailed rows by `created_at` age, not by status alone.
- Keep correlation id, provider, mode, status, linkage ids, timestamps, safe failure classification, and idempotency metadata.
- Drop or compact bulky safe metadata only if it does not remove duplicate detection or audit reconstruction value.
- Do not archive by deleting failed or ambiguous attempts earlier than successes.
- Do not introduce background archive jobs until scheduler/daemon policy is separately approved.

## Secret and provider metadata safety
Delivery tracking must never store or return:
- `SLACK_WEBHOOK_URL`.
- `TEAMS_WEBHOOK_URL`.
- future webhook URLs.
- request headers.
- authorization values.
- cookies.
- tokens.
- raw request payloads.
- raw provider response bodies.
- raw exception strings.
- provider URLs or URL path fragments that reveal secrets.

Safe fields:
- provider name.
- action name.
- booleans such as `webhook_configured`.
- numeric status code when safe.
- allowlisted provider error code when safe.
- hashed provider message id if useful.
- sanitized payload fingerprint.
- delivery correlation id.

Redaction must happen before persistence, before audit, before route serialization, and before frontend display.

## Delivery-vs-execution mismatch
The design must explicitly handle mismatch cases:
- Step succeeds but delivery record says `sent_simulated`: simulation was successful, no real provider delivery occurred.
- Step fails before adapter dispatch: delivery may be absent or recorded as `skipped`/`config_blocked`.
- Adapter dispatch happens but DB write fails: this is a high-risk ambiguity; future implementation should write an initial `planned` record before dispatch or otherwise choose a transactional pattern that minimizes lost delivery history.
- Provider accepts but step later fails writing `steps_log`: delivery record remains the immutable source of delivery truth.
- Timeout after dispatch: execution may fail, delivery status remains `timed_out` or `ambiguous`.

Future implementation should prefer creating a safe pre-dispatch record and then appending or finalizing via a linked terminal event if necessary, but without rewriting historical facts.

## Future multi-provider complexity
The schema and APIs should avoid Slack-only or Teams-only assumptions:
- provider is a stable string or constrained enum with migration room.
- provider-specific metadata is nested under `metadata.provider`.
- status and failure classification are provider-neutral.
- idempotency and correlation fields are provider-independent.
- UI labels should come from provider metadata, not hardcoded only for Slack/Teams.

Do not add PagerDuty, email, or generic webhook implementation as part of this design.

## Safety boundaries
- Default remains simulation.
- Real mode remains staging-controlled.
- Delivery history is immutable.
- Failures and ambiguous outcomes remain visible.
- Duplicate sends are detectable.
- Retry remains explicit/manual.
- No autonomous retries.
- No daemon or scheduler behavior.
- No queue redesign.
- No replay engine.
- No real firewall execution.
- No real email, generic webhook, or PagerDuty implementation.
- No frontend implementation in this change.
- No schema changes in this change.
- No actual persistence implementation in this change.
- No ingest, detection, or correlation changes.
- No secrets, webhooks, tokens, headers, raw payloads, raw provider responses, or unsafe metadata in delivery history.

## Risks and stop conditions
- Stop if delivery tracking requires storing webhook URLs, headers, tokens, or raw provider bodies.
- Stop if delivery records can be mutated to hide failures or duplicates.
- Stop if retry metadata creates automatic retries or hidden replay.
- Stop if implementation would call providers from read APIs, metrics APIs, or UI history views.
- Stop if real mode can be enabled outside staging guardrails.
- Stop if Slack and Teams correlation/idempotency fields are provider-specific in a way that blocks future providers.
- Stop if delivery tracking requires queue redesign, daemons, schedulers, or ingest/detection/correlation changes.
- Stop if execution success is presented as guaranteed provider delivery.
