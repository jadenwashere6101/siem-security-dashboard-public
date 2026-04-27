# Admin Users UI Spec

## Feature Overview

This change adds an admin-only Users panel to the SIEM frontend.

The scope is intentionally minimal:
- only admins can see the panel
- admins can view existing users
- admins can create new viewer users
- admins can activate and deactivate existing users
- no sensitive credential data is exposed in the UI

This provides a basic operational UI for user management on top of the existing backend admin user APIs.

## Current State

- Backend already supports:
  - `POST /admin/users`
  - `GET /admin/users`
  - `PATCH /admin/users/<username>/status`
- Frontend already reads the current user role from `/auth/me`.
- Frontend already hides admin-only controls from non-admin users.
- No frontend user management UI exists yet.

## UI Design

The UI should introduce a compact admin-only Users panel within the existing SIEM dashboard.

Expected panel contents:
- a user list section
- a create-user form
- activate/deactivate controls for existing users

User list display:
- `username`
- `role`
- `is_active`
- `created_at`

Create-user form:
- `username` input
- `password` input
- submit action

Status controls:
- active users show a deactivate action
- inactive users show an activate action

Design constraints:
- the panel should match the existing dark-theme dashboard styling
- the panel should feel like an internal admin utility, not a separate app
- no password hash or hidden credential fields are shown
- no role selector is included in v1

## Frontend Requirements

- Render the Users panel only when the authenticated role is `admin`.
- Do not render the Users panel for viewers or unauthenticated users.
- Fetch the user list from the backend admin users API.
- Submit new user creation through the existing create-user API.
- Submit activate/deactivate changes through the existing status API.
- Keep newly created users as `viewer` only.
- Handle backend errors with clear, minimal UI feedback.
- Refresh or update the user list after create or status-change actions succeed.
- Do not expose `password_hash` anywhere in component state, rendering, or logs.

## API Usage

The frontend should use these existing endpoints:

- `GET /admin/users`
  - load current users for the panel

- `POST /admin/users`
  - create a new viewer user
  - request body:
    - `username`
    - `password`

- `PATCH /admin/users/<username>/status`
  - activate or deactivate an existing user
  - request body:
    - `is_active`

Expected frontend behavior:
- use authenticated requests with existing session credentials
- treat backend responses as the source of truth
- refresh user state after successful mutations

## Security Rules

- Only admins may see or use the Users panel.
- Backend remains the source of truth for authorization.
- Hiding the UI is a usability feature, not a security boundary.
- The UI must never display `password_hash`.
- The UI must never allow role selection in v1.
- Newly created users must be viewers only.
- Viewer users must not be able to access or infer admin-user-management controls from the UI.

## Acceptance Criteria

- Admin sees a Users panel in the SIEM frontend.
- Viewer does not see a Users panel.
- Admin can load the current user list.
- Admin can create a new viewer user.
- Admin can activate an inactive user.
- Admin can deactivate an active user.
- The user list never includes `password_hash`.
- The UI does not expose role selection.
- Newly created users are viewers only.
- Backend permission failures are handled cleanly without breaking the dashboard.

## Non-Goals

This change does not include:
- role editing
- admin account creation from the UI
- password reset
- password editing
- user deletion
- pagination
- filtering
- search
- audit history
