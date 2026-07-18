## 1. Provider-Neutral Internet-Noise Service

- [x] 1.1 Add a provider-neutral `internet_noise_assessment` model with `provider`, `assessment`, `explanation`, `confidence`, `last_checked`, `cached`, `lookup_status`, and `provider_metadata`.
- [x] 1.2 Implement the first provider adapter for GreyNoise without coupling investigation logic or API contracts directly to GreyNoise-specific fields.
- [x] 1.3 Keep unknown, timeout, provider-unavailable, failure, and expired-cache cases neutral by default, including neutral `stale` handling for expired cached results.
- [x] 1.4 Add low-retry, backoff-aware, duplicate-suppressed cached lookup behavior with approximately 24-hour configurable TTL.

## 2. Rollout And Policy Gating

- [x] 2.1 Add explicit `INTERNET_NOISE_POLICY_MODE` handling with a safe default of `shadow`.
- [x] 2.2 Keep shadow mode lookup-active and analyst-visible while preventing Investigation Value or incident-policy changes by default.
- [x] 2.3 Allow `policy` mode to apply the already-designed negative weighting and prospective incident influence only after explicit runtime opt-in.
- [x] 2.4 Keep missing provider configuration or lookup failure neutral in both shadow and policy modes.

## 3. Investigation And Incident Policy

- [x] 3.1 Apply internet-noise-aware negative weighting only when policy mode is explicitly enabled, without changing severity, detector output, or alert history.
- [x] 3.2 Define and implement explicit local-evidence override rules for progression, corroboration, protected-target repetition, successful-attack evidence, and campaign intelligence.
- [x] 3.3 Keep malicious internet-noise results non-suppressive and prevent them from becoming the sole reason for escalation.
- [x] 3.4 Allow prospective incident policy to consume cached internet-noise context only after local-evidence override checks, with shadow-mode what-if recording but no enforcement.

## 4. Analyst-Facing Read Models

- [x] 4.1 Expose a separate Internet Noise section on alert payloads without changing AbuseIPDB or behavioral reputation contracts.
- [x] 4.2 Expose a separate Internet Noise section on source-IP context without conflating it with behavioral or stored external reputation.
- [x] 4.3 Add a compact visible Internet Noise section to Alert Details showing assessment, provider, prioritization effect, concise explanation, and override state when meaningful.
- [x] 4.4 Add a compact visible Internet Noise section to Source-IP Context showing assessment, provider, prioritization effect, concise explanation, and lookup status when meaningful.

## 5. Async, Cache, And Shadow Instrumentation

- [x] 5.1 Keep internet-noise execution asynchronous and non-blocking for ingest, detections, alert creation, and SOAR.
- [x] 5.2 Document and preserve v1 process-local behavior for executor lifecycle, restart behavior, in-memory cache scope, and multi-process limitations without overstating durability.
- [x] 5.3 Track lookup successes, commodity results, malicious results, neutral results, cache hits, and lookup failures.
- [x] 5.4 Track shadow-mode alerts that would have been deprioritized, shadow-mode incidents that would have been prevented prospectively, and commodity classifications overridden by local evidence.

## 6. Verification

- [x] 6.1 Add focused tests for cache hit, expiration, retry/backoff, provider timeout, provider-unavailable neutral handling, and shadow-mode default behavior.
- [x] 6.2 Add focused tests for shadow-mode no-op investigation scoring, policy-mode investigation lowering, malicious staying non-lowering, and strong local-evidence override behavior.
- [x] 6.3 Add focused alert payload and source-IP context API contract tests for separate internet-noise state and shadow-mode fields.
- [x] 6.4 Add focused incident-policy tests proving shadow mode is neutral by default while explicit policy mode can keep commodity noise alert-only prospectively.
- [x] 6.5 Add focused frontend tests for Alert Details and Source-IP Context Internet Noise rendering.
- [x] 6.6 Run `python3 -m py_compile` on changed backend and test files.
- [x] 6.7 Run focused backend, enrichment, investigation, incident-policy, and relevant API contract tests.
- [x] 6.8 Run focused frontend Internet Noise tests for Alert Details and Source-IP Context.
- [x] 6.9 Run `npm run build`.
- [x] 6.10 Run `openspec validate internet-noise-aware-investigation-priority --strict`.
- [x] 6.11 Run `git diff --check`.
