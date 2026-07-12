## Context

The current pipeline persists a normalized event and uses a hard-coded event-type dispatcher to call synchronous detector functions. Most detectors query the full recent `events` population by event type and group by `source_ip`, while alert inserts receive `source` and `source_type` from the event that happened to trigger evaluation. This permits cross-source threshold contribution and potentially false source attribution. `detection_config.active` is loaded but ignored, and the Detection Rules API/UI treats only parameters as mutable.

Source identity already survives normalization and persistence. The six supported pairs are Honeypot `honeypot/honeypot`, Bank App `bank_app/custom`, pfSense `pfsense/firewall`, NGINX `nginx/web_log`, Azure Application Insights `azure_insights/cloud_api`, and OpenTelemetry `opentelemetry/telemetry`. Existing correlation intentionally uses accurately attributed alerts across sources and must remain separate from base-rule isolation.

An archived Azure identity spec called cross-source Bank App/Azure aggregation intentional. This change deliberately supersedes only that aggregation behavior: both remain supported, but their thresholds and sequences are isolated. Targeted alert-level cross-source correlation remains intact.

## Goals / Non-Goals

**Goals:**

- Make one code-owned contract authoritative for canonical source pairs and all 15 current base detectors.
- Enforce applicability at dispatch and inside every historical SQL/evidence query.
- Enforce active state, preserve global overrides, and guarantee truthful alert attribution.
- Show effective active state and read-only source coverage in the existing super-admin UI/API.
- Preserve correlation, RBAC, auditing, transactional ingestion, SOAR handoff, and duplicate suppression.

**Non-Goals:**

- Per-source parameters, multi-IP/distributed detection, new anomaly rules, noise tuning, MITRE expansion, playbook redesign, plugin discovery, pfSense tuning, or implementation in this change.

## Decisions

### 1. Use exact source pairs and a centralized applicability registry

Add a small backend module (expected `engines/detection_applicability.py`) containing immutable canonical source-pair constants and a mapping from every base `rule_id` to classification and allowed pairs. Helpers will validate registry completeness against `get_detection_rule_defaults()`, answer whether a rule applies, and serialize deterministic display metadata.

Exact pair matching fails closed. The detection layer will not lowercase, alias, or infer values because normalization owns canonicalization and permissive matching would reintroduce attribution ambiguity.

Alternative: scatter source predicates through the dispatcher and SQL. Rejected because API coverage could drift from execution and future rules could omit one enforcement layer.

### 2. Use two enforcement layers

The ingest orchestrator will build explicit detector candidates for the current event and call a shared applicability gate before detector invocation. The gate checks rule existence, effective `active`, and the current exact source pair.

Each detector will also receive the evaluated source pair and include `source = %s AND source_type = %s` in every historical aggregation and representative-evidence query. This second layer is mandatory defense in depth and makes direct detector tests/calls safe.

Alternative: dispatch-only filtering. Rejected because supported sources could still contribute to one another's historical aggregates.

### 3. Scope evaluation to the triggering entity and source pair

Detector SQL will constrain the outer evaluation to the current `source_ip` as well as the current exact source pair instead of scanning and returning every qualifying IP in the global window. This directly ties any created alert to the triggering entity and evidence source. Existing aggregation dimensions, thresholds, windows, severities, response selection, and duplicate-open-alert semantics remain unchanged.

For `successful_login_after_spray`, both success and failed-login sides of the temporal join use the same source pair and source IP. Location/evidence lookups use the same constraints.

Alternative: continue global scans but select source columns from each aggregate. Rejected because one ingest could still generate unrelated historical alerts and increases query cost and attribution complexity.

### 4. Keep source applicability static and parameters global

Applicability is versioned code metadata, returned by the API but not stored in `detection_config`. Existing JSON parameter overrides remain global per rule and apply independently to each allowed source pair.

No schema migration is required: `events`, `alerts`, and `detection_config` already contain the necessary fields. Existing rows are not rewritten or reclassified.

Alternative: store applicability in `detection_config`. Rejected because the requested scope excludes per-source configuration and mutable coverage could silently broaden detection trust boundaries.

### 5. Make active state a normal audited configuration field

