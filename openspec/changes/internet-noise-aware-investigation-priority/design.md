## Context

The current architecture already separates several concerns that matter here:

- detector-authored alert severity;
- stored external reputation snapshots from AbuseIPDB-style lookups;
- current internal behavioral reputation derived from local alert history;
- investigation value derived from recurrence, progression, campaign evidence, corroboration, destination importance, and response history;
- incident policy that already tries to keep some commodity recon visible without automatically opening a case.

That separation is useful, but there is still no first-class model for commodity internet noise. As a result, repeated scanner or crawler IPs can accumulate seriousness through legitimate local recurrence fields even when the stronger story is "globally common background activity with limited local escalation."

The production policy constraint is strict: this change must not suppress detections, must not hide alerts, must not trust GreyNoise or any equivalent source over local evidence, and must not redesign incident lifecycle or SOAR. It is a prioritization refinement only.

## Architecture Findings

1. Existing alert enrichment already has a natural home for a new additive context source. `routes/alerts_events_routes.py` builds alert payloads from stored alert reputation, current behavioral reputation, investigation intelligence, and operational history. Internet-noise intelligence belongs in that same enrichment/projection layer rather than inside detector thresholds.
2. Existing source-IP context is already the cleanest read model for internet-noise explanation. `routes/source_ip_context_routes.py` aggregates alerts, incidents, queue state, blocklist state, behavioral reputation, and external reputation snapshots. A commodity-noise assessment belongs there as a peer to behavioral and external reputation, not as a replacement for either.
3. Existing investigation value is the right policy consumer. `core/investigation_intelligence.py` currently adds points for severity, progression, campaign evidence, recurrence, corroboration, destination importance, response history, repeated destination, and persistence. The missing concept is a bounded negative weighting input that says "this source also matches globally common background activity."
4. Existing incident policy is already selective enough to accept another input. `core/incident_store.py` keeps some scanner and recon activity alert-first. Internet-noise assessment should influence investigation urgency and incident eligibility only after local-evidence checks, not bypass them.
5. Existing AbuseIPDB enrichment is not the right place to encode this policy. AbuseIPDB currently behaves as external threat-intelligence reputation with stored snapshots. Internet-noise classification is a different question from "reported as abusive," so it should remain a separate concept and a separate explanation surface.

## Goals / Non-Goals

**Goals:**

- Add an internet-noise assessment as a distinct, explainable context source.
- Lower investigation urgency for commodity noise when local evidence is weak.
- Preserve or restore urgency when stronger local evidence is present.
- Make deprioritization visible and understandable to analysts.
- Require a production evidence audit before rollout changes incident behavior.

**Non-Goals:**

- No alert suppression.
- No detector rewrites or threshold retuning.
- No automatic incident closure.
- No SOAR, notification, or incident-lifecycle redesign.
- No speculative AI scoring.

## Production Impact Analysis

No live production classification audit was performed from the Mac environment in this authoring step. This workstation has no approved production-database access path in the current task, and no network path to perform recent GreyNoise lookups against production alert IPs.

Because of that, the change cannot truthfully claim last-30-day counts for:

- medium alerts that resolve to benign, malicious, or unknown internet-noise classifications;
- incidents that would remain unchanged, be investigation-lowered, or become non-incidents;
- the exact share of current incident pressure attributable to commodity background activity.

Implementation therefore requires a VM-side production audit before any rollout that changes prioritization or incident policy. The minimum audit should:

1. Extract the last 30 days of candidate source IPs for medium alerts and open/recent incidents, with alert type, severity, source, protected-target context, incident linkage, progression flags, correlation counts, and response history.
2. Classify those IPs through the approved internet-noise provider using bounded, sanitized lookup scripts.
3. Bucket results into `benign`, `malicious`, `unknown`, and `error/unclassified`.
4. Re-run a proposed local-evidence override policy against those rows to estimate:
   - unchanged urgency;
   - lowered investigation urgency;
   - incident suppressed prospectively;
   - still incident-worthy because local evidence overrides commodity classification.
5. Preserve sample evidence for analyst review before implementation proceeds.

## Decisions

### 1. Internet-noise intelligence becomes a separate enrichment object

It should not overwrite `reputation_*`, should not replace `behavioral_reputation`, and should not be folded invisibly into severity. Recommended shape for later implementation:

- `internet_noise_assessment.classification`
- `internet_noise_assessment.name`
- `internet_noise_assessment.explanation`
- `internet_noise_assessment.provider`
- `internet_noise_assessment.observed_globally`
- `internet_noise_assessment.deprioritized`
- `internet_noise_assessment.override_reasons`

Alternative considered: fold GreyNoise into existing `reputation_*`.
Rejected because abuse reputation and commodity-noise reputation answer different questions and would create misleading analyst explanations.

### 2. Internet-noise assessment is a negative weighting signal for investigation value

The cleanest policy insertion point is `build_investigation_value()`. It already models urgency as explainable factors. Additive negative weighting keeps the current architecture intact and avoids detector-level rewrites.

Alternative considered: detector-level severity downgrades.
Rejected because the user goal is not alert suppression or threshold redesign, and severity should remain detector-authored.

### 3. Local evidence always overrides commodity-noise classification

