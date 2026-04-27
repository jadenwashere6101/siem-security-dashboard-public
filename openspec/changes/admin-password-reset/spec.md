# Admin Password Reset Spec

## Feature Overview

This change adds an admin-only API for resetting the password of an existing database-backed user.

The scope is intentionally minimal:

- only authenticated admins can reset a user password
- the new password is hashed before storage
- the existing users table is reused
- env-admin credentials remain outside the scope of this route

This provides a basic operational password reset capability for database-backed accounts without expanding into a full self-service account system.

## Current State

- Admin can create viewer users.
- Admin can list users.
- Admin can activate and deactivate users.
- Database-backed user passwords are stored as hashes.
- There is currently no password reset API.
- The env-admin account is not stored in the users table and is therefore outside the scope of this feature.

## API Design

### Route

- PATCH /admin/users/<username>/password

### Request Body

- password (string)

Example:

{
  "password": "newPasswordHere"
}

### Success Response

- HTTP 200
- JSON success message

Example:

{
  "message": "Password updated successfully"
}

### Error Response

- HTTP 400 for invalid input
- HTTP 401 for unauthenticated requests
- HTTP 403 for authenticated non-admin users
- HTTP 404 if the target user does not exist
- HTTP 500 for unexpected backend failure

Example:

{
  "error": "Unable to update password"
}

### Rules

- only database-backed users in the users table are eligible
- the route updates only password_hash
- the route does not change username
- the route does not change role
- the route does not change is_active
- the route cannot affect env-admin because env-admin is not stored in users

## Backend Requirements

- The route must use:
    - @login_required
    - @admin_required
- The route must use the existing database connection helper.
- The submitted password must be hashed before storing.
- Password hashing must use the existing Werkzeug password hashing helpers already used by the backend.
- The route must update only the password_hash field for the specified username.
- The route must return a safe error if the target user does not exist.
- The route must return JSON responses consistent with the rest of the backend.
- Existing login behavior must continue to work with the newly stored hash.

## Security Requirements

- Never store plaintext passwords.
- Never log plaintext passwords.
- Never return password values in API responses.
- Never return password hashes in API responses.
- Only admins may access the route.
- Backend must enforce admin-only access.
- The route must not provide a path to modify env-admin credentials.
- Error responses should remain generic and safe.

## Audit Logging Behavior

- Successful password reset must emit an audit event.
- The audit event should record:
    - event type
    - actor username
    - actor role
    - target username
    - request path
    - HTTP method
    - source IP if available
    - timestamp
- The audit event must not include:
    - plaintext password
    - password hash
    - raw password request payload

Suggested event type:

- user_password_reset

## Acceptance Criteria

- Admin can reset the password of a database-backed user.
- The new password is stored as a hash.
- The target user can log in with the new password.
- The target user can no longer log in with the old password.
- Viewer cannot access the route.
- Unauthenticated requests cannot access the route.
- A non-existent target user returns HTTP 404.
- No plaintext password is stored or logged.
- No password hash is returned in responses.
- Successful password reset writes an audit event without including password data.

## Non-Goals

This change does not include:

- self-service password reset
- forgot-password email flow
- password reset UI
- env-admin password management
- password history
- password complexity policy changes
- role changes
- user deletion
