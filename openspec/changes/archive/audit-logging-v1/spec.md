# Audit Logging v1 Spec

## Feature Overview

This change adds a minimal audit logging capability for security-relevant admin and RBAC events in the SIEM.

The scope is intentionally narrow:
- log key authentication events
- log key admin user-management actions
- log RBAC denials for protected routes
- capture enough metadata for investigation without exposing sensitive secrets

This provides a first version of accountability and traceability for privileged actions and access-control failures.

## Current State

- RBAC enforcement already exists.
- Admin can create users.
- Admin can activate and deactivate users.
- Viewer access to protected routes returns HTTP 403.
- Login success and failure occur today, but there is no dedicated audit log record for these events.
- No dedicated audit log table or structured audit event storage exists yet.

## Events to Log

This v1 must log the following event types:

1. Admin creates a user
2. Admin activates a user
3. Admin deactivates a user
4. RBAC denies a protected action
5. Login success
6. Login failure

Expected examples:
- `user_create`
- `user_activate`
- `user_deactivate`
- `rbac_deny`
- `login_success`
- `login_failure`

## Audit Log Data Fields

Each audit log record should include:
- `event_type`
- `actor_username` if known
- `actor_role` if known
- `target_username` when relevant
- `target_alert_id` when relevant
- `http_method` when relevant
- `request_path` when relevant
- `source_ip` if available
- `created_at` timestamp

Optional v1 field:
- `details` as structured JSON for limited non-sensitive context

Field rules:
- do not log plaintext passwords
- do not log password hashes
- do not log raw credential payloads
- only include target identifiers relevant to the event

## Backend Requirements

- Authentication flows must emit audit events for:
  - login success
  - login failure
- Admin user-management flows must emit audit events for:
  - user creation
  - user activation
  - user deactivation
- RBAC enforcement must emit audit events for protected-route denial events.
- Audit logging should use a shared backend helper so event shape remains consistent.
- Audit logging failure must not crash normal request handling or block the main action response.
- If audit persistence fails, the main app should continue operating and log the audit failure through normal application logging.

## Database Requirements

This change requires a dedicated audit log table.

Minimal v1 table expectations:
- `id`
- `event_type`
- `actor_username`
- `actor_role`
- `target_username`
- `target_alert_id`
- `http_method`
- `request_path`
- `source_ip`
- `details`
- `created_at`

Database design rules:
- use append-only audit records
- do not update or delete audit records during normal application flow
- store only non-sensitive metadata needed for investigation

## Security Requirements

- Never store plaintext passwords in audit logs.
- Never store password hashes in audit logs.
- Never log raw request bodies for login or user creation events.
- Include actor username when known.
- Include actor role when known.
- Include target username or alert identifier when relevant.
- Include source IP when available.
- Include a timestamp on every audit event.
- Audit logging must not weaken or bypass existing RBAC controls.
- Audit log write failure must not crash the app or break the protected action response.

## Acceptance Criteria

- Successful admin login creates an audit event.
- Failed login creates an audit event.
- Admin user creation creates an audit event with actor and target username.
- Admin user activation creates an audit event with actor and target username.
- Admin user deactivation creates an audit event with actor and target username.
- RBAC denial creates an audit event with actor, role, route, method, and source IP when available.
- Audit records include a timestamp.
- Audit records do not contain plaintext passwords.
- Audit records do not contain password hashes.
- If audit log persistence fails, the main request still returns its normal response path without crashing the app.

## Non-Goals

This change does not include:
- audit log UI
- search or filtering UI
- export of audit logs
- retention policy management
- external SIEM forwarding
- tamper-evident signing
- full request/response capture
- logging every read-only dashboard action
