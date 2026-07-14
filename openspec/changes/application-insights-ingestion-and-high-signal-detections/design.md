## Context

Read: `AGENTS.md`, `docs/mac-vm-source-of-truth-policy.md`, `docs/azure-integration-setup.md`, `siem-azure-function/function_app.py`, `adapters/azure_insights_adapter.py`, `routes/ingest_routes.py` (`/ingest/azure`), `engines/detection_applicability.py`, `engines/detection_config.py` (rule defaults, `get_effective_detection_rule`, `detection_config` table), `engines/correlation_engine.py`, `core/incident_store.py`, `core/notification_policy_service.py`, `core/source_health.py`, `core/source_inventory.py`, `routes/admin_routes.py` (`/admin/detection-rules/*`), `frontend/src/utils/sourceMetadata.js`, and the unarchived `critical-response-consistency-and-severity-matrix` change (severity philosophy, matrix contract, incident-escalation and notification-routing decisions this change must stay consistent with). `helpers/ingest_normalizers.py` (`_is_azure_identity_payload`, app-name helpers). No dedicated Azure test module exists (`tests/test_*azure*`); Azure paths are currently covered indirectly through `tests/test_ingest_api_contracts.py`, `tests/test_ingest_normalized_event.py`, `tests/test_source_aware_detection.py`, `tests/test_targeted_correlation.py`, and `tests/test_source_health.py`.

### 1–13: Audit findings

