## Context

### Existing alert inventory (re-verified directly against the code)

**Detection-rule alert types** (`engines/detection_engine.py`, one generator function each):

| Alert type | Source function | Severity |
|---|---|---|
| `failed_login_threshold` | `_generate_failed_login_alerts_core` | high |
| `http_error_threshold` | `_generate_http_error_alerts_core` | medium |
| `port_scan_threshold` | `_generate_port_scan_alerts_core` | medium |
| `password_spraying_threshold` | `_generate_password_spraying_alerts_core` | high |
| `successful_login_after_spray` | `_generate_successful_login_after_spray_alerts_core` | critical |
| `application_exception_threshold` | `_generate_application_exception_alerts_core` | high |
| `high_request_rate_threshold` | `_generate_high_request_rate_alerts_core` | medium |
| `honeypot_env_probe_threshold` | `_generate_env_probe_alerts_core` | high |
| `honeypot_admin_probe_threshold` | `_generate_admin_probe_alerts_core` | medium |
| `honeypot_scanner_detected` | `_generate_scanner_detected_alerts_core` | medium |
| `honeypot_credential_stuffing_threshold` | `_generate_credential_stuffing_alerts_core` | high |

**Correlation alert types** (`engines/correlation_engine.py`):

| Alert type | Mechanism | Severity |
|---|---|---|
| `correlated_activity` | Cross-alert-type correlation: ≥2 distinct alert types from the same source IP | derived |
| `web_to_app_attack_pattern` | Targeted correlation: web-tier errors/rate + bank-app failed-login/spray within 10 min | critical |
| `spray_then_success_pattern` | Targeted correlation: `password_spraying_threshold` + `successful_login_after_spray` from the same IP within 15 min | critical |
| `cloud_app_error_pattern` | Targeted correlation: cloud + web-tier errors correlated within 10 min | high |

Both sets are consumed identically by the playbook trigger matcher (`engines/playbook_engine.py`), which recognizes exactly five trigger keys: `alert_type` (exact match), `min_severity` (rank-based, `low < medium < high < critical`), `source` (exact match), `correlation_flag` (boolean membership in the four correlation alert types above), and `reputation_score_min` (numeric floor against `alerts.reputation_score`). Trigger evaluation is pure AND logic over whichever keys are present.

### Existing playbook capability inventory

**Actions** (`engines/playbook_registry.py`, post-hardening): `monitor`, `flag_high_priority`, `require_approval` (`CORE_ACTIONS`), plus `notify_slack`, `notify_teams`, `notify_email`, `notify_webhook`, `block_ip` (`ADAPTER_ACTIONS`) — unified under `KNOWN_PLAYBOOK_ACTIONS`. Concretely:

- `monitor`, `flag_high_priority` — log-only step entries (`"[SIMULATED PLAYBOOK STEP] ..."`, `output: {simulated: true, executed: false}`). No alert-visible side effect beyond the execution's own `steps_log`.
- `require_approval` — fully functional: creates an `approval_requests` row, pauses the execution to `awaiting_approval`, TTL-bound (`expires_in_minutes`, default 60), risk-leveled (`medium`/`high`/`critical`), resolved only by `super_admin` via `POST /approvals/<id>/decision`. Approve resumes execution at the next step; deny or expiry finalizes the execution as `failed` with all later steps marked `skipped`.
- `notify_slack`/`notify_teams`/`notify_email`/`notify_webhook` — dispatch through the corresponding adapter, delivery-tracked and idempotency-deduplicated (`notification_delivery_store`). Message content comes from step `params`, resolved per execution once `dynamic-playbook-parameter-binding` is implemented.
- `block_ip` — protected-target-checked (`require_unprotected_target(params.get("source_ip"))`, added by `Playbook Engine Correctness Hardening`) before dispatch to the firewall adapter, which remains permanently simulation-only. Requires dynamic binding of `source_ip` to `{{alert.source_ip}}` for per-alert containment.

**Engine dependency (blocking for implementation):** playbook step `params` are currently read verbatim from stored step JSON (`engines/playbook_step_executor.py`: `params = step.get("params")`). There is no per-execution binding today. `execution["alert_id"]` is available but not used to populate params. Version 1 playbook designs below assume `dynamic-playbook-parameter-binding` resolves `{{alert.<field>}}` expressions at execution time. Content authorship is BLOCKED until that capability ships.

**Enrichment already available on an alert at the moment a playbook fires:** `reputation_score`, `reputation_label`, `reputation_source`, `reputation_summary` (computed at ingest via AbuseIPDB, `core/ip_helpers.py`), and — read separately, not through the playbook engine — a MITRE `alert_type → technique` tag (`helpers/enrichment_helpers.py`) and the Source-IP Context API. None of these are re-queried or re-computed during playbook execution; they are either already on the alert row (reputation) or available to an analyst through other existing views (MITRE, source-IP context) that the playbook cannot invoke as a step.

