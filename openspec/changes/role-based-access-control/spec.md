# Role-Based Access Control Spec

## Feature Overview

Role-Based Access Control (RBAC) limits what authenticated users can do based on an assigned role.

RBAC is needed in this SIEM because the current dashboard includes both:
- read-only analyst workflows such as viewing alerts, charts, maps, and reports
- state-changing workflows such as resolving alerts and executing response actions

A first version of RBAC should separate those responsibilities cleanly:
- `admin` keeps full operational access
- `viewer` gets read-only dashboard access

This reduces accidental changes, enforces least privilege, and aligns the SIEM with standard read-only vs edit access patterns.

## Roles & Permissions Table

| Action | admin | viewer |
|---|---|---|
| Log in | Yes | Yes |
| View dashboard | Yes | Yes |
| View alerts | Yes | Yes |
| Filter/search alerts | Yes | Yes |
| Open alert details | Yes | Yes |
| View charts | Yes | Yes |
| View map | Yes | Yes |
| Download TXT incident reports | Yes | Yes |
| Download PDF incident reports | Yes | Yes |
| Resolve alerts | Yes | No |
| Execute `block_ip` | Yes | No |
| Execute `monitor` | Yes | No |
| Execute `flag_high_priority` | Yes | No |
| Change alert state | Yes | No |
| Modify SIEM state | Yes | No |

## Affected Routes / Endpoints

### Read Routes Allowed for `admin` and `viewer`
- `POST /login`
- `POST /logout`
- `GET /auth/me`
- `GET /alerts`
- `GET /alerts/<id>/response-log`
- `GET /alerts/<id>/report`
- `GET /alerts/<id>/report/pdf`
- `GET /alerts/report`
- `GET /alerts/report/pdf`

### Privileged Routes Restricted to `admin`
- `POST /alerts/<id>/status`
- `POST /alerts/<id>/execute`

### Route Protection Rules
- All privileged routes must be enforced on the backend.
- UI-only hiding is not sufficient protection.
- Any future route that changes SIEM state must also require `admin`.

## Backend Changes

### User Role Model
- Add a role attribute to authenticated SIEM users.
- Allowed values for v1:
  - `admin`
  - `viewer`

### Default Role Behavior
- Existing admin login must continue to work as `admin`.
- New users must default to `viewer` unless explicitly created as `admin`.

### Authorization Enforcement
- Add a simple role-check helper or decorator for privileged endpoints.
- Enforce `admin` role for all state-changing actions.
- Deny by default for privileged actions when:
  - role is missing
  - role is invalid
  - authenticated user is not `admin`

### Error Response

Unauthorized privileged actions must return HTTP 403 with JSON:

```json
{
  "error": "forbidden",
  "message": "Admin role required"
}
```

### Logging

All authorization failures must be logged with:
- timestamp
- username if known
- role if known
- route
- HTTP method
- source IP if available

## Frontend Changes

Frontend updates are usability improvements only and must not replace backend enforcement.

### Admin UI
- Show all current action controls.
- Preserve current behavior for resolving alerts and executing response actions.

### Viewer UI
- Hide or disable state-changing controls:
  - resolve alert button
  - response action buttons
  - any other control that modifies alert or SIEM state
- Preserve all read-only access:
  - dashboard
  - alerts
  - alert details
  - charts
  - map
  - TXT/PDF report downloads

### Access Denied Handling
- If a viewer triggers a protected action by direct request or stale UI state, show a clear "Access denied" message.
- Frontend should handle 403 responses cleanly without breaking the dashboard session.

### Auth Payload
- Extend authenticated user payload to include role information so the frontend can render the correct controls.

## Database Changes

### Users Table Modification
- Add a `role` column to the users table.

### Role Column Definition
- name: `role`
- type: varchar or equivalent string type
- allowed values:
  - `admin`
  - `viewer`
- default: `viewer`
- nullability: non-null after migration/backfill

### Migration Requirements
- Backfill current admin account(s) to `admin`.
- Backfill any existing non-admin user(s) to `viewer`.
- Ensure all future user creation paths default to `viewer`.

## Security Rules

### Least Privilege
- Users receive only the minimum permissions required for their role.
- `viewer` is read-only by design.

### Deny by Default
- Any privileged action without an explicit `admin` role check must be denied.
- Missing role information must never grant write access.

### Backend Enforcement
- Backend authorization is mandatory for every privileged route.
- Frontend control visibility is convenience only.

### Auth Compatibility
- Do not break the existing authentication flow.
- Do not require a redesign of login for v1.

## Acceptance Criteria

### Admin Acceptance Criteria
- Admin can log in with the existing admin login.
- Admin can view dashboard, alerts, charts, and map.
- Admin can open alert details.
- Admin can filter/search alerts.
- Admin can download TXT and PDF incident reports.
- Admin can resolve alerts.
- Admin can execute `block_ip`, `monitor`, and `flag_high_priority`.

### Viewer Acceptance Criteria
- Viewer can log in successfully.
- Viewer can view dashboard, alerts, charts, and map.
- Viewer can open alert details.
- Viewer can filter/search alerts.
- Viewer can download TXT and PDF incident reports.
- Viewer cannot resolve alerts.
- Viewer cannot execute `block_ip`, `monitor`, or `flag_high_priority`.
- Viewer cannot modify alert state by direct HTTP request.

### Security Acceptance Criteria
- Privileged routes return HTTP 403 for authenticated viewers.
- 403 responses use clear JSON error messages.
- Authorization failures are logged.
- Existing admin behavior remains unchanged.

## Rollout Plan

1. Add `role` column to the users table with default `viewer`.
2. Backfill existing admin account(s) to `admin`.
3. Add backend role resolution during authenticated requests.
4. Add backend authorization checks for privileged endpoints.
5. Add logging for authorization failures.
6. Extend auth payload so frontend knows the current role.
7. Update frontend to hide or disable privileged controls for viewers.
8. Verify admin workflows still work.
9. Verify viewer workflows are read-only.
10. Verify TXT/PDF incident report downloads still work for both roles.

## Risks & Non-Goals

### Risks
- Existing login or session logic may assume all authenticated users are effectively admins.
- Missing backend coverage on one privileged route would create a security gap.
- Incorrect migration/backfill could assign the wrong role to current users.
- Frontend-only gating without backend enforcement would leave privileged actions exposed.

### Non-Goals
This v1 does not include:
- organizations
- SSO
- multi-tenancy
- external identity providers
- group-based access models
- approval workflows
- granular per-endpoint custom permissions
- in-app role administration UI
- audit dashboards beyond authorization failure logging
