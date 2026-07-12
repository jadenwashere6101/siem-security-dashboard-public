## 1. Shared Source Inventory and Backend Aggregation Contract — Mac AI

- [x] 1.1 Add one backend canonical source inventory module with the six exact source IDs, source types, display labels, and Live Logs destination IDs defined by the specification.
- [x] 1.2 Replace the existing events-read source allowlist with values derived from the shared backend inventory without changing `/events/search` behavior.
- [x] 1.3 Add or centralize frontend source metadata so Source Health, Live Logs, Dashboard source choices, and Detection Rules labels consume aligned identities without changing existing labels or behavior.
- [x] 1.4 Add focused backend and frontend contract tests that assert the exact six-entry inventory and prevent source/source-type/label/destination drift.
- [x] 1.5 Define a reusable read-only aggregation helper interface accepting one timezone-aware UTC observation instant and returning all required per-source fields.

## 2. Backend API and Tests — Mac AI

- [x] 2.1 Implement one grouped `events` aggregation using `created_at`, conditional uncapped counts, and the exact UTC boundaries from the specification.
- [x] 2.2 Merge grouped results onto the canonical inventory so all six sources appear exactly once, including never-seen sources with null/zero values.
- [x] 2.3 Add and register `GET /source-health` with `login_required` and `analyst_or_super_admin_required`, stable serialization, and fail-closed database error handling.
- [x] 2.4 Add focused query tests for exact hour/day boundaries, events beyond `generated_at`, uncapped counts above 100, latest event, mixed sources, and an entirely empty `events` table.
- [x] 2.5 Add API contract tests for field types, all six canonical identities, never-seen semantics, authentication, analyst/super-admin access, insufficient-role rejection, and database failure behavior.
- [x] 2.6 Inspect the aggregation with production-like data volume and `EXPLAIN` evidence; retain the no-migration design when existing indexes are adequate, and stop for explicit review before adding any migration if a blocker is proven.
- [x] 2.7 Run focused backend tests for Source Health, existing events search, authentication/RBAC, and affected source-aware API contracts.

## 3. Sidebar and Workspace Frontend Implementation — Mac AI

- [x] 3.1 Add Source Health immediately after Dashboard in the Overview section using existing role-visibility and destination-aware navigation conventions.
- [x] 3.2 Add a focused Source Health service using `buildSiemPath`, session credentials, established JSON/error handling, and the single backend endpoint.
- [x] 3.3 Add one shared Source Health workspace component that renders all six source entries and the required last-event, last-hour, UTC-today, total, and never-seen values.
- [x] 3.4 Implement initial loading, all-never-seen empty explanation, retained-data refresh, and request-error states without treating failures as zero activity.
- [x] 3.5 Integrate the workspace into `App.js` without changing Dashboard alert state, calculations, filters, sorting, charts, or refresh behavior.
- [x] 3.6 Add focused service, component, sidebar-order, App-routing, never-seen, loading, empty, error, accessibility, and Dashboard-regression tests.

## 4. Polling, Navigation, and Browser Verification — Mac AI

- [x] 4.1 Reuse the existing automatic refresh interval so Source Health performs one initial request, schedules one timer only when enabled, and cleans it up on workspace exit/unmount.
- [x] 4.2 Verify background refresh updates values without navigation actions, focus movement, scroll reset, duplicate timers, or stale zero substitution after errors.
- [x] 4.3 Wire each source action through existing workspace navigation to its exact Live Logs destination and preserve the canonical source identity.
- [x] 4.4 Add focused fake-timer and navigation tests for all six destinations, refresh disabled/enabled behavior, cleanup, and accessible source-specific action names.
- [x] 4.5 Run a local browser verification at desktop and narrow widths covering sidebar order, all six entries, populated and never-seen states, loading/error behavior, Live Logs links, keyboard focus, reduced motion, dark theme, contrast, and refresh stability; capture evidence paths in `verification.md`.

## 5. Final Quality Gates and Deployment Handoff — Mac AI

- [x] 5.1 Run the complete focused backend Source Health/events/RBAC regression set and record commands, counts, and results in `verification.md`.
- [x] 5.2 Run focused frontend Source Health/navigation/Dashboard regression tests with `--runInBand --watchAll=false` and record results.
- [x] 5.3 Run the frontend production build and record warnings separately from failures.
- [x] 5.4 Run `git diff --check` and `openspec validate add-source-health-workspace --strict` with passing results.
- [x] 5.5 Review the final diff to confirm no ingestion, parser, detection, correlation, SOAR, pfSense, Dashboard calculation, schema, secret, or production-runtime changes.
- [x] 5.6 Prepare a VM handoff with the approved commit placeholder, expected backend/frontend files, no-migration expectation or reviewed exception, API smoke checks, browser checks, rollback steps, and explicit next owner; do not commit or push without user authorization.

## 6. VM Deployment and Production Verification — VM AI

- [ ] 6.1 After explicit deployment authorization, confirm the VM worktree is clean, fetch without merging, verify the approved commit, and sync only with the source-of-truth policy workflow.
- [ ] 6.2 Run migration dry-run/apply only if Phase 2 produced an explicitly reviewed migration; otherwise record that no migration was required.
- [ ] 6.3 Deploy backend first, verify `/health` and authenticated `/source-health`, then deploy the Mac-built frontend artifact without unrelated service restarts.
- [ ] 6.4 Verify all six production response entries, authoritative sample counts, UTC boundaries, never-seen behavior where applicable, RBAC, Source Health navigation, polling, and all six Live Logs destinations.
- [ ] 6.5 Record deployed commit, service/artifact actions, sanitized results, production evidence, clean-tree post-check, rollback readiness, and unresolved risks without modifying source on the VM.
