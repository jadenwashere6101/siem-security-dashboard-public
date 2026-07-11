## Why

The standalone Blocklist navigation is only an alias for Response Registry's Blocklist Tracking view, while the supported removal action is easy to miss. The duplicate destination creates competing mental models, and a reported production IP requires careful runtime classification rather than destructive cleanup.

## What Changes

- **MAC AI:** Remove the standalone Blocklist sidebar destination while retaining Blocklist Tracking inside Response Registry and compatibility for legacy internal navigation.
- **MAC AI:** Make the existing supported Remove Tracking action discoverable and explicit that it ends SIEM tracking, preserves history, and does not change a firewall.
- **MAC AI:** Preserve analyst/super-admin RBAC, protected-target validation, audit events, idempotency, canonical tracking-only outcomes, and historical evidence.
- **MAC AI:** Produce a sanitized VM handoff for `12.12.12.12`; add no direct-delete endpoint, migration, or seed deletion.
- **VM AI, future explicit authorization only:** verify a clean approved deployment, classify the runtime record, and use the supported workflow only if applicable and separately authorized.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `response-registry-workspace`: Makes Response Registry the sole visible Blocklist workspace and clarifies removal affordance/legacy compatibility.
- `canonical-indicator-response-registry`: Defines safe runtime classification and supported non-destructive removal evidence.

## Impact

- Mac frontend/tests: section configuration, `App.js`, Sidebar/Settings landing options, Response Registry, navigation tests, and handoff documentation.
- Existing APIs/services remain authoritative: `/blocked-ips`, `/blocked-ips/<id>/unblock`, response-command `remove_tracking`, audit logging, and registry events.
- No schema/migration is expected. Future authorized VM work may read production tables/API and perform one supported mutation with before/after evidence.

