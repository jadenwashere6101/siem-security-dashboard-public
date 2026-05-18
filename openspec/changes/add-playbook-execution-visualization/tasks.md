## 1. Frontend Audit and Data Contract

- [ ] 1.1 Audit `frontend/src/components/PlaybooksPanel.js` execution detail rendering, selected execution flow, existing controls, and current tests.
- [ ] 1.2 Audit `frontend/src/services/playbookService.js` for `listPlaybookExecutions()` and `getPlaybookExecution()` response assumptions.
- [ ] 1.3 Inspect existing execution fixtures/tests for `steps_log`, approval, dead-letter, retry, recovery, lease, and notification fields.
- [ ] 1.4 Document any tiny read-only field gap discovered during implementation; do not add backend endpoints unless the visualization cannot render safely without it.

## 2. Timeline Data Normalization

- [ ] 2.1 Add pure helpers to parse and normalize `steps_log` from arrays, JSON strings, missing values, and malformed values.
- [ ] 2.2 Normalize step names, order, action/adapter labels, status, timestamps, durations, retry counts, approval references, failure class/code, and safe messages.
- [ ] 2.3 Derive overall execution summary counts for success, failed, skipped, pending/running, awaiting approval, retries, and unknown steps.
- [ ] 2.4 Add defensive sanitization/truncation so raw payloads, provider responses, credentials, webhook URLs, auth headers, SMTP secrets, and tokens are not displayed.
- [ ] 2.5 Add safe fallback labels for unknown or unsupported statuses.

## 3. Playbook Execution Timeline Component

- [ ] 3.1 Create `frontend/src/components/PlaybookExecutionTimeline.js`.
- [ ] 3.2 Add full mode with execution header, status badge, simulation/real badge, flow visualization, timeline list, and summary counts.
- [ ] 3.3 Add compact mode for optional cross-context display.
- [ ] 3.4 Render pending, running, success, failed, skipped, awaiting approval, and unknown states.
- [ ] 3.5 Highlight current step, terminal state, approval pause, retry attempts, recovery/lease markers, and failure details when present.
- [ ] 3.6 Add empty, malformed, loading-compatible, and sparse-data states.
- [ ] 3.7 Add accessible labels and compact responsive styles for narrow widths.

## 4. PlaybooksPanel Integration

- [ ] 4.1 Import and render `PlaybookExecutionTimeline` inside `PlaybooksPanel` execution detail.
- [ ] 4.2 Preserve existing execution list, detail fields, and any existing safe controls unchanged.
- [ ] 4.3 Ensure visualization uses existing loaded execution detail data before adding any extra read-only fetch.
- [ ] 4.4 Ensure no new mutation buttons, retry controls, execution triggers, approval actions, or real integration controls are added.
- [ ] 4.5 Keep existing PlaybooksPanel empty/loading/error states intact.

## 5. Optional SOC Command Center Reuse

- [ ] 5.1 Evaluate whether existing SOC Command Center execution data is sufficient for compact timeline display.
- [ ] 5.2 If feasible without backend scope, render compact execution summary/timeline for selected or recent execution context.
- [ ] 5.3 If not feasible, leave SOC Command Center unchanged and document the reason in implementation notes.

## 6. Tests

- [ ] 6.1 Add `frontend/src/components/PlaybookExecutionTimeline.test.js`.
- [ ] 6.2 Test success-path timeline rendering.
- [ ] 6.3 Test failed step rendering with safe failure class/message display.
- [ ] 6.4 Test awaiting-approval rendering and approval pause marker.
- [ ] 6.5 Test malformed, empty, missing, and stringified `steps_log` handling.
- [ ] 6.6 Test retry count/attempt display when present.
- [ ] 6.7 Test lease/recovery marker rendering when relevant fields are present.
- [ ] 6.8 Test simulation and real-mode labels.
- [ ] 6.9 Update `PlaybooksPanel` tests for visualization integration without changing existing control behavior.
- [ ] 6.10 Add SOC Command Center compact rendering tests only if compact reuse is implemented.

## 7. Verification

- [ ] 7.1 Run `CI=true npm test -- --runInBand PlaybookExecutionTimeline`.
- [ ] 7.2 Run `CI=true npm test -- --runInBand PlaybooksPanel`.
- [ ] 7.3 If SOC Command Center is touched, run `CI=true npm test -- --runInBand SocCommandCenter`.
- [ ] 7.4 Run `npm run build` from `frontend/`.
- [ ] 7.5 Run `git diff --check`.
- [ ] 7.6 Confirm no backend, schema, VM/runtime, env var, ingest, detection, correlation, execution semantic, mutation-control, or real-integration behavior changed.
