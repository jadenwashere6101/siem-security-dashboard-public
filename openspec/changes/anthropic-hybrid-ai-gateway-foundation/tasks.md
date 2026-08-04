## 1. Phase 1 - Provider Foundation

- [x] 1.1 Add focused contract tests proving a second provider can use the existing `AiProvider` operations and that Ollama behavior remains unchanged.
- [x] 1.2 Implement the Anthropic adapter inside the provider layer with capability validation, bounded generation, normalized response metadata, usage extraction, and redacted error mapping.
- [x] 1.3 Register Anthropic through the existing provider factory/registry without adding a route-, planner-, worker-, or client-owned provider path.
- [x] 1.4 Add environment-only Anthropic credential loading and prove credentials cannot enter runtime payloads, PostgreSQL, API output, logs, or audit details.
- [x] 1.5 Add provider-specific non-generating readiness checks and normalized disabled/configured/unavailable/timeout/incapable/authentication/ready states.
- [x] 1.6 Extend backend and worker startup validation so Phase 1 Anthropic configuration fails closed on missing or invalid credentials, model, timeout, or API version while Ollama-only startup remains valid; pricing and budget validation remain Phase 3 work before paid routing.
- [x] 1.7 Run focused provider, gateway, startup, redaction, and Ollama regression tests before enabling any paid profile.

## 2. Phase 2 - Profile Routing

- [x] 2.1 Extend the backend profile model and validation with trusted provider assignment and paid-fallback eligibility while preserving model, prompt, output, timeout, and temperature controls.
- [x] 2.2 Update the machine-readable inventory so `agentic_planning` maps to Anthropic and `fast_triage`, `guided_analysis`, `deep_briefing`, and `developer_assistant` map explicitly to Ollama.
- [x] 2.3 Change gateway resolution from global local-first order to profile provider/model resolution under the existing four gateway modes.
- [x] 2.4 Reject or ignore all client-supplied provider, model, profile, fallback, timeout, token, cost, and budget controls at backend boundaries.
- [x] 2.5 Route initial planner proposals through `agentic_planning` without changing planner packet construction, semantic ownership, validation, orchestration, evidence, or async boundaries.
- [x] 2.6 Enforce one repair with the same Anthropic provider/model, repair-stable decisions, precise validation feedback, and no Ollama substitution.
- [x] 2.7 Add route, service, worker, and inventory tests covering every profile in every applicable gateway mode and proving Ollama-only workflows never use paid fallback.

## 3. Phase 3 - Cost, Accounting, and Safety

- [x] 3.1 Add an additive PostgreSQL migration/schema definition for shared paid-request accounting and validate forward application without modifying credential storage.
- [x] 3.2 Implement a gateway-owned accounting store/service for provider, model, profile, correlation/repair identity, status, token counts or estimates, cost or estimate, and provider latency.
- [x] 3.3 Implement conservative pre-call cost calculation from validated provider/model pricing, estimated input tokens, and maximum output tokens.
- [x] 3.4 Implement transactional shared budget reservation so concurrent Gunicorn and worker requests can never authorize combined spend above the daily cap.
- [x] 3.5 Reconcile reservations to provider-reported usage and retain the conservative charge when reliable usage is unavailable.
- [x] 3.6 Implement UTC-day lazy rollover on the first budget-controlled request after the date changes, including concurrent first-request coverage and no scheduler dependency.
- [x] 3.7 Fail closed before provider contact when source policy, pricing, accounting, or budget state is invalid or unreadable; use only an explicitly configured Ollama fallback, otherwise return a degraded non-executing outcome.
- [x] 3.8 Independently authorize and account planner repair; return the existing graceful non-executing planner outcome when repair budget is insufficient.
- [x] 3.9 Add unit, PostgreSQL integration, concurrency, timeout, provider-error, UTC rollover, and forced-budget-exhaustion tests that assert no silent cap overrun.

## 4. Phase 4 - Runtime Administration

