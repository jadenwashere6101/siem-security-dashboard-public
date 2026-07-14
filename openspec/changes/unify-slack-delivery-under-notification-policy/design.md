## Context

The repo now has a real notification-policy path for alert, incident, and route-test Slack sends. That path already owns global enable/disable, minimum severity, alert-vs-incident eligibility, compact-vs-detailed formatting, source normalization, route-specific webhook selection, and append-only `notification_delivery_attempts` evidence. The remaining bypass is playbook `notify_slack`, which is still registered as a generic adapter action in `engines/playbook_registry.py` and executed directly by `engines/playbook_step_executor.py`.

That split creates two operational problems:

- the playbook path can send Slack even when notification policy would suppress it; and
- overlapping playbooks can emit duplicate equivalent Slack messages for one alert because dedup is currently keyed to playbook execution and step index, not notification purpose.

The implementation must fix that without broadening into a general notification framework, without changing detection severity, and without touching the VM or enabling Slack.

## Goals / Non-Goals

**Goals:**
- Make notification policy the single authoritative Slack decision gate for alerts, incidents, route tests, and playbook-originated Slack notifications.
- Preserve the current safety chain: playbook action -> notification policy -> route/format selection -> Slack adapter -> `SOAR_REAL_SLACK_ENABLED` -> HTTP send.
- Define a small bounded purpose/stage contract that allows deterministic deduplication of equivalent messages while preserving intentionally distinct lifecycle updates.
- Reconcile existing core playbooks so notification steps that merely duplicate the immediate policy alert page are removed or reclassified, while distinct containment/outcome messaging remains.
- Reuse existing notification policy storage, APIs, routing, and audit-safe delivery evidence without adding a new generic settings or notification framework.

**Non-Goals:**
- No new notification providers, schedules, escalation chains, or per-rule routing.
- No detection, severity, incident, approval, or containment redesign.
- No database migration unless implementation proves the current delivery-attempt contract cannot safely represent purpose/stage deduplication.
- No VM runtime changes, secret changes, or Slack enablement on Mac.

## Decisions

### 1. Notification policy becomes the only Slack gateway

Decision:
- Add one backend notification-policy send entrypoint that every Slack-producing path uses.
- `notify_for_alert`, `notify_for_incident`, and playbook `notify_slack` will all flow through the same evaluation, route resolution, formatting, adapter execution, and delivery-attempt recording logic.

Rationale:
- The policy service already owns the right routing and suppression semantics.
- Moving playbooks into that path is smaller and safer than adding policy logic to the playbook executor.

Alternatives considered:
- Keep direct playbook adapter calls and duplicate policy checks in the executor. Rejected because policy drift is guaranteed.
- Treat playbook Slack as outside notification policy. Rejected because it is the defect being fixed.

### 2. Bounded notification purposes drive deduplication

Decision:
- Introduce a closed purpose/stage vocabulary in the policy service:
  - `immediate_alert`
  - `incident_created`
  - `investigation_update`
  - `containment_outcome`
  - `route_test`
- Deduplication keys will include object kind/id, purpose, route key, and delivery stage, instead of only alert/incident kind plus Slack format.

Rationale:
- Equivalent messages must collapse across multiple playbook executions for the same alert.
- Distinct lifecycle messages must remain independently deliverable.

Alternatives considered:
- Free-form purpose strings in playbooks. Rejected because they make dedup non-deterministic.
- Dedup by raw message text. Rejected because formatting changes would break the contract.

### 3. Reuse notification_delivery_attempts for authoritative duplicate checks

Decision:
- Reuse `notification_delivery_attempts` as the authoritative dedup evidence store.
- Extend recorded metadata/idempotency inputs to include `notification_policy`, `event_kind`, `purpose`, `delivery_stage`, and `route_key`.
- Look for existing `success` or `pending` attempts with the same policy dedup key before sending.

Rationale:
- The store already provides append-only, audit-safe evidence and sanitized metadata.
- This avoids a new table and keeps duplicate suppression observable.

Alternatives considered:
- Add a new dedup table. Rejected as unnecessary scope.
- Dedup only inside a single playbook execution. Rejected because overlapping playbooks are the real defect.

### 4. Playbook Slack steps are classified, not all preserved

Decision:
- Core playbook `notify_slack` steps that only repeat the immediate alert page will be removed from the playbook definition or converted to a policy-routed `investigation_update` only when they add lifecycle value.
- Distinct outcome messaging, such as the post-approval containment update in `core-v1-spray-success-response`, remains as a policy-routed `containment_outcome`.

Rationale:
- Routing duplicate text through policy and then deduplicating it is weaker than deleting unnecessary duplicate steps.
- A retained containment outcome is operationally different from an initial alert page.

Alternatives considered:
- Leave all playbook steps untouched and rely on dedup alone. Rejected because it preserves redundant content and complexity.

### 5. Legacy generic Slack remains only for explicit non-policy/manual tests

Decision:
- Notification-policy sends must continue to use only route-specific webhooks and must not fall back to `SLACK_WEBHOOK_URL`.
- The generic webhook path remains only for existing non-policy/manual integration tests that intentionally exercise the legacy Slack adapter contract.

Rationale:
- This preserves the audited webhook-routing safety model while avoiding unrelated breakage in legacy integration smoke tests.

## Risks / Trade-offs

- [Policy unification could break existing playbook delivery evidence] -> Mitigation: preserve append-only delivery attempts and keep playbook execution step entries explicit about policy suppression, duplicate skip, or adapter outcome.
- [Dedup keys could over-collapse distinct lifecycle messages] -> Mitigation: require bounded purpose plus delivery stage and keep containment outcomes on a distinct purpose.
- [Reconciliation of seeded core playbooks could drift from persisted playbook rows] -> Mitigation: update the idempotent core playbook reconciliation path and verify it remains idempotent.
- [Legacy tests may still assume direct Slack adapter execution for playbooks] -> Mitigation: update only the affected tests and keep the non-policy/manual adapter path unchanged.
- [Suppression could accidentally fail a playbook] -> Mitigation: policy suppression must return a successful non-terminal playbook step outcome with explicit skipped/suppressed evidence, not a hard failure.

## Migration Plan

- Preferred implementation has no migration.
- Reuse `notification_policy` and `notification_delivery_attempts`.
- If implementation proves that current status/action/idempotency fields cannot safely represent purpose/stage-aware policy deduplication without schema change, stop and report the exact blocking reason before adding any migration.
- Rollback path is code-only: remove playbook policy routing and restore direct `notify_slack` execution, leaving existing additive delivery-attempt evidence rows harmless.

## Open Questions

- Whether the smallest implementation should expose purpose explicitly in playbook step params for retained core playbooks, or derive it centrally from playbook id + step position for now.
- Whether any existing non-core custom playbooks in persisted data need a safe default purpose classification beyond `investigation_update`.