The PATCH contract will accept `parameters`, `active`, or both, require at least one supported mutable field, preserve omitted effective values, validate a strict boolean, and upsert both JSON parameters and active state. Audit details include old/new active state and parameter changes. Existing super-admin guards remain.

Every detector gate reads the effective rule once per candidate and returns before detector SQL when inactive. Configuration lookup failures retain the current fail-to-default behavior, which means code defaults remain active unless a valid stored override says otherwise.

Alternative: check active independently inside all 15 detector functions. Rejected as the sole mechanism because it duplicates policy, though detector entry points should still fail closed when called directly through a shared wrapper/helper.

### 6. Preserve correlation as a separate applicability domain

The base applicability registry does not register `correlated_activity` or the three targeted correlation alerts. Correlation continues after base alert creation and intentionally reads multiple source values. More truthful base alerts improve its inputs without changing its matching rules.

Regression tests will prove generic correlation, all three targeted patterns, evaluation order, and duplicate suppression remain unchanged.

### 7. Keep UI changes minimal

The existing Detection Rules cards will add an accessible active control/status and a compact list of applicable source labels. The service sends active state with parameter changes. Coverage is display-only and sourced from the API; the UI will not duplicate the backend matrix.

Focused component/service tests, production build, keyboard review, semantic labeling, contrast/dark-theme review, and practical visual verification are required.

## Proposed applicability matrix

| Rule | Classification | Supported pairs |
|---|---|---|
| Failed login | canonical | Bank App, Azure, NGINX, OpenTelemetry |
| Generic port scan | canonical legacy/custom | Bank App |
| Password spraying | canonical | Bank App, Azure |
| HTTP error | canonical | Honeypot, NGINX, Azure, OpenTelemetry |
| Application exception | canonical | Azure, OpenTelemetry |
| High request rate | partially source-aware → explicit | NGINX, OpenTelemetry |
| Success after spray | canonical sequence | Bank App, Azure |
| Four honeypot rules | source-specific | Honeypot only |
| Four pfSense rules | source-specific | pfSense only |

Exact pair values and the rule-by-rule expansion are normative in the capability spec.

## Risks / Trade-offs

- [Previously mixed counters stop reaching thresholds] → Treat this as the intended correctness change; add split-source negative tests and per-supported-source positive tests.
- [Archived Azure expectations conflict] → Document that both Azure and Bank App remain supported but no longer share raw-event counters; preserve Azure-only spray/success behavior.
- [Dispatcher and SQL registry drift] → Add completeness tests comparing defaults, dispatch candidates, and applicability entries.
- [A query misses a source predicate] → Review every aggregation, temporal join, location lookup, and representative-row query; add adversarial same-IP cross-source fixtures.
- [Inactive state changes operational coverage] → Make status prominent, changes super-admin-only and audited, and add re-enable tests retaining parameters.
- [Existing historical events affect post-deployment detection] → Source filters apply immediately without rewriting data; only matching canonical history contributes.
- [More accurate attribution changes correlation volume] → Preserve correlation code and verify positive/negative regression scenarios from independently attributed alerts.
- [UI implies per-source tuning] → Label coverage as read-only “Applicable sources” and keep one global parameter form.

## Migration Plan

1. **Mac AI:** implement constants/registry, gates, source-constrained detector queries, active mutation/API metadata, UI, and tests.
2. **Mac AI:** run focused backend/API/correlation tests, full affected regression, schema snapshot/migration validation confirming no migration, frontend tests/build, accessibility/dark-theme/visual checks, `git diff --check`, and strict OpenSpec validation.
3. Obtain explicit authorization before commit or push.
4. **VM AI:** after an explicitly approved commit, perform the clean-tree preflight and approved sync, restart only affected backend services, deploy the Mac-built frontend artifact, and run sanitized source-isolation/active/correlation smoke tests.
5. Rollback is application-version rollback to the prior approved commit. No database down-migration or data rollback is expected because no schema/data migration is planned; any active-state changes made during authorized smoke testing must be restored and audited.

## Open Questions

None. The applicability matrix, configuration ownership, API mutability, correlation boundary, and no-migration expectation are fixed by this design.
