# Custom JSON Rate Limit Response Spec

## Feature Overview

This change adds a JSON error handler for HTTP 429 rate-limit responses in the SIEM backend.

The scope is intentionally minimal:

- keep existing rate limiting in place
- replace the default HTML 429 response with a JSON response
- align rate-limit errors with the rest of the SIEM API style

This improves API consistency for frontend consumers, scripts, and operational testing.

## Current State

- Flask-Limiter rate limiting already works.
- Login returns HTTP 429 after too many attempts.
- The current 429 response body is HTML.
- Most SIEM backend API responses already use JSON.
- Existing rate-limit thresholds are already defined and should remain unchanged.

## Backend Requirements

- Add a backend error handler for HTTP 429 responses.
- The handler must return:
    - status code: 429
    - JSON body:

      {
        "error": "rate_limited",
        "message": "Too many requests. Please try again later."
      }

- The handler must apply consistently to Flask-Limiter-triggered 429 responses.
- Existing rate-limit thresholds must remain unchanged.
- Existing route logic must remain unchanged.
- Existing auth and RBAC logic must remain unchanged.

## Security Requirements

- Rate limiting behavior must remain enforced exactly as it is today.
- This change must not weaken existing auth protections.
- This change must not weaken RBAC protections.
- The JSON response must not expose internal implementation details.
- The response should remain generic and safe for public-facing API clients.

## Acceptance Criteria

- When a rate limit is exceeded, the backend returns HTTP 429.
- The 429 response body is JSON, not HTML.
- The response body is:

  {
    "error": "rate_limited",
    "message": "Too many requests. Please try again later."
  }

- Existing rate-limit thresholds remain unchanged.
- Existing auth behavior remains unchanged.
- Existing RBAC behavior remains unchanged.

## Non-Goals

This change does not include:

- changing rate-limit thresholds
- changing rate-limit scope
- frontend-specific handling
- custom retry timing metadata
- per-route custom 429 messages
- redesign of auth or RBAC behavior
