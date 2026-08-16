## 1. Schema and Persisted NIST Reads

- [x] 1.1 Add migration `0038` extending only the `ai_workflow_requests.workflow` constraint for `nist_evidence_explanation` and update `schema.sql`.
- [x] 1.2 Add bounded keyset run-history persistence and Analyst+ route behavior using the existing run index.
- [x] 1.3 Add exact run/requirement-result lookup and make evidence ownership mismatches return 404.
- [x] 1.4 Add migration, schema snapshot, run-history bounds/order, cursor validation, RBAC, and evidence-ownership tests.

## 2. Isolated Explanation Submission

- [x] 2.1 Add strict ID-only request validation for four NIST IDs plus UUID client request ID and reject unknown authority/context fields.
- [x] 2.2 Implement authoritative four-ID binding and capped persisted evidence-context helpers with total/supplied/omitted/truncation metadata.
- [x] 2.3 Add the Analyst+ enqueue route using existing idempotent workflow-request persistence and safe queued/duplicate/rejected audits.
- [x] 2.4 Register the isolated async workflow in existing store/worker constraints without adding planner, conversation, tool, collector, source-health, or events dependencies.

## 3. Grounded Worker Synthesis

- [x] 3.1 Implement worker-side four-ID revalidation and direct isolated dispatch that bypasses generic workflow and session-memory preparation.
- [x] 3.2 Build a bounded server-owned prompt and invoke only the existing local `fast_triage` text-generation profile through `AiGateway`.
- [x] 3.3 Parse and strictly validate the five-field explanation schema, citation subset, identities, deterministic state, overclaim language, confidence/truncation limits, and operational classification.
- [x] 3.4 Discard all prose on provider, parse, schema, citation, contradiction, or overclaim failure and return a safe deterministic `explanation_unavailable` envelope without repair.
- [x] 3.5 Add safe completed/rejected/unavailable/failed worker audits containing only identifiers and bounded provider/reference metadata.
- [x] 3.6 Add backend tests for binding, context caps, citations, malformed/contradictory/overclaim output, provider failures, idempotency, owner polling, redaction, metadata, isolation, and unchanged deterministic NIST rows.

## 4. NIST Analyst Workspace

- [x] 4.1 Add the Analyst+ NIST SOC navigation section and state/history integration without adding a router or global store.
- [x] 4.2 Add a validated NIST frontend service for boundaries, run history, run/results/evidence, boundary mutations, explicit runs, exports, explanation enqueue, and owner polling.
- [x] 4.3 Implement the permanent disclaimer, boundary selector/details, super-admin create/edit flow, bounded run history, run summary, exports, and explicit super-admin assessment control.
- [x] 4.4 Implement the 12-result master/detail workspace with separate safe mapping/evidence/confidence terminology, reason, limitation, counts, loading/error/empty/refresh states, and no automatic run.
- [x] 4.5 Implement paginated safe evidence provenance and allowlisted existing navigation for alert, incident, approval request, and playbook execution only.
- [x] 4.6 Implement async explanation queued/running/success/unavailable rendering while preserving deterministic evidence and discarding stale four-ID responses.
- [x] 4.7 Add focused frontend tests for data states, role controls, exact terminology, pagination/navigation, polling/failures/stale responses, accessibility, focus, and responsive behavior.

## 5. Verification and Handoff

- [x] 5.1 Run focused NIST, async worker, fast-triage gateway, RBAC/audit, migration/schema, and PostgreSQL-backed backend tests without provider calls.
- [ ] 5.2 Run focused and full frontend suites, production build, accessibility/dark-theme review, and practical local visual verification.
- [x] 5.3 Run affected backend regressions, Python compilation, schema validation, migration lint/tests, `git diff --check`, and strict validation of this and related NIST OpenSpecs.
- [x] 5.4 Review the final diff for forbidden architecture dependencies and document exact separately authorized VM migration/backend/worker/frontend/browser-path verification.
- [ ] 5.5 After separately authorized deployment, complete the Anakin production completion gate below through the real browser path. This task remains pending during Mac-only implementation.

Anakin production completion gate:

Before reporting this Anakin change as working, done, fully verified, or production-ready, follow `docs/anakin-production-acceptance-policy.md`.

Automated tests, OpenSpec validation, frontend build success, service health, direct-backend localhost 200s, and offline acceptance harness success are necessary but not sufficient.

For every affected canonical workflow, verify the deployed browser path:
`browser -> /siem/ -> nginx -> frontend -> backend -> worker/Ollama -> frontend-rendered result`.

Capture Workflow, Browser-path result, Live API result, Latency, UI-rendered result, Pass/Fail, exact failure root cause, Production mutation performed: Yes/No, and remaining unverified behavior.

Confirm timeout compatibility across nginx, Gunicorn/backend, AI profile/provider, worker/runtime, polling, and terminal-state handling. Confirm the correct assistant/data source handled the request. Confirm safe workflows do not persist, apply, or mutate anything unless explicitly authorized.

Final totals must include Passed, Failed, and Unverified. Only report production-ready when Failed = 0 and Unverified = 0.

If browser-path verification was not performed, say exactly:
`Implementation complete; production behavior unverified.`
Do not say working, done, fully verified, or production-ready.