**Approval-gated actions:** only `require_approval` gates anything. Risk levels `medium`/`high`/`critical` map to no automatic behavioral difference beyond what the playbook author sets as `risk_level` and `expires_in_minutes` per step — the engine does not itself escalate handling by risk level.

### Which alerts are actually worth automating

Not every alert type above deserves a playbook. Selection criteria applied: (1) the alert type represents a real, recurring SOC decision point (act vs. investigate vs. ignore), (2) the response is expressible with engine actions once parameter binding exists, (3) the playbook would not be redundant with another one in this same pack. On that basis: `failed_login_threshold`, `password_spraying_threshold`, `successful_login_after_spray` (or its corroborating correlation, `spray_then_success_pattern`), and `reputation_score_min` (an existing, currently-unused trigger key) are the highest-value candidates.

## Goals / Non-Goals

**Goals:**
- Define exactly five Version 1 playbooks, each fully specified (trigger, purpose, steps, actions used, dynamic bindings, approval requirement, expected outcome, V1 justification).
- Use actions and trigger keys that work once `dynamic-playbook-parameter-binding` is implemented.
- Name every playbook idea deferred for reasons other than parameter binding.

**Non-Goals:**
- Not an engine change, schema change, new action, or UI change of any kind in this spec-writing step.
- Not queue retirement, branching, chaining, scheduler work, or enrichment steps.
- Not implementation of playbook rows — BLOCKED until `dynamic-playbook-parameter-binding` lands.
- Not a redesign of `require_approval`, notification delivery, or protected-target policy.

## Decisions

### Proposed Core Playbook Pack (five playbooks)

1. **Brute Force Containment** (approval-gated containment)
2. **Password Spray Investigation** (enrichment-only, no block — intentional SOC restraint)
3. **Successful Login After Spray Response** (highest-severity approval-gated containment)
4. **Malicious IP Containment** (reputation-triggered approval-gated containment)
5. **Reputation-Only Investigation** (broad, low-bar enrichment nudge)

Each is detailed below with full trigger/step JSON shape.

---

#### 1. Brute Force Containment

- **Trigger:** `{"alert_type": "failed_login_threshold", "min_severity": "high"}`
- **Purpose:** Escalate a sustained failed-login pattern from one source fast enough for an analyst to act before credentials are exhausted.
- **Why this playbook exists:** `failed_login_threshold` is the single most common real brute-force signal the platform already produces, and today it generates an alert with zero automated response.
- **Step-by-step flow:**
  1. `flag_high_priority` — marks the execution/alert for analyst attention (log-only today).
  2. `require_approval` (`risk_level: "high"`, `expires_in_minutes: 30`, `reason: "Sustained failed-login pattern from {{alert.source_ip}} — approve IP block"`).
  3. On approval: `block_ip` (`params.source_ip: "{{alert.source_ip}}"`) — blocks the offending source IP (simulation-only until live firewall integration).
  4. `notify_slack` (`params.message: "{{alert.alert_type}} from {{alert.source_ip}} (severity {{alert.severity}}) — brute-force containment executed"`).
- **Engine actions used:** `flag_high_priority`, `require_approval`, `block_ip`, `notify_slack`.
- **Approval required:** Yes — high risk, 30-minute TTL. `block_ip` runs only after approval.
- **Expected outcome:** on approval, the triggering alert's source IP is blocked (simulated) and the analyst channel is notified with alert-specific context; on deny/expiry, the execution ends `failed` with no block or notification.
- **Why it belongs in Version 1:** highest-frequency brute-force signal; demonstrates approval-gated containment with dynamic IP targeting end-to-end.

#### 2. Password Spray Investigation

- **Trigger:** `{"alert_type": "password_spraying_threshold"}`
- **Purpose:** Low-and-slow credential attacks across many accounts warrant investigation, not knee-jerk blocking — spray traffic often rides shared/VPN egress IPs where blocking causes collateral impact.
- **Why this playbook exists:** demonstrates deliberate restraint (not every SOAR response should escalate to containment) using a real, already-produced correlation-adjacent signal.
- **Step-by-step flow:**
  1. `monitor` — durable log entry marking the execution.
  2. `notify_slack` (`params.message: "Password spray from {{alert.source_ip}} — review reputation ({{alert.reputation_label}}, score {{alert.reputation_score}}) and Source-IP Context"`).
