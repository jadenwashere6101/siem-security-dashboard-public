# Admin User Management Spec

## Feature Overview

This change adds an admin-only API for creating new SIEM users.

The initial scope is intentionally narrow:
- only authenticated admins can create users
- newly created users default to role `viewer`
- submitted passwords are hashed before storage
- existing RBAC enforcement remains the source of truth for privileged access

This provides a safer operational path than manual database inserts while keeping the implementation minimal.

## Current State

- Viewer accounts currently exist only through manual database insertion.
- There is no backend API for creating users.
- Existing admin authentication already works.
- RBAC enforcement already protects privileged routes.
- The `users` table already exists for database-backed accounts.

## API Design

### Route

- `POST /admin/users`

### Request Body

- `username` (string)
- `password` (string)

### Success Response

- HTTP 201
- JSON success message

Example:

```json
{
  "message": "User created successfully"
}
```

### Error Response

- HTTP 400 or 409 for invalid or duplicate input
- HTTP 401 for unauthenticated requests
- HTTP 403 for authenticated non-admin users

Example:

```json
{
  "error": "Unable to create user"
}
```

### Rules

- `username` must be unique
- `password` must be hashed before storing
- `role` is always `viewer` by default for this route
- `is_active` should default to `true`
- the route does not accept a caller-supplied role in v1

## Backend Requirements

- The route must use:
  - `@login_required`
  - `@admin_required`
- The route must use the existing database connection helper.
- Password hashing must use Werkzeug password hashing helpers.
- User creation must insert into the existing `users` table.
- Duplicate usernames must be handled safely and predictably.
- The route must not modify existing login behavior.
- The route must return JSON responses consistent with the rest of the backend.

## Security Requirements

- Never store plaintext passwords.
- Never log plaintext passwords.
- Backend must enforce admin-only access.
- Frontend visibility is not a security boundary.
- Error responses should be generic enough to avoid unnecessary information leakage.
- The API must not expose password hashes in responses.

## Migration Plan

1. No schema changes are required.
2. Add the admin-only user creation route.
3. Hash the submitted password before inserting the user.
4. Verify duplicate usernames are handled safely.
5. Test the route with `curl` using an authenticated admin session.
6. Verify the created viewer account can log in through the existing login flow.
7. Verify the new viewer cannot access admin-only routes.

## Acceptance Criteria

- Admin can create a new viewer account through `POST /admin/users`.
- Newly created accounts default to role `viewer`.
- Viewer can log in successfully with the created credentials.
- Viewer cannot access admin-only routes.
- Duplicate username returns a safe error response.
- Stored password value is a hash, not plaintext.
- Existing admin login behavior remains unchanged.

## Non-Goals

This change does not include:
- signup page
- password reset
- multi-role system beyond `admin` and `viewer`
- role selection at user creation time
- user management UI
- self-service registration