- [ ] 4.1 Re-audit current `detection_config` and pfSense runtime configuration code immediately before implementation and document the exact store, route, validation, audit, and UI elements to copy.
- [ ] 4.2 Add an additive PostgreSQL migration/schema definition for non-secret gateway runtime policy with `updated_by` and `updated_at`; keep all credentials environment-only.
- [ ] 4.3 Implement source-controlled safe defaults plus a validated durable runtime policy store whose unreadable/invalid state forces effective `local_only` mode, disables paid routing, and falls to `disabled` only when local defaults are invalid.
- [ ] 4.4 Add authenticated read and super-admin-only mutation handling using existing admin blueprint, transaction, error, and RBAC conventions.
- [ ] 4.5 Validate gateway mode, exhaustive profile/provider/model assignments, daily cap, pricing, timeouts, and paid-fallback combinations atomically and reject unknown or credential-like fields.
- [ ] 4.6 Apply valid policy changes to subsequent gateway authorizations without restart and prove a cap/mode reduction cannot be bypassed by stale process-local state.
- [ ] 4.7 Emit existing-format sanitized audit events for successful, invalid, and RBAC-denied mutations with actor, outcome, old/new values, `updated_by`, and `updated_at`.
- [ ] 4.8 Add the minimal super-admin runtime policy UI by copying the chosen existing settings pattern, with validation/error states and no provider choice exposed to analyst workflows.
- [ ] 4.9 Add focused store, route, RBAC, immediate-effect, audit, frontend service/component, dark-theme, accessibility, and production-build coverage.

## 5. Phase 5 - Observability

- [ ] 5.1 Extend `/ai/status` serialization with active mode, secret-free provider readiness, and active provider/model for every profile.
- [ ] 5.2 Add current UTC budget period, cap, used, remaining, and token/cost usage without triggering reset or billable generation; label exact provider-returned values `provider_reported` and every calculated, reserved, or inferred value `estimated`, never actual billed usage.
- [ ] 5.3 Normalize configuration, readiness, budget-blocked, timeout, incapable, and provider failure states across API responses, logs, accounting, and audit events.
- [ ] 5.4 Add automated redaction tests using credential-bearing provider errors, headers, URLs, prompts, and completions and prove none reach status, logs, audit, or frontend state.
- [ ] 5.5 Add status endpoint authentication/RBAC, degraded-state, accounting, and provider-readiness tests while preserving its read-only philosophy.
- [ ] 5.6 Update operator documentation and environment templates with variable names and safe rollout guidance but no secret values.

## 6. Phase 6 - Acceptance and Completion Gates

- [ ] 6.1 Include the reusable Anakin production completion-gate block below verbatim in every implementation and production-acceptance prompt for this change.
- [ ] 6.2 Run focused backend tests, PostgreSQL migration/schema validation, worker tests, frontend tests, the production frontend build, dark-theme/accessibility review, and `git diff --check` on Mac source of truth.
- [ ] 6.3 Run the full relevant AI/Anakin regression matrix for provider routing, all gateway modes, planner validation, one-repair behavior, Ollama-only continuity, hybrid routing, and async lifecycle.
- [ ] 6.4 Force daily budget exhaustion below the next Anthropic authorization and verify no provider call, no cap overrun, no local planner substitution, graceful planner degradation, correct status/audit evidence, and continued Ollama-only workflows.
- [ ] 6.5 Verify shared accounting and lazy UTC rollover under concurrent web/worker requests, including failures with missing usage and unreadable configuration/accounting.
- [ ] 6.6 Run secret scans and observable-output tests proving API keys, authorization material, raw prompts/completions, and sensitive endpoints are absent from source, PostgreSQL, logs, audits, status, and frontend state.
- [ ] 6.7 Run OpenSpec strict validation for this change and preserve evidence for every requirement/scenario before requesting production work.
- [ ] 6.8 After explicit authorization, hand off deployment to VM AI using the documented Gunicorn/systemd path and production-safe shared Flask-Limiter storage; Mac AI SHALL NOT deploy.
- [ ] 6.9 Through `browser -> /siem/ -> nginx -> frontend -> backend -> worker/provider -> frontend-rendered result`, capture the required live API/UI/latency report for every affected Anakin workflow and confirm no unintended mutation.
- [ ] 6.10 Report final Passed, Failed, and Unverified totals; use production-ready language only when Failed and Unverified are both zero, otherwise use the policy-mandated wording.

### Required reusable completion-gate block

```text
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
```