- **Engine actions used:** `monitor`, `notify_slack`.
- **Approval required:** No — no destructive or escalating action is requested.
- **Expected outcome:** timely analyst nudge to review already-computed enrichment for a developing pattern, with no automatic action taken.
- **Why it belongs in Version 1:** a real interview differentiator — shows the automation layer knows when *not* to escalate, not just when to.

#### 3. Successful Login After Spray Response

- **Trigger:** `{"alert_type": "successful_login_after_spray", "min_severity": "critical"}`
- **Purpose:** A successful login immediately following a password-spray pattern is near-certain account compromise — the platform's single highest-confidence signal, currently with zero automated response.
- **Why this playbook exists:** `successful_login_after_spray` (and its corroborating correlation alert, `spray_then_success_pattern`, produced when both it and `password_spraying_threshold` occur from the same IP within 15 minutes) are real, already-computed signals that deserve the fastest escalation path in the pack.
- **Step-by-step flow:**
  1. `flag_high_priority`.
  2. `require_approval` (`risk_level: "critical"`, `expires_in_minutes: 15`, `reason: "Successful login following password-spray from {{alert.source_ip}} — near-certain compromise, approve IP block"`).
  3. On approval: `block_ip` (`params.source_ip: "{{alert.source_ip}}"`) — block the compromised source immediately (simulation-only).
  4. `notify_slack` (`params.message: "CRITICAL: {{alert.alert_type}} from {{alert.source_ip}} — containment executed"`).
  5. `notify_email` (`params.subject: "CRITICAL: compromise signal {{alert.alert_type}}"`, `params.message: "Successful login after spray from {{alert.source_ip}}. Severity: {{alert.severity}}."`).
- **Engine actions used:** `flag_high_priority`, `require_approval`, `block_ip`, `notify_slack`, `notify_email`.
- **Approval required:** Yes — critical risk, 15-minute TTL. `block_ip` runs only after approval.
- **Expected outcome:** fastest possible approval-gated containment for the platform's most severe signal, with dual-channel alert-specific notification on approval.
- **Why it belongs in Version 1:** the strongest "why this matters" narrative in the pack; the only playbook that exercises the tightest approval TTL and dual-channel notification; built on a signal the correlation engine already independently corroborates.
- **Note:** a natural V1.1 extension (not required now) is a second playbook keyed on `correlation_flag: true, alert_type: "spray_then_success_pattern"` for the cross-validated version of this same scenario — left out of V1 to keep the pack minimal, since the atomic `successful_login_after_spray` alert already fires immediately without waiting on the correlation pass.

#### 4. Malicious IP Containment (reputation-triggered containment)

- **Trigger:** `{"reputation_score_min": 80, "min_severity": "medium"}` — no `alert_type` key, so it matches any alert type from a source IP AbuseIPDB already scores as high-confidence malicious.
- **Purpose:** When an alert's source IP is already independently known-bad, escalate and contain faster than a first-seen IP — regardless of which specific rule tripped.
- **Why this playbook exists:** `reputation_score_min` is an existing, already-supported trigger key that no playbook has ever used — this closes the audit's "reputation only gates whether other playbooks fire, never drives its own response" gap.
- **Step-by-step flow:**
  1. `flag_high_priority`.
  2. `require_approval` (`risk_level: "high"`, `reason: "Known-malicious source IP {{alert.source_ip}} (reputation {{alert.reputation_score}}) — approve block"`).
  3. On approval: `block_ip` (`params.source_ip: "{{alert.source_ip}}"`).
  4. `notify_slack` (`params.message: "{{alert.alert_type}} from known-malicious IP {{alert.source_ip}} (score {{alert.reputation_score}}) — blocked"`).
- **Engine actions used:** `flag_high_priority`, `require_approval`, `block_ip`, `notify_slack`.
- **Approval required:** Yes — high risk.
- **Expected outcome:** any alert type from a known-bad IP gets approval-gated containment with alert-specific notification on approval.
- **Why it belongs in Version 1:** the only playbook in the pack that is alert-type-agnostic, demonstrating trigger-key coverage beyond `alert_type` matching.
- **Risk to note:** because it is alert-type-agnostic, a source IP tripping several different alert types in quick succession can generate several separate executions/notifications for the same underlying IP. Acceptable for V1; a tuning consideration, not a defect.

#### 5. Reputation-Only Investigation

