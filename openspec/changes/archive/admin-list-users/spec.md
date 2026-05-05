# Admin List Users Spec

## Feature Overview

This change adds an admin-only API for listing SIEM users.

The scope is intentionally minimal:
- only authenticated admins can view users
- the response includes operational account metadata only
- no sensitive credential data is exposed

This provides a simple management view for accounts that already exist in the system.

## Current State

- Users can be created through the admin user creation API.
- There is currently no API to view existing users.
- Admin authentication already works.
- RBAC enforcement already protects privileged routes.

## API Design

### Route

- `GET /admin/users`

### Response

- HTTP 200
- JSON array of users

Returned fields:
- `username`
- `role`
- `is_active`
- `created_at`

Example:

```json
[
  {
    "username": "viewer1",
    "role": "viewer",
    "is_active": true,
    "created_at": "2026-04-24T12:00:00Z"
  }
]
```

## Backend Requirements

- The route must use:
  - `@login_required`
  - `@admin_required`
- The route must query the existing `users` table.
- The route must return all users currently stored in the table.
- The route must not return `password_hash`.
- The route should return users in a stable, predictable order.

## Security Requirements

- Only admins may access the route.
- Backend must enforce admin-only access.
- No sensitive credential data may be returned.
- The response must never include `password_hash`.

## Acceptance Criteria

- Admin can call `GET /admin/users` successfully.
- Admin receives a list of users with:
  - `username`
  - `role`
  - `is_active`
  - `created_at`
- Viewer cannot access the route.
- Unauthenticated requests cannot access the route.
- The response does not include `password_hash`.

## Non-Goals

This change does not include:
- pagination
- filtering
- sorting controls beyond any default backend order
- UI
- user editing
- user deletion
