# Admin Password Reset UI Spec

## Feature Overview

This change adds a minimal admin-only password reset control to the existing Users panel in the SIEM frontend.

The scope is intentionally narrow:
- admin can reset the password of a database-backed user
- the action is initiated from the Users panel
- the frontend uses the existing backend password reset API
- no password values are retained or displayed after submission

This provides a basic operational password reset workflow without expanding into a full account settings system.

## Current State

- Backend already supports `PATCH /admin/users/<username>/password`.
- Successful password reset already creates an audit event.
- The Users panel already supports:
  - listing users
  - creating users
  - activating users
  - deactivating users
- There is currently no password reset UI.
- Env-admin credentials are not stored in the `users` table and are outside the scope of this UI.

## UI Design

The password reset control should be added to the existing admin-only Users panel.

Expected interaction:
- each database-backed user row includes a reset password control
- admin selects the control for a user
- admin enters a new password
- admin submits the reset request
- the UI shows success or error feedback

Minimal UI options for v1:
- inline password reset row within the selected user row
- small expandable reset form
- compact modal-like inline section inside the existing Users panel

Design constraints:
- match the current dark SIEM styling
- keep the control compact and operational
- do not add role editing
- do not add env-admin password controls
- do not display password hashes
- do not display plaintext passwords after submission

## Frontend Requirements

- Render password reset controls only for admin users.
- Keep the feature inside the existing Users panel.
- Allow admin to enter a new password for a selected database-backed user.
- Submit the new password to the existing password reset API.
- Show clear success and error feedback.
- Clear the password input after submit, whether success or failure handling completes.
- Do not retain plaintext password in visible UI after submission.
- Do not render any password hash data.
- Keep all existing user-management functionality unchanged.

## API Usage

Use the existing backend endpoint:

- `PATCH /admin/users/<username>/password`

Request body:
- `password`

Example:

```json
{
  "password": "newPasswordHere"
}
```

Expected frontend behavior:
- use authenticated requests with existing session credentials
- treat backend responses as the source of truth
- show success message on HTTP 200
- show safe error feedback on failure responses

## Security Rules

- Only admins may see or use the password reset control.
- Backend remains the source of truth for authorization.
- Frontend visibility is not a security boundary.
- The UI must never display `password_hash`.
- The UI must never display plaintext password after submission.
- The UI must not expose env-admin password reset functionality.
- The UI must not introduce role editing or other unrelated account management controls.

## Acceptance Criteria

- Admin sees a password reset control in the Users panel.
- Viewer does not see password reset controls.
- Admin can submit a new password for a database-backed user.
- Successful reset shows success feedback.
- Failed reset shows safe error feedback.
- Password input is cleared after submission handling.
- The UI never displays `password_hash`.
- The UI never displays plaintext password after submission.
- Existing user create/list/activate/deactivate behavior remains unchanged.

## Non-Goals

This change does not include:
- self-service password reset
- forgot-password flow
- env-admin password reset
- role editing
- password history
- password policy redesign
- dedicated password management page
- user deletion
