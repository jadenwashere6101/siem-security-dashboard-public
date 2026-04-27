# Session Identity Clarity Spec

## Feature Overview

This change improves session and account clarity in the SIEM frontend so users can always see which account and role are currently active.

The scope is intentionally minimal:
- show the signed-in username and role in the top UI
- make logout or account switching explicit
- surface a clear message when the active session changes
- keep the existing session model unchanged

This is primarily a usability and demo-clarity improvement. It does not change how browser sessions work.

## Current State

- Browser tabs share the same session cookie.
- Logging in as a different user in one tab changes the active session for all tabs in that browser profile.
- A tab that previously appeared to be admin may refresh into a viewer session if the shared cookie changed.
- The current UI does not make active identity and role prominent enough for demos or operational clarity.

## UX Design

The SIEM should show session identity clearly in the top header area.

Visible identity elements:
- signed-in username
- signed-in role:
  - `admin`
  - `viewer`

Suggested presentation:
- compact top badge or pill in the header
- clear account label such as:
  - username
  - role
- keep the styling aligned with the existing dark SIEM dashboard

Session actions:
- keep a clear `Logout` action
- optionally label it more explicitly as `Switch Account` or `Logout`

Session change messaging:
- if auth state is re-checked and the active identity or role changes from the previously known value, show clear feedback:
  - `Session changed. Permissions updated.`

Demo guidance:
- do not attempt to support two different signed-in accounts in two normal tabs of the same browser profile
- recommended demo setup:
  - admin in normal browser
  - viewer in incognito or separate browser

## Frontend Requirements

- Track the currently authenticated username and role from the auth response.
- Display the current username and role prominently in the top header area.
- Keep the logout/account switch action clearly visible.
- Detect when a later auth check returns a different authenticated identity or role than the previously stored one.
- Show a clear session-change message when identity or role changes mid-session.
- Preserve the current auth flow and session model.
- Do not introduce multi-session support in the same browser profile.

## Security Rules

- Backend remains the source of truth for identity and authorization.
- This change must not alter the session cookie model.
- This change must not weaken auth or RBAC behavior.
- The frontend should reflect the current backend-authenticated identity, not infer it independently.
- Clear identity display is a usability improvement, not a security boundary.

## Acceptance Criteria

- The signed-in username is visible in the top UI.
- The signed-in role is visible in the top UI.
- A clear logout or switch-account action is visible.
- If the authenticated user or role changes after a refresh or auth re-check, the UI shows:
  - `Session changed. Permissions updated.`
- Existing auth behavior remains unchanged.
- Existing RBAC behavior remains unchanged.
- The UI does not attempt to support two different active accounts in two normal tabs of the same browser profile.

## Non-Goals

This change does not include:
- multi-session support in one browser profile
- per-tab isolated authentication
- backend session redesign
- multiple concurrent identities in one browser
- SSO
- account impersonation
- role changes
- changes to cookie behavior
