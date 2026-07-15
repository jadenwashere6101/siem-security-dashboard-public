## Context

The current pfSense flow is mechanically correct but operationally misleading under real Internet traffic. `firewall_block` events fan out into `pfsense_firewall_repeated_deny`, `pfsense_firewall_port_scan`, and `pfsense_firewall_noisy_source`; `firewall_allow` fans out into `pfsense_firewall_suspicious_allow` and `pfsense_firewall_noisy_source`. Severity then drives automatic incident creation through `routes/ingest_routes.py` and `core/incident_store.py`, while `high` pfSense playbooks remain approval-gated for `block_ip`. Notification policy routes pfSense alerts and incidents once they meet the global minimum severity.

Production evidence changes the problem statement. The High-alert storm was not caused primarily by numeric thresholds. It was caused by severity escalation that treated `reputation_score >= 70` as sufficient for `high`, plus per-source incident/approval behavior that assumed each hostile IP deserved its own operational object. The authoritative production summary for this change is:

- 504 unique source IPs produced 510 alerts.
- 289/289 High pfSense alerts became High because `AbuseIPDB reputation_score >= 70`.
- None became High because of meaningful breadth or volume.
- `repeated_deny` High alerts fired at exactly 7 events.
- `port_scan` High alerts averaged about 2 ports and 8-9 hosts.
- 298 open P2 incidents were created.
- 165 approval requests expired unactioned.
- The activity reflects distributed commodity Internet reconnaissance against the protected `8.14.136.x` range, not proven coordination or compromise.

The change therefore needs to correct severity, incident, approval, and notification behavior without hiding evidence, rewriting history, or redesigning SOAR.

## Goals / Non-Goals

**Goals:**
- Make pfSense `high` mean meaningful observed risk against this environment, not just bad reputation on a minimum-threshold alert.
- Preserve individual alerts and raw-event evidence while giving analysts one durable summary for distributed commodity reconnaissance.
- Reduce incident, approval, and Slack noise without suppressing true escalation paths.
- Expand target evidence and analyst wording so alerts describe actual scan behavior rather than only counts.
- Add one narrowly scoped allow-after-deny progression detector that preserves evidence and supports approved containment when justified.
- Keep notification policy authoritative and integrate with existing alert, incident, playbook, and Severity Matrix behavior.
- Preserve historical artifacts and use the existing baseline model to separate pre-fix from post-fix behavior after deployment.

**Non-Goals:**
- No VM work, no production mutation, and no implementation in this authoring step.
- No historical rewrite of existing alerts, incidents, approvals, thresholds, or notifications.
- No new generic campaign platform for every source type; this aggregate is pfSense-scoped and bounded to distributed Internet reconnaissance.
- No replacement of the existing approval model, response-action queue, or notification system.
- No broad dashboard redesign or new analytics warehouse.

## Decisions

### 1. Correct pfSense severity by requiring observed behavior, not reputation alone

Severity will remain on the existing four pfSense alert families, but `reputation_score >= 70` will become supporting evidence rather than an independent `high` switch.

Final severity model:

- `pfsense_firewall_noisy_source`
  - Always `low`.
  - Never incident-eligible.
  - Never approval-eligible.

- `pfsense_firewall_repeated_deny`
  - Inbound external-source baseline remains `low`, even with high reputation, when the alert only meets the base repeated-deny threshold on one target/service tuple.
  - Escalates to `medium` only for materially sustained inbound denied activity on that tuple, defined as `event_count >= threshold * PFSENSE_SEVERITY_ESCALATION_MULTIPLIER`.
  - Escalates to `high` only for behavior that is operationally meaningful against this environment:
    - outbound/internal-host repeated deny meeting the base threshold, or
    - later corroborating progression/telemetry tied to the same source.
  - Pure inbound commodity deny noise does not become `high` from reputation alone.

- `pfsense_firewall_port_scan`
  - Baseline is `medium` when either the port threshold or host threshold is met.
  - Escalates to `high` only when breadth is materially strong against this environment, defined as any of:
    - `distinct_port_count >= threshold * 3`
    - `distinct_destination_count >= host_threshold * 3`
    - `reputation_score >= 70` plus `distinct_port_count >= threshold * 2`
    - `reputation_score >= 70` plus `distinct_destination_count >= host_threshold * 2`
    - corroborating same-source progression or non-pfSense telemetry
  - Reputation never creates `high` by itself.

