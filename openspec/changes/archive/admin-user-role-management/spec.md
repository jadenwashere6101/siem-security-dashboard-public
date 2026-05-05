 # Admin User Role Management Spec

  ## Feature Overview

  This change adds a minimal super-admin-only capability to update the role of an existing
  database-backed user from the admin dashboard.

  The scope is intentionally narrow:

  - only super_admin may change roles
  - only existing database-backed users may be updated
  - allowed target roles are limited to:
      - analyst
      - viewer
  - env-admin remains outside the scope of this API and UI

  This provides basic role reassignment without expanding into a broader identity-management
  system.

  ## Current State

  - Three-tier RBAC already exists:
      - super_admin
      - analyst
      - viewer
  - Super Admin can create users as analyst or viewer.
  - Super Admin can list users.
  - Super Admin can activate/deactivate users.
  - Super Admin can reset passwords.
  - There is currently no API or UI to change an existing user’s role after creation.

  ## API Design

  ### Route

  - PATCH /admin/users/<username>/role

  ### Request Body

  - role (string)

  Example:

  {
    "role": "analyst"
  }

  ### Allowed Roles

  - analyst
  - viewer

  ### Disallowed Roles

  - super_admin
  - admin

  ### Success Response

  - HTTP 200
  - JSON success message

  Example:

  {
    "message": "User role updated successfully"
  }

  ### Error Response

  - HTTP 400 for invalid input
  - HTTP 401 for unauthenticated requests
  - HTTP 403 for authenticated non-super-admin users
  - HTTP 404 if the target user does not exist
  - HTTP 500 for unexpected backend failure

  Example:

  {
    "error": "Unable to update user role"
  }

  ## Backend Requirements

  - Protect the route with:
      - @login_required
      - @super_admin_required
  - Use the existing database connection helper.
  - Update only users.role.
  - Accept only:
      - analyst
      - viewer
  - Reject:
      - super_admin
      - admin
      - any unknown value
  - Do not modify password, username, or is_active.
  - Do not provide any path to modify env-admin.
  - Return JSON responses consistent with existing admin APIs.
  - Keep existing user create/list/status/password reset behavior unchanged.

  ## Frontend Requirements

  - Add a compact role-management control to the existing AdminUsersPanel.
  - The control should be visible only in the super-admin administration UI.
  - Each database-backed user row should allow changing role between:
      - viewer
      - analyst
  - The UI should submit the role update through:
      - PATCH /admin/users/<username>/role
  - The UI should remain compact and operational.
  - Existing create/list/status/password reset behavior must remain unchanged.
  - Do not add any control for assigning:
      - super_admin
      - admin

  ## Security Requirements

  - Only super_admin may access the API.
  - Backend remains the source of truth for role assignment authorization.
  - Env-admin must not be modifiable through this API.
  - The API must never allow assignment of:
      - super_admin
      - admin
  - The route must update only the intended database-backed user role.
  - Existing RBAC behavior must remain intact after role changes.

  ## Audit Logging Behavior

  - Successful role change must emit an audit event:
      - user_role_update
  - The audit event must include:
      - actor username
      - actor role
      - target username
      - new role
      - request path
      - HTTP method
      - source IP
  - The audit event must not include unrelated secrets or credentials.
  - Existing audit logging behavior for other admin actions must remain unchanged.

  ## Acceptance Criteria

  - Super Admin can change an existing user role from viewer to analyst.
  - Super Admin can change an existing user role from analyst to viewer.
  - The API rejects attempts to assign:
      - super_admin
      - admin
  - The API rejects unknown role values.
  - Viewer cannot access the route.
  - Analyst cannot access the route.
  - Unauthenticated requests cannot access the route.
  - Env-admin is not modifiable through this API.
  - Successful role updates create a user_role_update audit event.
  - Existing user create/list/status/password reset behavior remains unchanged.

  ## Non-Goals

  This change does not include:

  - creating super-admin accounts
  - modifying env-admin
  - bulk role changes
  - multi-role assignment
  - custom permission editing
  - role history UI
  - user deletion
  - identity-provider synchronization