Any of the following must preserve higher urgency regardless of internet-noise classification:

- successful authentication or likely compromise evidence;
- credential stuffing progression;
- exploitation or post-recon progression;
- repeated attacks against protected assets;
- honeypot interaction plus escalation evidence;
- cross-source or cross-surface correlation;
- campaign progression;
- strong local behavioral evidence or repeated corroboration.

Alternative considered: hard benign veto.
Rejected because it would hide legitimate attacks that happen to originate from globally noisy infrastructure.

### 4. Incident policy may consume internet-noise assessment only after evidence gating

The policy should never read as "benign scanner means no incident." The policy should read as "commodity-noise classification lowers investigation urgency unless stronger local evidence overrides it." This keeps incidents prospective and actionability-based.

Alternative considered: restrict internet-noise logic to analyst explanation only.
Rejected because explanation alone would not solve incident inflation or investigation-value inflation.

### 5. Analyst explanation is mandatory

Every lowered-priority outcome needs a visible reason such as:

- `Known benign internet scanner; local evidence currently does not exceed normal background activity.`
- `Known global scanner, but repeated protected-target activity keeps this investigation elevated.`

Alternative considered: hidden weighting only.
Rejected because invisible policy changes undermine analyst trust and make triage harder to audit.

## Recommended Architecture

```text
External internet-noise provider
  -> bounded provider adapter / lookup helper
  -> internet_noise_assessment enrichment object
  -> alert payload + source-IP context projection
  -> investigation value negative weighting
  -> incident policy input after local-evidence override checks
  -> analyst-facing reason strings
```

This keeps the capability additive, traceable, and bounded to existing intelligence/read-model layers.

## Rollout Mode

The first production posture must be explicit shadow mode:

- `INTERNET_NOISE_POLICY_MODE=shadow` is the safe default.
- Shadow mode performs asynchronous lookups, uses cache, exposes the assessment in APIs and UI, and records what would have changed.
- Shadow mode does not lower Investigation Value, does not block incident creation, and does not suppress alerts.
- `INTERNET_NOISE_POLICY_MODE=policy` is an explicit runtime opt-in for future rollout after production audit review.

This preserves the spec requirement that rollout remains blocked until real production evidence exists.

## Async And Cache Reality For V1

The implementation is intentionally narrow and process-local:

- Asynchronous execution is handled by a backend `ThreadPoolExecutor`.
- Lookup jobs do not survive process restart or deployment.
- Cache is in-memory only and keyed by source IP with configurable TTL.
- Completed assessments are available only to later requests served by the same backend process.
- Duplicate in-flight lookups are prevented only within a single process.
- Multiple backend processes do not share cache state or in-flight suppression.
- Process restart or deployment clears cache contents and cancels outstanding in-flight work.
- Expired cache entries become neutral `stale` results until refreshed; failures remain neutral.

This is acceptable for v1 because ingest, detections, alerts, and SOAR remain non-blocking and neutral on failure. It is not durable distributed enrichment, and the implementation must not overstate that.

## Shadow Instrumentation

Shadow rollout must record lightweight evidence without changing analyst-visible severity:

- lookup outcome category counts;
- cache-hit and failure counts;
- alerts that would have been deprioritized in shadow mode;
- incidents that would have been prevented prospectively in shadow mode;
- commodity classifications whose deprioritization was overridden by local evidence.

The v1 metrics are process-local counters, suitable for controlled rollout review but not durable cross-process reporting.

## Analyst Explanation Strategy

- Show internet-noise assessment separately from AbuseIPDB-style external reputation and separately from behavioral reputation.
- Always pair deprioritization with a short reason.
- Always show override reasons when local evidence wins.
- Prefer plain English over jargon such as `benign` with no context.

## Risks / Trade-offs

- **[Commodity label becomes a hidden suppressor]** -> Keep alerts visible, prohibit hard veto logic, and require visible reasons.
- **[Provider confidence is mistaken for local truth]** -> Separate provider classification from local evidence and always allow local override.
- **[Incident pressure changes without proof]** -> Require a VM-side production audit before implementation changes policy.
- **[Another intelligence field confuses analysts]** -> Keep the model separate and named around internet noise, not generic reputation.
- **[Unknown lookups lower urgency incorrectly]** -> Unknown or failed lookups must not lower seriousness by default.

## Implementation Phases

### Phase 1: Architecture and production audit

- Define the provider abstraction, payload shape, and local-evidence override rules.
- Execute the VM-side last-30-day production audit and review sampled cases.

### Phase 2: Additive backend intelligence

- Add internet-noise assessment enrichment and read-model exposure without detector changes.
- Add bounded negative weighting to investigation value with explicit override reasons.

### Phase 3: Incident policy refinement

- Apply the new signal prospectively to incident eligibility and priority reasoning only after local-evidence checks.

### Phase 4: Analyst-facing explanation

- Surface internet-noise assessment and override reasoning in alert, source-IP context, and incident explanations.

## Open Questions

- Which provider field mapping is authoritative for `benign`, `malicious`, and `unknown` in this product language?
- Should lookups be live, cached, or backfilled for recent alert IPs before analyst views?
- Which exact local-evidence combinations are sufficient to override commodity-noise deprioritization without ambiguity?
