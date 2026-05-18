# SOAR Security and Safety Boundaries

Last updated: 2026-05-18

This document explains the safety boundaries that make the project suitable for
public demos and portfolio review.

## Default Runtime Boundary

The platform is simulation-safe by default. A normal demo must not trigger real
Slack, Teams, email, webhook, or firewall actions.

Real outbound execution is intentionally hard to enable. It requires a real
mode setting, an approved environment, an adapter-specific enable flag, and
required credential env vars. Missing any guard fails closed.

## Real-Mode Guard Model

Real adapter execution requires:

- `INTEGRATION_MODE=real`
- `SOAR_ENV=staging` or another approved safe value documented for that adapter
- `SOAR_REAL_<ADAPTER>_ENABLED=true`
- Required credential env vars present and non-empty

Logs and audit events may include env var names and safe status metadata. They
must not include credential values.

## Firewall Boundary

Firewall execution remains simulation/dry-run only for this spec lineage. There
is no promotion path to real firewall changes in the current productization
scope. Any real firewall execution requires a separate future approved OpenSpec
and staging runbook.

## Audit and Redaction

Safe audit metadata can include adapter name, action name, mode, result status,
failure class/code, execution id, incident id, alert id, and safe correlation or
idempotency keys.

Never log or expose:

- webhook URLs
- tokens
- SMTP passwords
- auth headers
- raw notification payloads
- private environment values

## Flood Protection and Deduplication

Notification delivery uses rate limiting and idempotency/deduplication guards
to avoid uncontrolled outbound sends. Rate-limited delivery is recorded as a
safe blocked/skipped outcome rather than attempting a send. Duplicate successful
or in-flight deliveries are skipped instead of sent again.

## Dead Letters and Retryability

Dead letters classify retryability centrally. Known transient classes can be
retryable; unknown classes fail closed as non-retryable. This prevents the UI
from promoting unsafe retries for ambiguous failures.

## Approvals and Human Gates

Approval-paused playbooks are deliberate human gates. Stale recovery must not
treat approval waits as failed worker leases. Demo users should explain these
states as safety controls, not as stalled automation.

## Demo Stop Conditions

Stop the session and capture evidence if any of the following occurs:

- a real outbound adapter appears to run during a general demo
- a firewall action appears to move beyond dry-run/simulation
- secrets or raw payloads appear in UI, logs, screenshots, or audit output
- duplicate notification attempts appear for the same idempotency context
- stale recovery moves an approval-paused execution