1. **Application Insights ingestion already partially exists — it is a working demo path, not a production one.** `siem-azure-function/function_app.py` runs a timer trigger every 5 minutes (`schedule="0 */5 * * * *"`), queries a Log Analytics workspace with a KQL query unioning `AppExceptions`, `AppRequests`, and `AppTraces` over a fixed `ago(5m)` window, classifies rows client-side, and POSTs each mapped row to `SIEM_AZURE_INGEST_URL` (`/ingest/azure`) with a shared `X-API-Key`. The backend (`routes/ingest_routes.py:548`, `adapters/azure_insights_adapter.py`) independently re-normalizes the same payload and inserts into `events`, then runs it through the standard detection pipeline (`ingest_normalized_event` → `_create_playbook_executions_for_alerts` → `_create_incidents_for_alerts`, the correct single-call ordering already, unlike the bug fixed for other routes in `critical-response-consistency-and-severity-matrix`).
2. **KQL queries that already exist**: the `APP_INSIGHTS_QUERY` in `function_app.py` covers `AppExceptions` (all rows), `AppRequests` (only rows with non-empty `ClientIP`), and `AppTraces` (only rows whose `Message` contains the literal string `"HTTP request received"` — which is the exact string the Function's own `test_endpoint` handler logs; this is a demo self-reference, not a real telemetry pattern). No `AppDependencies` or `AppAvailabilityResults` query exists, despite `adapters/azure_insights_adapter.py::normalize_azure_insights_telemetry` already having a dedicated `availability_failure` branch and a generic `request`/`dependency` branch ready to receive them.
3. **Authentication mechanism that already exists**: `DefaultAzureCredential` (`azure.identity`) against `LogsQueryClient` (`azure.monitor.query`) for the KQL side — resolves to managed identity in Azure, developer credentials locally; no secret management needed on that leg. The SIEM-facing leg uses a shared static secret, `AZURE_INGEST_API_KEY`, validated by `require_azure_api_key()`, matching the pattern used for every other ingest route's API key guard. Both mechanisms are sound and reused as-is by this change.
4. **Polling vs. push**: polling is already chosen and is appropriate — Application Insights/Log Analytics does not offer a low-latency push mechanism suitable for this architecture (Event Hubs streaming export exists but is a materially larger integration than this change's scope), and a 5-minute-cadence timer is consistent with the platform's existing correlation windows (10–15 minutes). This change keeps polling but makes it checkpoint-driven instead of fixed-window.
5. **Adapter placement**: ingestion belongs beside the existing adapters, not as a parallel system — `adapters/azure_insights_adapter.py` and `POST /ingest/azure` already exist and are the correct integration point; this change extends that adapter and endpoint rather than introducing a second Azure-specific pipeline.
6. **Checkpoints/bookmarks — do not currently exist.** The Function's only "memory" between runs is the fixed `ago(5m)` KQL window matched to the 5-minute timer cadence. If a run is delayed, fails, or is skipped (cold start, transient Log Analytics error, Function host restart), any telemetry generated in the gap between the last successful run and `now - 5m` is never queried again — permanent, silent data loss. There is also no dedup: if two runs' windows ever overlap (e.g., a delayed run followed by an on-time run), the same row could theoretically be forwarded twice, and neither the Function nor the backend adapter has an idempotency key for Azure-sourced events.
7. **Application Insights vs. generic Azure Monitor**: this change stays scoped to Application Insights tables (`AppExceptions`, `AppRequests`, `AppDependencies`, `AppAvailabilityResults`) plus the existing Entra ID identity path — not generic Azure Monitor/Activity Log ingestion, which is a different telemetry domain (control-plane/resource events, not application telemetry) and out of scope here.
8. **Expected event volume**: currently capped at `MAX_RECORDS = 25` per 5-minute poll (≈300/hour ceiling today, an artificial demo limit, not a real signal about production volume). A moderately active instrumented application can produce far more — hundreds of requests and a handful to dozens of exceptions per minute during normal operation, spiking sharply during an incident (the exact moment detection quality matters most). The current hard cap silently truncates exactly the bursts detections need to see.
9. **Expected operational cost**: Log Analytics KQL queries against Application Insights tables are billed per GB of data scanned (consumption-tier pricing) plus the Function App's own consumption/execution cost for a lightweight 5-minute timer. Cost scales with query frequency × data scanned per query, not with events forwarded — an unbounded `take` removal without checkpointing would not by itself increase cost, but re-scanning already-processed windows (as a checkpoint failure-safe fallback might, see below) does. This change's checkpoint-driven design queries only the checkpoint-to-now range each run, keeping scanned volume proportional to actual new telemetry rather than a fixed window.
10. **Required runtime configuration**: see the dedicated section below — the answer is "less than it might seem," per the explicit instruction not to over-configure.
11. **Failure/retry behavior — does not currently exist.** `_query_recent_telemetry()` and `forward_telemetry_to_siem()` each run once per row/poll with no retry; a transient KQL or HTTP failure for one row is logged and skipped (`failures` counter), and a KQL query failure aborts the entire poll (bare `except Exception: return`), losing the whole window with no retry and no checkpoint to recover from later. This is the same root problem as finding 6, compounded by no retry.
12. **Health monitoring**: `core/source_health.py` + `core/source_inventory.CANONICAL_SOURCES` already track `azure_insights` generically via last-event-arrival timestamps (the existing Source Health workspace already reflects this). What does **not** exist is any visibility into *why* Azure telemetry stopped arriving — a silent poll failure (finding 11) and "the application genuinely produced no telemetry" look identical from the SIEM's side today. This change closes that gap with a small poll-outcome record (see Decisions), without duplicating Source Health's existing event-arrival view.
13. **Existing reusable infrastructure** (all confirmed by reading the code, all reused rather than duplicated by this change): `adapters/azure_insights_adapter.py` and `POST /ingest/azure`; `engines/detection_applicability.py`'s `AZURE_INSIGHTS` canonical source identity and `RULE_APPLICABILITY` registry; `engines/detection_config.py` + the `detection_config` DB table + `/admin/detection-rules/<rule_id>` (the real Runtime Configurables system — per-rule JSON parameter overrides merged over code defaults, audited via `detection_rule_updated`); `engines/correlation_engine.py`'s `cloud_app_error_pattern` rule (already correlates `azure_insights` `http_error`/`application_exception` with `nginx` `http_error`/`high_request_rate` at High); `core/source_health.py` + `core/source_inventory.py`; `core/incident_store.maybe_create_or_link_incident` and the incident-escalation behavior from `critical-response-consistency-and-severity-matrix`; `core/notification_policy_service.py` (once that change's `critical_cross_source` route ships, any Critical-adjacent Application Insights alert routes through it automatically — no new routing work needed here); `frontend/src/utils/sourceMetadata.js` already has an `azure_insights` entry (`displayLabel: "Azure Application Insights"`, Live Logs destination) for any future UI work.

### Architecture: current state vs. this change

```
Current (demo-grade):

  App Insights (Log Analytics)
        │  KQL: ago(5m) window, take 25, no dependencies/availability
        ▼
  Azure Function timer (every 5m)
        │  classify 401/403 as "unauthorized_access" (client-side only)
        │  no retry, no checkpoint
        ▼
  POST /ingest/azure  ──►  azure_insights_adapter
                              │  re-derives event_type from raw payload shape
                              │  "unauthorized_access" not recognized ──► normal_activity (low)  <-- drift bug
                              ▼
                           events table ──► detection_engine / correlation_engine
                                              (application_exception_threshold, http_error_threshold,
                                               failed_login_threshold, password_spraying_threshold,
                                               successful_login_after_spray, cloud_app_error_pattern)

This change (reliable + high-signal):

  App Insights (Log Analytics)
        │  KQL: checkpoint-to-now window, paged, + AppDependencies + AppAvailabilityResults
        │  (AppTraces demo query removed)
        ▼
  Azure Function timer (every 5m, unchanged cadence)
        │  bounded retry+backoff on query and forward
        │  reads/writes checkpoint via SIEM checkpoint API
        │  reports poll outcome (success/failure, counts) via same API
        ▼
  POST /ingest/azure  ──►  azure_insights_adapter (401/403 recognized consistently as auth-abuse)
                              ▼
                           events table ──► detection_engine / correlation_engine
                                              existing rules (unchanged) +
                                              NEW: app_insights_unauthorized_access_threshold
                                              NEW: azure_auth_abuse_exception_correlation
                                                     │
                                                     ▼ (if successful_login_after_spray already open for IP)
                                              links to existing incident, no second Critical path
                                                     │
                                                     ▼
                     ingestion_checkpoints table ──► Source Health (poll-health surfaced alongside
                                                       existing event-arrival staleness)
```

## Goals / Non-Goals

**Goals:**
- Make Application Insights ingestion durable: no silent data loss from missed polls, volume spikes, or transient failures.
- Fix the authentication-abuse classification drift so 401/403 application-tier signals are actually visible to detections.
- Add exactly the telemetry coverage that improves detection quality (`AppDependencies` failures, `AppAvailabilityResults` failures) and nothing that doesn't (no custom events/metrics, no broad trace ingestion).
- Add detections that indicate attack progression (auth abuse correlated with app instability), not isolated exceptions — Critical requires corroborated evidence, consistent with the platform-wide Critical philosophy from `critical-response-consistency-and-severity-matrix`.
- Give the SIEM visibility into *why* Azure telemetry might be missing (poll failure vs. no telemetry), reusing Source Health rather than building a parallel health surface.
- Keep runtime configuration minimal and consistent with the existing `detection_config`/Runtime Configurables pattern.

**Non-Goals:**
- Not "collect everything" — no custom events, no custom metrics, no general-purpose trace ingestion, no generic Azure Monitor/Activity Log ingestion.
- No new UI in this change (recommendations only, see the UI section).
- No auto-containment, no new approval-flow changes — new alerts flow through the existing playbook/incident/notification machinery unchanged.
- No push/Event Hubs streaming ingestion — polling remains the model.
- No change to the existing Entra ID identity ingestion path (`normalize_azure_identity_telemetry`), which already works correctly and is out of scope.
- No isolated-exception-triggered Critical severity, ever.

## Telemetry inventory

| Telemetry type | Currently ingested? | Usefulness | Expected noise | Ingest in this change? | Recommended severity ceiling | Correlation opportunity |
|---|---|---|---|---|---|---|
| Exceptions (`AppExceptions`) | Yes, flat `high` per row | High *when correlated*; low standalone | High volume in unstable apps | Keep, but stop treating as inherently High in isolation — severity comes from the threshold/correlation rule, not the raw event | High via `cloud_app_error_pattern`; High via new auth-abuse correlation; never Critical alone | Correlate spikes with recent auth-abuse/spray from the same IP (new rule below) |
| Failed requests, 5xx (`AppRequests`) | Yes (`http_error_threshold`) | Medium — could be attacker probing or an unrelated bug | Medium–high | Keep, unchanged | High via `cloud_app_error_pattern` | Already correlates with `nginx` |
| Slow requests / duration (`AppRequests`) | No | Low standalone; only meaningful as a resource-exhaustion signal | High if naively thresholded | **Not in this change** — defer; would need correlation with `high_request_rate_threshold` from the same IP to mean anything security-relevant | Medium, deferred | Potential future correlation with `high_request_rate_threshold`/pfSense flood signals |
| Dependencies (`AppDependencies`) | No (backend adapter is ready, KQL is not) | High — dependency *failures* and anomalous outbound targets can reflect exploitation side-effects (e.g., unexpected outbound calls, DB call failures consistent with injection attempts) | Medium if scoped to failures only; high if raw call volume were ingested | Yes, **failures only**, not call volume | High (Critical only if corroborated with an independent compromise signal) | Correlate dependency-failure spikes with honeypot/pfSense recon or app-tier auth abuse on the same IP |
| Availability tests (`AppAvailabilityResults`) | No (backend adapter is ready, KQL is not) | Medium — signals the app is down; could be attack-induced or an unrelated outage | Low volume | Yes, **failures only** | Medium by default; High only when corroborated with a concurrent attack-pattern alert | Correlate with `high_request_rate_threshold`/pfSense flood on the same window |
| Authentication failures — app tier (`AppRequests` 401/403) | Broken today (classification drift, see finding 4) | Very high — this is the core "authentication abuse against the application" signal, distinct from Entra ID sign-in | Medium | Yes — fix classification, add a dedicated threshold rule | High ceiling; Critical only via corroboration (mirrors `successful_login_after_spray`'s evidentiary bar) | Correlate with existing `failed_login_threshold`/`password_spraying_threshold`/`successful_login_after_spray` for the `AZURE_INSIGHTS` source, and with pfSense/Honeypot recon on the same IP |
| HTTP status-family spikes (401/403/429/5xx) | Partial (5xx only) | High — bucketing by status family catches both access-abuse (401/403) and rate-abuse (429) patterns already present in `AppRequests.ResultCode` | Medium | Yes, as part of the classification fix — bucket by family rather than only checking `>= 500` | High via correlation | 403-spike + Honeypot/pfSense recon on the same IP is a strong attack-progression signal |
| Custom events | No | Unknown — entirely dependent on what the instrumented app emits; no standard schema | Potentially very high, arbitrary | **No** — explicitly excluded; would need an allowlist design once specific events are catalogued for a real app, which is out of scope here | N/A | N/A until a concrete need is identified |
| Custom metrics | No | Low generic security value (mostly performance/business metrics, numeric time series) | Very high volume | **No** — this is exactly the "collect everything" trap the objective explicitly rejects | N/A | N/A |
| Traces (`AppTraces`) | Yes, but only a demo-artifact query (`"HTTP request received"`, a string the Function's own test endpoint logs) | Very low as implemented; traces in general are high-volume/low-signal for security detection at platform-generic granularity | Very high if broadened | **No** — remove the current demo query; do not broaden general trace ingestion | N/A | N/A |

## Detection philosophy and new detections

Consistent with `critical-response-consistency-and-severity-matrix`'s Critical philosophy ("the highest-confidence attack-chain or likely-compromise signal requiring immediate human review... not automatically confirmed compromise"), this change adds exactly two new detection rules — both correlation-first, both High by default, neither capable of independently producing Critical:

### New Rule 1 — `app_insights_unauthorized_access_threshold`
A base threshold rule (same shape as `http_error_threshold`): N `AppRequests` rows with `resultCode` in {401, 403} from the same source IP within a configurable window. This is the fix for finding 4 turned into a real detection rather than a silently-dropped signal — application-tier authorization abuse (credential stuffing against the app itself, forced-browsing into protected endpoints, token replay attempts) that Entra ID sign-in monitoring cannot see because it never reaches the identity provider. `RULE_APPLICABILITY`: `{AZURE_INSIGHTS}` only (this is an Application Insights–specific status-code pattern, not a generic web-log pattern already covered by `nginx`/`http_error_threshold`). Severity: `high`. Creates/links incidents under the existing High rule. No playbook containment step by default (investigation playbook only, matching `Reputation-Only`/`Password Spray Investigation`-style playbooks) — this is a detection-visibility fix, not a containment trigger.

### New Rule 2 — `azure_auth_abuse_exception_correlation`
A new correlation rule (added to `generate_targeted_correlation_alerts`'s rule tuple in `engines/correlation_engine.py`, same mechanism as `web_to_app_attack_pattern`/`cloud_app_error_pattern`): fires when `app_insights_unauthorized_access_threshold` (or the existing `password_spraying_threshold`/`failed_login_threshold` for `AZURE_INSIGHTS`) **and** `application_exception_threshold` (or a new `AppDependencies`-failure signal, Phase 2) are both open for the same source IP within a shared window. This is the attack-progression signal the objective asks for: authentication abuse against the app *and* the app becoming unstable at the same time, from the same source — materially stronger evidence than either alone, but still not confirmed compromise. Severity: `high`. **Critical precedence**: if `successful_login_after_spray` is already open for the same source IP (i.e., an actual successful authentication followed the spray), this correlation alert still fires at High and links to that incident via the existing `find_open_incident_by_source_ip`/`maybe_create_or_link_incident` path — it does **not** independently escalate to Critical and does **not** trigger a second approval-gated containment cycle, following the exact precedence model `critical-response-consistency-and-severity-matrix` established for `spray_then_success_pattern`. This is the concrete answer to "Critical should require corroborated evidence": the corroboration this rule provides is High-strength, and the only path to Critical remains an actual observed successful login.

**Phase 2 (optional, same change, lower priority)**: `azure_dependency_failure_after_recon_pattern` — correlates `AppDependencies` failure spikes with `pfsense_firewall_port_scan`/`honeypot_scanner_detected` on the same source IP (recon followed by backend instability). High, investigation-only, same precedence rules apply. Included in this change's scope but sequenced after Rules 1–2 land and prove out; can be dropped to a follow-on change without weakening the core proposal if time-boxed.

**Explicitly rejected**: a rule that fires on `application_exception_threshold` alone at anything above High, or that treats a single exception as alert-worthy. Both would violate "do not build detections around isolated exceptions."

## Correlation opportunities with existing sources

- **pfSense**: `azure_dependency_failure_after_recon_pattern` (Phase 2) — port scan/recon followed by application-tier instability on the same IP.
- **Honeypot**: same Phase 2 pattern via `honeypot_scanner_detected`; also a natural reputation-scoring input (`lookup_ip_reputation` already weights correlation alert types generically, so any new correlation alert type automatically contributes once added to `core/ip_helpers.py`'s `correlation_signal_config`, without new code beyond registering the weight).
- **nginx**: already correlated via `cloud_app_error_pattern` (unchanged by this change).
- **bank_app**: `app_insights_unauthorized_access_threshold` is deliberately scoped to `AZURE_INSIGHTS` only rather than merged into `bank_app`'s existing `failed_login_threshold`/`password_spraying_threshold`, because they are different applications/attack surfaces reported by different telemetry systems — merging them would conflate two distinct application tiers' evidence into one signal, which is not "smallest safe," it's evidence-blending.
- **Existing Critical logic (`successful_login_after_spray`)**: both new rules explicitly defer to it as the sole Critical trigger for spray-then-success evidence, per the precedence model above — this change adds corroborating High signals, not a second Critical path.

## Decisions

### D1 — Checkpoint/bookmark: SIEM-owned, not Function-owned
Add a new table `ingestion_checkpoints` (generic — keyed by `connector_name`, not Azure-specific, so it can be reused by a future connector without a new table): `connector_name TEXT PRIMARY KEY`, `last_processed_at TIMESTAMPTZ`, `last_poll_status TEXT` (`success`/`failure`/`partial`), `last_poll_counts JSONB` (returned/forwarded/skipped/failed), `updated_at TIMESTAMPTZ`. Two small endpoints on the existing Azure-authenticated surface: `GET /ingest/azure/checkpoint` (returns `last_processed_at`, defaulting to `NOW() - 1 hour` on first run — bounded catch-up, not unbounded backfill) and `PATCH /ingest/azure/checkpoint` (Function reports new watermark + poll outcome after each run), both guarded by the existing `require_azure_api_key()`. The Function's KQL window becomes `TimeGenerated >= datetime({checkpoint})` (paged, see D2) instead of `ago(5m)`. **Alternative considered**: Azure Durable Functions / Blob Storage checkpoint, keeping all state Azure-side. Rejected — it would make the SIEM's detection quality dependent on Azure-side state the SIEM cannot see or reason about (violates "plugs into the existing pipeline," and the SIEM already owns durable state for every other connector-adjacent concern); a tiny SIEM-owned table is the smaller, more consistent change, and it doubles as the health-visibility fix (D5).

### D2 — Paging instead of a raw record cap
Replace `take {MAX_RECORDS}` with checkpoint-plus-continuation paging: query `checkpoint → now`, ordered by `TimeGenerated asc`, capped per page at a Function app-setting `PAGE_SIZE` (default unchanged at 25 to preserve current behavior); if a full page is returned, advance the checkpoint to the last row's `TimeGenerated` and immediately query again within the same invocation (bounded to a small max-pages-per-invocation setting, e.g. 10, to keep the timer function's execution time bounded) rather than waiting for the next 5-minute tick. This means a burst above 25 events is caught up within the same poll cycle instead of silently truncated.

### D3 — Retry/timeout
Bounded retry (3 attempts, exponential backoff, e.g. 1s/2s/4s) on `_query_recent_telemetry()` and on `forward_telemetry_to_siem()` individually per row; the existing 10-second HTTP timeout on the forward call is kept. A row that still fails after retries is counted in `failures` and skipped for that poll — it is **not** lost, because the checkpoint only advances past a row once processing succeeds (or after a bounded number of poison-row skip retries, to avoid one permanently-failing row blocking the checkpoint forever — see Open Questions).

### D4 — Fix the classification drift (authentication-abuse signal)
`adapters/azure_insights_adapter.py::normalize_azure_insights_telemetry` gets a new branch: when `base_type_lower` indicates request/dependency telemetry and `result_code in {401, 403}`, return `event_type = "unauthorized_access"`, `severity = "medium"` (base event severity; the new threshold rule, not this per-row severity, is what determines alert severity — matching how `http_error`/`application_exception` per-row severities already work as informational context, not the alert-triggering authority). The Function's existing `_classify_telemetry_row` already computes this classification correctly — this decision makes the backend agree with it instead of silently overriding it.

### D5 — Poll-health visibility via the checkpoint table, not a new health system
`core/source_health.py::aggregate_source_health` gets one additional field per source, populated only for connectors that have an `ingestion_checkpoints` row (currently just `azure_insights`): `last_poll_status`, `last_poll_at`, `last_poll_counts`. This directly answers "did the poll fail, or is there genuinely no telemetry" without building a second health surface — Source Health remains the one place analysts check source health, exactly as `critical-response-consistency-and-severity-matrix`'s matrix principle would want ("this page explains current behavior, it is not a second system").

### D6 — Runtime configuration: what becomes configurable and what doesn't
**Becomes runtime-configurable (via the existing `detection_config` table/Runtime Configurables UI, same as every other rule)**: threshold and window for `app_insights_unauthorized_access_threshold`; threshold/window for `azure_auth_abuse_exception_correlation`'s shared correlation window. **Stays as Azure Function app settings, not SIEM-DB-configurable**: polling interval (the timer schedule itself — changing it requires a Function redeploy regardless, so a SIEM-side setting would not actually be hot-reloadable without extra plumbing that isn't justified here), `PAGE_SIZE`/max-pages-per-invocation, retry attempt count/backoff, KQL/HTTP timeouts. **Stays as a computed value, not a setting at all**: the lookback window, which becomes checkpoint-driven (D1) rather than a fixed number an operator would tune. This split follows the explicit "do not over-configure" instruction — only values with a real, exercised tuning need (detection sensitivity) go into the runtime-config system; operational plumbing settings that require a redeploy anyway stay in Function app settings.

### D7 — Detection wiring
`engines/detection_applicability.py`: add `"app_insights_unauthorized_access_threshold": RuleApplicability("source_specific", frozenset({AZURE_INSIGHTS}))`. `engines/detection_config.py`: add both new rules' defaults (threshold/window parameters, `active: True`, description) following the existing dict shape. `engines/correlation_engine.py`: add `azure_auth_abuse_exception_correlation` as a fourth entry in `generate_targeted_correlation_alerts`'s `rules` tuple, `severity: "high"`, matching on `(AZURE_INSIGHTS.source, AZURE_INSIGHTS.source_type)` rows with `alert_type in {app_insights_unauthorized_access_threshold, password_spraying_threshold, failed_login_threshold}` for one required group and `alert_type == application_exception_threshold` for the other — same `matches`/`group_for_row`/`required_groups` shape as the existing rules, no new correlation mechanism.

### D8 — Severity Response Matrix integration
Both new rules must appear in the matrix contract (`engines/severity_response_matrix.py`, once `critical-response-consistency-and-severity-matrix` is implemented) with `default_severity: "high"`, `maximum_severity: "high"`, and a `why` sentence consistent with the platform's Critical philosophy, e.g.: `app_insights_unauthorized_access_threshold` → "Application-tier authorization failures indicate probing, not confirmed access." / `azure_auth_abuse_exception_correlation` → "Correlated auth-abuse and application instability is a stronger signal, but still not proof of a successful compromise." This is a stated dependency, not a code change performed by this proposal (see Capabilities in `proposal.md`); the matrix's own requirements already guarantee any newly-registered rule with a `detection_config` entry appears automatically once both changes are implemented, since the matrix reads live from `detection_config`/`playbook_store`, not a hardcoded list.

## Runtime configuration summary

| Setting | Configurable? | Where |
|---|---|---|
| `app_insights_unauthorized_access_threshold` threshold/window | Yes | `detection_config` table / Runtime Configurables UI |
| `azure_auth_abuse_exception_correlation` window | Yes | `detection_config` table / Runtime Configurables UI |
| Azure Function polling interval | No (requires redeploy anyway) | Function app setting (`host.json`/timer schedule) |
| Page size / max pages per invocation | No | Function app setting |
| Retry attempts / backoff | No | Function app setting |
| KQL / HTTP timeouts | No | Function app setting |
| Lookback window | N/A — computed from checkpoint | `ingestion_checkpoints.last_processed_at` |

## UI recommendations (not implemented in this change)

Only one addition provides real operational value and is recommended as a **follow-on change**, not built here:
- **Extend the existing Source Health workspace** with the `last_poll_status`/`last_poll_at`/`last_poll_counts` fields from D5, scoped to connectors that report checkpoints (currently just Application Insights). This directly answers "is Azure ingestion actually working" without a new page.

**Explicitly not recommended**: a standalone "Application Health," "Azure Monitor status," or "Connector health" workspace — Source Health already exists and already tracks `azure_insights`; a second page duplicating that surface for one connector would be exactly the kind of parallel system this change's own design principle (D5) argues against. If a second connector with meaningfully different health semantics is added later, revisit this recommendation.

## Scope planning: one OpenSpec, one deferred follow-on

**Recommendation: one OpenSpec now** (this change), covering ingestion reliability and the two new detections together — they are not independently valuable: adding detections on top of an unreliable, silently-lossy, misclassifying pipeline would produce detections analysts couldn't trust, and fixing reliability without adding the detections leaves the "high-signal" half of the objective undone. Splitting them would create an artificial sequencing dependency between two child specs that must land together anyway.

**Deferred, not created now**: a follow-on child OpenSpec for the Source Health UI extension (above). It is genuinely independent (pure frontend, no detection/ingestion coupling), small, and explicitly out of scope for "do not implement UI" in this pass.

**Not recommended as separate specs**: splitting `AppDependencies`/`AppAvailabilityResults` ingestion (Phase 2 telemetry) or `azure_dependency_failure_after_recon_pattern` (Phase 2 detection) into their own change. They're sequenced later within *this* change's phases (see `tasks.md`) because they're lower-priority, not because they're architecturally separable — pulling them into a second OpenSpec would just add coordination overhead for work that reuses every decision (D1–D7) made here.

## Risks / Trade-offs

- [Checkpoint table becomes a new durability dependency — if `ingestion_checkpoints` is unreachable, the Function has no watermark] → Mitigation: `GET /ingest/azure/checkpoint` failure falls back to a bounded default (`NOW() - 1 hour`), never to an unbounded backfill; this mirrors the existing fail-open pattern (`critical-response-consistency-and-severity-matrix` D6) — a checkpoint-read failure degrades to "poll a fixed recent window" rather than blocking ingestion entirely.
- [Paging (D2) could make one Function invocation run long during a genuine burst] → Mitigation: bounded max-pages-per-invocation; any remainder is picked up by the next timer tick since the checkpoint only advances through what was actually processed.
- [New `app_insights_unauthorized_access_threshold` could be noisy for applications with legitimate periodic 401s (e.g., expired-token retry patterns)] → Mitigation: threshold/window are runtime-configurable (D6) specifically so operators can tune sensitivity per-environment without a code change, same as every other threshold rule.
- [Classification fix (D4) changes historical-looking severity for any already-open `normal_activity` alerts that were actually 401/403s] → Mitigation: applies to newly ingested events only, consistent with "no historical data rewrites" established in the prior change.
- [Retry-with-backoff (D3) could delay a poll's completion, risking timer overlap] → Mitigation: bounded attempts (3) with short backoff (max ~7s total added latency), well inside the 5-minute timer cadence.

## Migration Plan

1. **Mac AI**: add `ingestion_checkpoints` migration; implement D1–D8 as source changes (Function + backend); add the two new detection rules and one correlation rule; run focused + affected backend tests; update `docs/azure-integration-setup.md` for the new checkpoint/paging behavior.
2. **Mac AI**: full affected regression suite, `openspec validate --strict`, `git diff --check`.
3. **User authorization gate**: commit/push only when explicitly authorized.
4. **VM AI**: clean-tree preflight, sync, migration dry-run + apply, restart affected services, verify `/health`; separately (Azure-side, outside the Mac/VM source-of-truth boundary) redeploy the Azure Function with the updated `function_app.py` and any new app settings (`PAGE_SIZE`, `MAX_POLL_PAGES`, retry settings) — this is an Azure Function deployment, not a VM deployment, and follows whatever authorization process already governs that Function App; it is called out explicitly here so it isn't mistaken for a VM step.
5. **Rollback**: the checkpoint table is additive (new table, no existing table altered); if the paged/checkpoint Function logic misbehaves, reverting `function_app.py` to the previous fixed-window version is safe — the checkpoint table would simply go unused, not become inconsistent, since nothing else depends on it being populated.

## Open Questions

- Poison-row handling: if a single Application Insights row fails processing repeatedly (e.g., a malformed payload), should the checkpoint skip past it after N retries (bounded data loss for one row) or block the checkpoint from advancing (bounded data loss for the whole connector, sequential)? Recommend skip-after-N with a logged/health-visible warning — a single bad row should not stall a shared telemetry pipeline — but this needs explicit confirmation before implementation.
- Whether `azure_dependency_failure_after_recon_pattern` (Phase 2) ships in this change's later phase or is explicitly deferred to a follow-on if Phase 1's reliability work takes longer than expected — recommend keeping it in this change but treating it as droppable without renegotiating scope.
- Whether the checkpoint API's default catch-up window (`NOW() - 1 hour` on first run / after a read failure) is the right bound, or whether it should be tighter (e.g., 15 minutes, closer to existing correlation windows) to limit backfill volume after an extended outage.