- `pfsense_firewall_suspicious_allow`
  - Baseline is `medium` for a qualifying inbound allow to a sensitive service.
  - Escalates to `high` only when corroborated by behavior:
    - `event_count >= high_confidence_repeat_threshold`
    - `distinct_sensitive_port_count >= distinct_port_escalation_threshold`
    - same-source allow-after-deny progression on the same target/service
    - `reputation_score >= 70` plus repeated qualifying allows (`event_count >= 2`)
  - Reputation alone never creates `high`.

- `pfsense_firewall_noisy_source`
  - Remains a suppression-only low-severity rollup.

No pfSense alert family becomes `critical`.

Alternative considered: lower only the numeric thresholds through `detection_config`. Rejected because it would not solve the evidence hierarchy error that made reputation alone sufficient for `high`.

### 2. Decouple severity from containment eligibility

Not every `high` pfSense alert should create an approval-gated `block_ip` path.

Containment-eligible behavior will be narrowed to source-specific, actionable cases:
- `pfsense_firewall_suspicious_allow` `high`
- `pfsense_firewall_allow_after_deny` `high`
- `pfsense_firewall_repeated_deny` `high` with outbound/internal-host context
- `pfsense_firewall_port_scan` `high` only when it is not classified as routine distributed commodity reconnaissance and carries strong single-source breadth or corroboration

Commodity distributed reconnaissance, even when operationally important, is not itself a reason to generate one approval per external source. The aggregate object will never open bulk `block_ip` approvals.

Alternative considered: keep current “all High pfSense port scan alerts are containment-eligible.” Rejected because it is exactly what produced 165 expired approvals.

### 3. Preserve per-alert evidence but add one durable distributed-recon aggregate

This change will recommend a durable persistence model rather than a purely calculated view.

Rationale:
- The aggregate needs lifecycle/status.
- It needs deterministic membership over time.
- It needs opening/update notification deduplication.
- It must relate to incidents and approvals without inventing a second classification system.
- It must not rely on time alone.

Recommended persistence:
- `recon_activities`
  - one row per aggregate
  - scoped initially to pfSense distributed Internet reconnaissance
- `recon_activity_alerts`
  - many-to-many membership between aggregate and underlying alerts

Minimum `recon_activities` fields:
- `id`
- `activity_type` (`distributed_internet_reconnaissance`)
- `source`
- `source_type`
- `status` (`open`, `monitoring`, `resolved`)
- `severity` (`low`, `medium`, `high`)
- `coordination_status` (`not_established`, `possible`, `supported`)
- `protected_range_key`
- `service_signature`
- `first_seen`
- `last_seen`
- `assessment_text`
- `created_at`
- `updated_at`
- `resolved_at`

Summary counts and representative values should be derivable live from linked alerts/events where practical, but bounded cached snapshots are acceptable for analyst performance as long as alerts/events remain source of truth.

Alternative considered: a read-only aggregation query with no durable row. Rejected because it does not cleanly support status, deduped notifications, stable analyst links, or related-incident tracking.

### 4. Aggregate membership must be based on target signature plus time, not time alone

Membership criteria for `Distributed Internet Reconnaissance Activity`:
- candidate alert types are `pfsense_firewall_port_scan` and `pfsense_firewall_repeated_deny`
- source must be external/public
- traffic must be inbound
- candidate must not already be source-specific containment behavior (`suspicious_allow`, outbound/internal-host repeated deny, allow-after-deny high)
- target evidence must map into the same protected public range bucket
- service signature must overlap by at least one destination port
- alert evidence windows must overlap the aggregate’s active window

The recommended protected-range key is a normalized public destination range bucket, initially `/24` for IPv4 public targets unless implementation finds a safer existing inventory signal. The service signature is the bounded set of primary destination ports represented by member alerts.

This deliberately excludes unrelated same-time activity that hits a different protected range or different service set.

### 5. Use the aggregate as the primary analyst object for commodity distributed recon, not the incident table

Routine distributed commodity reconnaissance should create:
- preserved underlying alerts
- one durable recon activity aggregate
- dashboard visibility
- at most one optional grouped incident only if the aggregate itself escalates materially

