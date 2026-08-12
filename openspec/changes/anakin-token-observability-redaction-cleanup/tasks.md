## 1. Sanitizer Correction — Mac AI

- [x] 1.1 Add an exact allowlist for `prompt_tokens` and `completion_tokens` and preserve them only when their values are non-negative integers that are not booleans.
- [x] 1.2 Preserve the existing sensitive-key matcher and recursive fail-closed redaction for credential, secret, and unknown token-bearing fields.

## 2. Focused Regression Coverage — Mac AI

- [x] 2.1 Add direct sanitizer tests for numeric usage counts, known credential tokens, API keys/secrets/passwords, nested values, invalid safe-key values, and unknown token-bearing keys.
- [x] 2.2 Add planner observability persistence coverage for token counts, completion state, stop reason, typed validation metadata, and exclusion of raw prompts, failed plans, reasoning, and secrets.
- [x] 2.3 Confirm existing session-memory depth validation and artifact/session-memory normalization behavior remain unchanged.

## 3. Offline Verification — Mac AI

- [x] 3.1 Run focused sanitizer and planner persistence tests, affected conversation orchestration and artifact regressions, relevant provider/accounting regressions, and the offline AI acceptance harness without real provider traffic.
- [x] 3.2 Run Python compilation, `git diff --check`, strict OpenSpec validation, and review the final diff for narrow scope.

## 4. Production Completion Gate — VM AI After Separate Authorization

- [ ] 4.1 After an authorized commit, push, and deployment, verify the affected deployed browser path and capture the production acceptance fields required by `docs/anakin-production-acceptance-policy.md`. Until then report exactly: `Implementation complete; production behavior unverified.`

Anakin production completion gate:

Before reporting this Anakin change as working, done, fully verified, or production-ready, follow docs/anakin-production-acceptance-policy.md.

Automated tests, OpenSpec validation, frontend build success, service health, direct-backend localhost 200s, and offline acceptance harness success are necessary but not sufficient.

For every affected canonical workflow, verify the deployed browser path:
browser -> /siem/ -> nginx -> frontend -> backend -> worker/Ollama -> frontend-rendered result.

Capture Workflow, Browser-path result, Live API result, Latency, UI-rendered result, Pass/Fail, exact failure root cause, Production mutation performed: Yes/No, and remaining unverified behavior.

Confirm timeout compatibility across nginx, Gunicorn/backend, AI profile/provider, worker/runtime, polling, and terminal-state handling. Confirm the correct assistant/data source handled the request. Confirm safe workflows do not persist, apply, or mutate anything unless explicitly authorized.

Final totals must include Passed, Failed, and Unverified. Only report production-ready when Failed = 0 and Unverified = 0.

If browser-path verification was not performed, say exactly:
Implementation complete; production behavior unverified.
Do not say working, done, fully verified, or production-ready.
