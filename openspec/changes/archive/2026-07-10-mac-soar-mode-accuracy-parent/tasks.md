## 1. Contract and Regression Baseline

- [x] 1.1 Inventory execution payload fields and all Playbooks/timeline consumers of `mode`, `execution_mode`, `executed`, and action outcome metadata
- [x] 1.2 Add failing table-driven tests for real, simulation, read-only, unknown, paused, resumed, failed, retry, and resume presentation states
- [x] 1.3 Add regression tests for Teams conditional wording and for the simulation-only admin queue control remaining accurately labeled

## 2. Frontend Mode Accuracy

- [x] 2.1 Implement or reuse a canonical execution-mode normalization helper with conservative unknown handling
- [x] 2.2 Replace hardcoded simulation status summaries in `PlaybooksPanel.js` with normalized mode-aware or neutral execution copy
- [x] 2.3 Correct the approval-paused banner, panel subtitle/help text, and Retry/Resume labels in `PlaybooksPanel.js`
- [x] 2.4 Correct `approval_resumed` and related timeline event copy in `PlaybookExecutionTimeline.js`
- [x] 2.5 Align the Teams description in `IntegrationStatusPanel.js` with the “when real mode is enabled” qualifier without changing enablement behavior
- [x] 2.6 Run focused frontend tests and review rendered combinations for contradictions between copy and badges

## 3. Backend Outcome Accuracy

- [x] 3.1 Identify producers and consumers of `enrich_context` simulation/no-execution metadata and document compatibility constraints
- [x] 3.2 Add failing backend tests that require successful enrichment to be represented as executed read-only work with no external side effect
- [x] 3.3 Implement the metadata correction without changing enrichment data access or enabling external mutations
- [x] 3.4 Update frontend compatibility handling and metrics/tests so historical records remain conservatively truthful

## 4. Worker Configuration Hardening

- [x] 4.1 Reproduce the response-worker shell-sourcing failure with synthetic secrets containing quotes, spaces, `$`, `#`, and command metacharacters
- [x] 4.2 Reproduce and explain the source-controlled unit/wrapper precedence that defeats explicit safety overrides
- [x] 4.3 Select and document one authoritative precedence model and kill-switch layer for backend and SOAR workers
- [x] 4.4 Update launch wrappers and/or systemd unit templates so environment values are treated as data and the kill-switch wins deterministically
- [x] 4.5 Replace inaccurate “simulation-safe” service descriptions or make that guarantee true and testable
- [x] 4.6 Add automated tests for secret fidelity, non-execution of shell syntax, explicit override precedence, and default simulation-only boundaries

## 5. Verification and VM Handoff

- [x] 5.1 Run focused frontend and backend test suites plus configuration/unit validation and resolve all regressions
- [x] 5.2 Confirm no change enables Teams, firewall/block_ip, monitor, or flag_high_priority real execution and no UI claims firewall enforcement
- [x] 5.3 Write a deployment checklist covering clean-VM verification, changed artifacts, daemon reload, restarts, sanitized effective-environment checks, health checks, and rollback
- [x] 5.4 Hand the approved source changes and acceptance criteria to the VM parent; do not edit VM source or deploy before commit/push authorization
- [x] 5.5 Record final file/test evidence and leave commit, push, and deployment actions unperformed unless separately requested
