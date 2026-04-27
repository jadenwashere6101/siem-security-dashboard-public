# RBAC Viewer Support Spec

## Feature Overview

This phase adds real `viewer` account support to the SIEM while preserving the current env-based admin login.

The current RBAC work already establishes:
- role-aware authentication payloads
- backend admin-only protection for privileged write routes
- frontend role-aware visibility for write controls

What is still missing is a real way for non-admin users to authenticate as `viewer`.

This phase should add that capability with the smallest safe expansion:
- preserve the current admin login path exactly
- introduce a minimal users table for non-admin accounts
- default new users to `viewer`
- keep backend authorization as the source of truth

## Current State

- Admin login is currently env-based.
- Existing admin credentials authenticate successfully today and must keep working.
- `/auth/me` already returns `authenticated`, `user`, and `role`.
- Backend already enforces admin-only access on privileged write routes.
- Frontend already hides write-capable controls for non-admin users.
- No `users` table exists yet.
- There is no persistent viewer account system yet.

## Proposed Minimal Users Table

Add a minimal `users` table for real non-admin accounts.

Required columns:
- `id`
  - integer primary key
- `username`
  - unique
  - non-null
- `password_hash`
  - non-null
- `role`
  - non-null
  - allowed values:
    - `admin`
    - `viewer`
  - default: `viewer`
- `created_at`
  - timestamp
  - default current time
- `is_active`
  - boolean
  - default `true`

Minimal design rules:
- keep the schema intentionally small
- do not add profile fields, org fields, or permission tables
- do not require a separate RBAC mapping table in v2

## Admin Compatibility Path

Existing env-based admin login remains the primary compatibility path.

Requirements:
- the current env-backed admin username/password must continue to authenticate exactly as they do today
- successful env-admin login must continue to resolve to role `admin`
- the env-admin path must not depend on the new `users` table
- if the database is unavailable, env-admin login behavior should remain functional if the existing system would otherwise function

Optional compatibility rule for v2:
- a database-backed `admin` account may exist later, but it must not replace or weaken the env-admin fallback in this phase

## Viewer Login Behavior

Viewer login uses the existing login route and existing session/auth flow.

Expected behavior:
- login request still posts `username` and `password`
- backend first checks whether the credentials match the existing env-admin account
- if not, backend checks the `users` table for an active user with the submitted username
- backend verifies the submitted password against the stored password hash
- if valid, backend authenticates that user with role `viewer`
- if invalid, backend returns the existing invalid-credentials response pattern

Session/auth behavior:
- authenticated viewer sessions use the same Flask-Login/session flow already in place
- `/auth/me` returns the viewer username and `role: "viewer"`
- viewer sessions remain read-only because backend authorization is already enforced on privileged routes

## Password Storage Strategy

Passwords for database-backed users must be hashed, never stored in plaintext.

Requirements:
- store only `password_hash`
- use a standard password hashing approach already compatible with the Flask/Python stack
- include per-password salt through the hashing library rather than custom crypto logic
- do not build a custom hashing scheme
- do not store plaintext passwords in the database, logs, seeds, or config files

V2 expectation:
- use a well-supported password hash helper such as Werkzeug password hashing
- compare passwords using the corresponding verify/check helper

## Backend Changes Required

Authentication:
- extend login logic to support a second credential source:
  - existing env-admin credentials
  - database-backed users
- preserve current env-admin behavior as the highest-safety path
- load `role` from the database-backed user record for viewer accounts

Session/user model:
- extend the authenticated user model to carry:
  - username or stable user identifier
  - role
- ensure Flask-Login `user_loader` can reconstruct both:
  - env-admin sessions
  - database-backed viewer sessions

Database access:
- add a small user lookup path by username
- verify `is_active` before authenticating a database-backed user

Authorization:
- keep current admin-only route protection unchanged
- do not weaken existing admin-only enforcement
- continue to deny viewer write actions with HTTP 403 JSON

Logging:
- continue logging authorization failures
- log failed login attempts without writing plaintext passwords

## Frontend Changes Required

Frontend behavior should remain minimal because Phase 1 role awareness already exists.

Required frontend expectations:
- continue consuming `role` from `/auth/me`
- viewer users should see the existing read-only dashboard experience
- viewer users should not see:
  - resolve controls
  - manual response action controls
- viewer users should still be able to:
  - view alerts
  - filter/search alerts
  - open alert details
  - view charts and map
  - download TXT/PDF reports

Potential small frontend adjustment:
- ensure login error handling remains correct for invalid viewer credentials using the same existing login UX

No v2 frontend redesign is required.

## Migration Plan

1. Create the `users` table with the minimal schema.
2. Keep env-admin authentication untouched.
3. Add backend support for looking up database-backed users by username.
4. Add password-hash verification for database-backed users.
5. Update authenticated session loading so database-backed users retain their role.
6. Create one test viewer account manually in a safe local/dev path.
7. Verify viewer login works without affecting env-admin login.
8. Verify `/auth/me` returns `role: "viewer"` for the viewer account.
9. Verify privileged write routes still return HTTP 403 for viewers.
10. Verify viewer read-only dashboard workflows still work.

## Rollback Plan

If this phase causes auth instability:

1. Stop using database-backed user login paths.
2. Revert backend auth logic to env-admin-only behavior.
3. Leave existing admin route protection intact.
4. Keep the `users` table unused rather than rushing a destructive schema rollback.
5. Confirm env-admin login still works end-to-end.

Rollback priority:
- preserve admin access first
- preserve dashboard availability second
- remove viewer login support only if required

## Acceptance Criteria

Admin compatibility:
- existing env-admin credentials still log in successfully
- env-admin still receives `role: "admin"`
- current admin workflows remain unchanged

Viewer authentication:
- a database-backed viewer account can log in successfully
- invalid viewer password is rejected
- inactive viewer account cannot log in
- `/auth/me` returns the correct viewer identity and `role: "viewer"`

Viewer authorization:
- viewer can access dashboard read routes
- viewer can open alert details
- viewer can download TXT and PDF reports
- viewer cannot resolve alerts
- viewer cannot execute `block_ip`
- viewer cannot execute `monitor`
- viewer cannot execute `flag_high_priority`
- viewer direct API attempts to privileged routes return HTTP 403

Security:
- database-backed passwords are stored only as hashes
- plaintext passwords are not stored or logged
- backend remains the source of truth for privileged action enforcement
- env-admin access is not locked out by the migration

## Risks and Non-Goals

### Risks

- mixing env-admin auth with database-backed user auth can introduce session-loading edge cases
- Flask-Login user reconstruction can accidentally map viewer sessions incorrectly if the user loader is not designed carefully
- incorrect precedence between env-admin and database-backed users could break admin compatibility
- introducing a users table expands auth scope and raises the risk of login regressions
- weak migration/testing discipline could create a state where viewer login exists but session role handling is incomplete

### Non-Goals

This phase does not include:
- removing env-based admin login
- multi-admin management UI
- self-service signup
- password reset flows
- organizations
- SSO
- multi-tenancy
- granular per-feature permissions beyond `admin` and `viewer`
- audit dashboards beyond current authorization logging