- **Trigger:** `{"reputation_score_min": 40, "min_severity": "low"}` — a deliberately low bar, paired with no approval gate, to catch the "not bad enough to escalate, but worth a look" band.
- **Purpose:** Many alerts deserve a context-gathering nudge, not an action. Separating "worth a glance" from "worth an approval-gated escalation" is itself a SOC-maturity signal.
- **Why this playbook exists:** complements Playbook 4 by demonstrating a genuinely tiered reputation response (low bar → nudge, high bar → escalate), reusing the same trigger key with different thresholds and different consequences.
- **Step-by-step flow:**
  1. `monitor`.
  2. `notify_slack` (`params.message: "Review alert {{alert.alert_type}} from {{alert.source_ip}} — reputation {{alert.reputation_label}} ({{alert.reputation_score}})"`).
- **Engine actions used:** `monitor`, `notify_slack`.
- **Approval required:** No.
- **Expected outcome:** analyst awareness without escalation fatigue.
- **Why it belongs in Version 1:** proves the reputation trigger key supports tiered responses, not just one fixed threshold, at essentially no additional engine risk.

### Deferred playbooks (explicitly out of Version 1, with the specific blocking dependency)

| Idea | Blocked on |
|---|---|
| Ransomware early response | Endpoint/file-integrity telemetry — no such ingestion source exists. |
| Suspicious PowerShell investigation | Endpoint/process telemetry — none ingested. |
| Suspicious process investigation | Same as above. |
| Beaconing / suspicious outbound traffic investigation | Network flow + periodicity detection — no such correlation rule exists. |
| Impossible travel investigation | Identity + geolocation correlation rule — geolocation exists (honeypot backfill) but no correlation rule joins it with identity/time. |
| Privileged account monitoring | Identity/role metadata for real (non-honeypot) accounts — not modeled. |
| Repeated malware detections | AV/EDR ingestion — none exists. |
| Suspicious authentication chains | Password-reset/account-change event ingestion — not modeled. |
| Threat hunting helper workflow | Manual/ad hoc playbook trigger route — roadmap item `Ad Hoc Trigger & Enrichment Step`, not yet built. |
| Analyst evidence collection | Evidence-snapshot data model — roadmap item `Incident Evidence Collection & Automated Case Enrichment`, not yet built. |
| Automated case enrichment on incident creation | Wiring only, but scoped to its own roadmap item, not bundled here. |
| Multi-approver / escalating approval workflows | Approval-model gap — roadmap item, not yet built. |
| Playbook chaining | Chaining capability — roadmap item, deliberately sequenced last. |

**Note:** Parameter binding is no longer a deferred-playbook blocker — it is tracked as `dynamic-playbook-parameter-binding` (roadmap item 2.4) and is a hard prerequisite for implementing this pack.

## Risks / Trade-offs

- **[Risk]** Playbook 4's alert-type-agnostic trigger could produce notification volume disproportionate to its value if a noisy IP trips many rules.
  **[Mitigation]** Threshold (`reputation_score_min: 80`) and `min_severity: "medium"` floor are tuning parameters, adjustable at authorship time without any engine change; notification delivery is already idempotency-deduplicated per execution/step so repeat *processing* of the same step cannot double-send.
- **[Risk]** `flag_high_priority`/`monitor` remaining log-only (unchanged by this or the prior hardening spec) means "escalation" in these playbooks is only visible in the execution's own `steps_log`, not in any analyst-facing priority indicator elsewhere in the UI.
  **[Mitigation]** Accepted for V1 — fixing `flag_high_priority`'s real-world effect is an engine change, out of scope here; the approval + notification steps still produce real, actionable signal regardless.
- **[Risk]** Five playbooks matching broad `alert_type`/`reputation_score_min` criteria could create duplicate-feeling executions if an alert matches more than one playbook's trigger simultaneously (e.g., a `password_spraying_threshold` alert with a high reputation score matches both Playbook 2 and Playbook 4).
  **[Mitigation]** This is intended, not a bug — `playbook_definitions` is designed for many-to-one matching (`engines/soar_playbook_orchestrator.py` creates one execution per matched playbook), and here it correctly reflects that the same alert can warrant both an investigation nudge and a reputation-based escalation.

## Migration Plan

Not applicable in the schema/deployment sense — no code or schema changes are required by this spec. **Implementation is BLOCKED** until `dynamic-playbook-parameter-binding` is complete. When the gated implementation phase executes: each playbook is created via one `POST /playbooks` call (or an optional convenience seed script). Rollback for any single playbook is `PATCH /playbooks/<id>/enabled` to `false`, or deletion via existing definition management.

## Open Questions

- Exact reputation thresholds (`80` for Playbook 4, `40` for Playbook 5) are reasonable starting points — tune at authorship time without revisiting this spec.
- Should `require_approval` `reason` fields support embedded static text plus dynamic bindings in a future template extension, or whole-value binding only for v1? Deferred to `dynamic-playbook-parameter-binding`.
