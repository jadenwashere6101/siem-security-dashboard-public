## 1. Notification Policy Architecture

- [x] 1.1 Audit every current Slack notification entrypoint from alert/incident creation through Slack delivery and document the single policy-evaluation insertion point.
- [x] 1.2 Define the backend notification-policy module contract, including policy inputs, outcomes, and fail-closed result states.
- [x] 1.3 Confirm the canonical source values and severity vocabulary that policy evaluation is allowed to consume.
- [x] 1.4 Confirm policy outcomes distinguish disabled, below-minimum-severity, unrouted-source, delivered-attempted, and policy-unavailable states without faking success.

## 2. Runtime Notification Configuration

- [x] 2.1 Audit reusable backend runtime configuration storage and API patterns, including `detection_config` and pfSense ingest filter controls.
- [x] 2.2 Decide whether existing durable notification-control storage can be reused or whether a small additive notification-policy store is required.
- [x] 2.3 Define validation rules and defaults for Slack enabled, minimum severity, notify-on-alerts, notify-on-incidents, Slack format, and per-source channel labels.
- [x] 2.4 Define RBAC, audit logging, and safe read/write API behavior for notification policy updates.

## 3. Source-Based Slack Routing

- [x] 3.1 Define the routing helper contract that maps existing alert source values to bounded source keys.
- [x] 3.2 Define initial route handling for pfSense and honeypot sources only, with runtime-configurable channel labels.
- [x] 3.3 Define safe behavior for unknown or future sources so new source families can plug in later without redesigning the routing model.
- [x] 3.4 Verify routing design does not introduce per-rule routing or arbitrary channel mapping.

## 4. Slack Formatting

- [x] 4.1 Define the compact Slack payload contract with bounded, scan-friendly fields only.
- [x] 4.2 Define the detailed Slack payload contract, including allowed investigation context fields and redaction boundaries.
- [x] 4.3 Confirm detailed formatting reuses existing alert or incident context instead of recomputing MITRE, response, or target data.
- [x] 4.4 Define tests for compact vs detailed formatting, missing optional context, and secret-safe output.

## 5. Frontend Configuration

- [x] 5.1 Identify the existing runtime/admin configuration UI surface that should own notification policy controls.
- [x] 5.2 Define the notification policy UI fields, defaults, validation messages, and read/write flows.
- [x] 5.3 Define focused frontend tests for rendering, mutation permissions, validation, and effective-state display.
- [x] 5.4 Define visual verification expectations, including dark-theme fit and operator clarity for source routing and format settings.

## 6. Testing And Verification

- [x] 6.1 Define focused backend tests for policy evaluation, routing, runtime-config fallback behavior, RBAC, and audit logging.
- [x] 6.2 Define focused frontend tests for configuration UI behavior and effective policy display.
- [x] 6.3 Define migration/schema validation expectations only if implementation proves a new durable policy store is necessary.
- [x] 6.4 Run `openspec validate notification-policy-and-slack-routing --strict` and `git diff --check` before implementation handoff.