Auto-incident rules:
- `low`/`medium` pfSense alerts: no auto incident
- `pfsense_firewall_repeated_deny` inbound commodity scan: no auto incident
- `pfsense_firewall_port_scan` enrolled into distributed recon aggregate: no per-source auto incident
- `pfsense_firewall_suspicious_allow high`: source-specific incident eligible
- `pfsense_firewall_allow_after_deny high`: source-specific incident eligible
- distributed recon aggregate:
  - no auto incident while coordination remains `not_established` and all member behavior remains commodity reconnaissance
  - may create at most one grouped P2 incident if the aggregate itself escalates to `high` because of materially sustained breadth, progression, or corroboration

This keeps incident volume aligned with operational actionability.

### 6. Expand target evidence through bounded snapshots plus on-demand related-event inspection

`events.raw_payload` remains authoritative. Alert and aggregate context become bounded investigation snapshots.

Recommended alert `target_context` additions:
- `evidence_kind` (`exact_target`, `aggregate_sample`)
- `primary_destination_ip`
- `primary_destination_port`
- `sample_destination_ips` (max 5)
- `sample_destination_ports` (max 5)
- `distinct_destination_count`
- `distinct_port_count`
- `protocol`
- `firewall_action`
- `interface`
- `direction`
- `attempts`
- `first_seen`
- `last_seen`
- `related_event_count`
- `evidence_window`

Deterministic sample rules:
- IP samples: sort by descending event frequency, then ascending IP text; keep first 5
- port samples: sort by descending event frequency, then ascending numeric port; keep first 5

Do not store unbounded raw payloads in alert or aggregate rows. Instead, add a read-only related-events inspection path that uses the stored evidence window and target filters to return a bounded event list.

### 7. Generate canonical human-readable scan descriptions in the backend

The backend will own analyst wording so alert tables, detail panels, aggregate cards, and notifications do not drift.

Canonical rules:
- 1 port, N hosts: `Scanned port 5060 across 10 public IPs.`
- N ports, 1 host: `Scanned 8 ports on 1 destination host.`
- N ports, M hosts: `Scanned 6 ports across 12 destination hosts.`

Use `public IPs` only when the supporting evidence is a public-IP sample/range. Otherwise use `destination hosts`.

Exact counts remain available separately in target evidence.

### 8. Add one new alert family for allow-after-deny progression

Recommended new alert type: `pfsense_firewall_allow_after_deny`.

Detection shape:
- same external source IP required
- inbound only
- qualifying deny count required before allow
- progression window required

Matching rules:
- Medium path:
  - same source IP
  - at least 3 prior denies
  - later allow to the same destination port/protocol within the same protected range
  - within 30 minutes
- High path:
  - same source IP
  - at least `PFSENSE_REPEATED_DENY_THRESHOLD` prior denies
  - later allow to the same destination IP and same destination port/protocol within 30 minutes
  - or the later allow reaches a sensitive service with same-source deny history
  - or corroborating non-pfSense application/auth telemetry exists in the correlation window

Does not qualify:
- outbound allow
- different source IP
- unrelated port change with no matching service signature
- a single prior deny

Behavior:
- `medium`: no incident, no approval, dashboard/investigation only
- `high`: source-specific incident eligible, immediate notification eligible, approval-gated containment eligible
- never `critical`
- never auto-block

### 9. Keep notification policy authoritative, but reduce pfSense commodity noise by routing fewer objects into it

Notification design:
- low and medium commodity pfSense recon alerts remain dashboard-only
- one recon aggregate opening notification is eligible only when the aggregate reaches `high`
- one recon aggregate update notification is eligible only when one of these changes:
  - severity increases
  - coordination status changes
  - primary destination services materially change
  - aggregate status resolves
- per-source commodity recon alerts enrolled into an active aggregate do not send their own immediate Slack notifications
- source-specific high suspicious allow and allow-after-deny alerts remain immediately eligible
- notification policy still applies final routing, destination, and minimum-severity decisions

This uses the existing notification policy service rather than a parallel system.

### 10. Keep UI additions small and investigation-oriented

Recommended surfaces:
- Alert Details / Target Context
  - richer target evidence
  - canonical scan description
  - link to related recon activity when present
- Recon Activity workspace or bounded detail panel
  - primary analyst object for distributed commodity recon
