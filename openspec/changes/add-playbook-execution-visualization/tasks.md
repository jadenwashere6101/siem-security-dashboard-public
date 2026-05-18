## 1. Frontend Audit and Data Contract

- [x] 1.1 Audit `frontend/src/components/PlaybooksPanel.js` execution detail rendering, selected execution flow, existing controls, and current tests.
- [x] 1.2 Audit `frontend/src/services/playbookService.js` for `listPlaybookExecutions()` and `getPlaybookExecution()` response assumptions.
- [x] 1.3 Inspect existing execution fixtures/tests for `steps_log`, approval, dead-letter, retry, recovery, lease, and notification fields.
- [x] 1.4 Document any tiny read-only field gap discovered during implementation; no backend endpoint was required.

## 2. Timeline Data Normalization

- [x] 2.1 Add pure helpers to parse and normalize `steps_log` from arrays, JSON strings, missing values, and malformed values.
- [x] 2.2 Normalize step names, order, action/adapter labels, status, timestamps, durations, retry counts, approval references, failure class/code, and safe messages.
- [x] 2.3 Derive overall execution summary counts for success, failed, skipped, pending/running, awaiting approval, retries, and unknown steps.
- [x] 2.4 Add defensive sanitization/truncation so raw payloads, provider responses, credentials, webhook URLs, auth headers, SMTP secrets, and tokens are not displayed.
- [x] 2.5 Add safe fallback labels for unknown or unsupported statuses.

## 3. Playbook Execution Timeline Component

- [x] 3.1 Create `frontend/src/components/PlaybookExecutionTimeline.js`.
- [x] 3.2 Add full mode with execution header, status badge, simulation/real badge, flow visualization, timeline list, and summary counts.
- [x] 3.3 Add compact mode for optional cross-context display.
- [x] 3.4 Render pending, running, success, failed, skipped, awaiting approval, and unknown states.
- [x] 3.5 Highlight current step, terminal state, approval pause, retry attempts, recovery/lease markers, and failure details when present.
- [x] 3.6 Add empty, malformed, loading-compatible, and sparse-data states.
- [x] 3.7 Add accessible labels and compact responsive styles for narrow widths.

## 4. PlaybooksPanel Integration

- [x] 4.1 Import and render `PlaybookExecutionTimeline` inside `PlaybooksPanel` execution detail.
- [x] 4.2 Preserve existing execution list, detail fields, and any existing safe controls unchanged.
- [x] 4.3 Ensure visualization uses existing loaded execution detail data before adding any extra read-only fetch.
- [x] 4.4 Ensure no new mutation buttons, retry controls, execution triggers, approval actions, or real integration controls are added.
- [x] 4.5 Keep existing PlaybooksPanel empty/loading/error states intact.

## 5. Optional SOC Command Center Reuse

- [x] 5.1 Evaluate whether existing SOC Command Center execution data is sufficient for compact timeline display.
- [x] 5.2 Compact SOC rendering was skipped because existing Command Center execution list data does not reliably include `steps_log` detail without extra fan-out.
- [x] 5.3 Leave SOC Command Center unchanged and document the reason in implementation notes.

## 6. Tests

- [x] 6.1 Add `frontend/src/components/PlaybookExecutionTimeline.test.js`.
- [x] 6.2 Test success-path timeline rendering.
- [x] 6.3 Test failed step rendering with safe failure class/message display.
- [x] 6.4 Test awaiting-approval rendering and approval pause marker.
- [x] 6.5 Test malformed, empty, missing, and stringified `steps_log` handling.
- [x] 6.6 Test retry count/attempt display when present.
- [x] 6.7 Test lease/recovery marker rendering when relevant fields are present.
- [x] 6.8 Test simulation and real-mode labels.
- [x] 6.9 Update `PlaybooksPanel` tests for visualization integration without changing existing control behavior.
- [x] 6.10 SOC Command Center compact rendering tests were not added because compact reuse was not implemented.

## 7. Verification

- [x] 7.1 Run `CI=true npm test -- --runInBand PlaybookExecutionTimeline`.
- [x] 7.2 Run `CI=true npm test -- --runInBand PlaybooksPanel`.
- [x] 7.3 Run `CI=true npm test -- --runInBand SocCommandCenter`.
- [x] 7.4 Run `npm run build` from `frontend/`.
- [x] 7.5 Run `git diff --check`.
- [x] 7.6 Confirm no backend, schema, VM/runtime, env var, ingest, detection, correlation, execution semantic, mutation-control, or real-integration behavior changed.