- SOC Command Center
  - summary count/open-highlights for active recon activities
- Severity & Response Matrix
  - updated pfSense severity/response philosophy
- Detection Rules documentation/read-only metadata
  - updated explanations only

No broad app-shell redesign is needed.

### 11. Advance the operational baseline after deployment instead of rewriting history

Historical alerts/incidents remain intact under the existing pre-tuning model. After deployment, the pfSense tuning baseline should be advanced to the new rollout timestamp so post-fix operational views can separate old noisy artifacts from the new behavior. This is the correct place to distinguish legacy from current operations; historical rows should not be rewritten.

## Risks / Trade-offs

- [Risk] A new aggregate table introduces persistence and membership logic.  
  Mitigation: keep the model narrowly scoped to pfSense distributed recon, use only two tables, and preserve alerts/events as source of truth.

- [Risk] Over-correcting severity could hide meaningful hostile scanning.  
  Mitigation: keep exact structural escalators for `high`, retain source-specific progression paths, and preserve all alerts and target evidence.

- [Risk] Aggregate membership could over-group unrelated activity.  
  Mitigation: require shared protected-range key and service overlap in addition to time overlap.

- [Risk] Aggregate membership could under-group if target evidence is too sparse.  
  Mitigation: expand target snapshots with bounded deterministic samples before aggregate enrollment logic depends on them.

- [Risk] Notification suppression could make analysts miss escalation.  
  Mitigation: send aggregate open/update notifications only on material changes and keep source-specific high progression alerts immediately eligible.

- [Risk] Approval noise could remain if high severity still implies containment too broadly.  
  Mitigation: define containment eligibility separately from severity and remove commodity distributed recon from automatic approval generation.

- [Risk] Existing playbook assumptions about `high` pfSense port scans may no longer match desired behavior.  
  Mitigation: update core playbook pack contracts and Severity Matrix together in the same bounded change.

## Migration Plan

Recommended migration scope:

1. Add `recon_activities`.
2. Add `recon_activity_alerts`.
3. Backfill nothing.
4. Start creating aggregates only for new post-deploy activity.
5. Advance `SIEM_PFSENSE_TUNING_BASELINE` after rollout so operational views distinguish pre-fix from post-fix behavior.
6. Roll back by disabling aggregate creation and leaving additive tables/history intact if needed.

This is the smallest correct durable model. A read-only calculation is insufficient for lifecycle, deduped notifications, and stable analyst links.

## API / UI Impact

Expected additive backend impact:
- additive recon-activity list/detail endpoints
- additive alert detail fields for richer target evidence and aggregate linkage
- additive related-event inspection endpoint or route variant
- updated Severity Matrix row content for pfSense rules

Expected focused frontend impact:
- alert detail target evidence rendering
- bounded recon activity detail/list surface
- SOC Command Center recon summary card or section

## Implementation Phases

1. pfSense severity and response correction
2. Incident/approval noise reduction
3. Distributed-recon aggregation
4. Target evidence and readable descriptions
5. Allow-after-deny progression detection
6. UI/notification integration
7. Verification and VM handoff

## Verification Plan

- prove reputation alone cannot create `high` from minimum-threshold commodity scanning
- prove real breadth/volume/corroboration can still create `high`
- prove routine distributed recon no longer creates one P2 incident/approval per source
- prove underlying alerts remain preserved when enrolled into an aggregate
- prove aggregate membership requires target/service overlap and does not rely on time alone
- prove unrelated same-window activity stays outside the aggregate
- prove sample destination IPs/ports are deterministic, accurate, and bounded
- prove canonical scan descriptions are grammatically and technically correct
- prove allow-after-deny true-positive and false-positive scenarios
- prove no path auto-blocks without approval
- prove notification dedup/update behavior for aggregate open/update flows
- prove Severity Matrix and playbook behavior match the new pfSense response model
- run focused backend/frontend tests, migration/schema validation, `openspec validate --strict`, and `git diff --check`

## Open Questions

- Whether the protected destination range key should be derived from explicit future inventory metadata or use a normalized public `/24` bucket initially.
- Whether aggregate severity should be stored directly or derived on read from member alerts plus aggregate state.
- Whether recon activities should appear as a dedicated workspace entry or a bounded Incident-adjacent panel first.
