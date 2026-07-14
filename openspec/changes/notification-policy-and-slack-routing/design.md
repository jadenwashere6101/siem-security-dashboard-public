## Context

This change is intentionally narrower than the earlier SOAR integration-control work. It is not about proving Slack readiness, adding provider Active toggles, or redesigning delivery history. It is about introducing a policy layer between existing alert/incident production and Slack delivery so the system can answer a simple operational question: given an alert or incident that already exists, should it notify Slack, where should it go, and how much context should it include?

Current repo patterns matter:

- Detection already owns severity and source production. This change must consume those fields rather than recompute them.
- Runtime operator controls in this repo are backend-owned for operational concerns such as detection-rule overrides and pfSense ingest filters, while frontend `uiSettings` is browser-local and not suitable for shared runtime notification policy.
- Slack integration already exists and is guarded; this change should route into that existing path rather than invent a second delivery mechanism, but source-based notification-policy routing must select distinct Slack incoming webhooks rather than rely on cosmetic channel labels.
- Core playbooks already notify Slack directly today, which means notification behavior is partially encoded in playbook content instead of one bounded policy surface.

## Goals / Non-Goals

**Goals:**
- Separate notification policy from detection logic while keeping alert severity as the single source of truth.
- Define one bounded runtime policy model for Slack enabled/disabled, minimum severity, notify-on-alerts, notify-on-incidents, source routing, and format mode.
- Route pfSense and honeypot notifications by existing alert source, with runtime-configurable human-readable destination labels and source-specific webhook secrets kept in environment-backed integration configuration.
- Support only compact and detailed Slack formats, reusing existing alert/investigation context when available.
- Leave room for future sources to plug into the routing map without redesigning the policy model.

**Non-Goals:**
- No new provider types beyond Slack.
- No per-rule routing, arbitrary channel mapping UI, template editor, schedules, quiet hours, escalation chains, or notification-history redesign.
- No detection-threshold or severity changes.
- No VM work, deployment changes, or implementation in this planning change.

## Decisions

### 1. Introduce a notification-policy layer that consumes alert facts, not detector logic

Decision:
- Notification decisions should take an existing alert or incident payload and evaluate only policy inputs already present on that object: `severity`, `source`, object kind (`alert` or `incident`), and available investigation context.

Rationale:
- This preserves severity as the single source of truth and avoids a second copy of “what is urgent.”
- It matches the repo’s existing engineering gate to trace UI/API/backend/database effects without hidden logic forks.

Alternatives considered:
- Recompute severity or urgency inside the notification layer. Rejected because it duplicates detector logic and will drift.
- Keep notification policy embedded in playbook definitions. Rejected because routing and paging become scattered across content instead of one runtime policy.

### 2. Use a bounded source-routing map, not per-rule or arbitrary-channel routing

Decision:
- Routing should key off the existing alert source family, with two initial route keys:
  - `pfsense` -> runtime-configurable pfSense destination label plus `SLACK_PFSENSE_WEBHOOK_URL`
  - `honeypot` -> runtime-configurable honeypot destination label plus `SLACK_HONEYPOT_WEBHOOK_URL`
- Unknown future sources should be able to plug into the same routing map contract later, but this change only defines the two initial sources.

Rationale:
- The user asked for realistic SOC routing without an overbuilt framework.
- Source routing is stable, explainable, and aligns with the repo’s existing source-aware alert model.
- The deployed audit proved that label-only routing is insufficient because a single webhook cannot guarantee delivery to two independent Slack channels.

Alternatives considered:
- Per-rule routing. Rejected as too granular and likely to recreate detector-coupled policy.
- Arbitrary channel mapping UI for any string. Rejected because it expands scope into a generic routing engine.
- Reuse one `SLACK_WEBHOOK_URL` while passing source labels in the payload. Rejected because it does not produce real source-based delivery separation.

### 3. Make notification policy a shared backend runtime configuration concern

Decision:
- The policy should live in the backend runtime configuration surface, not browser-local `uiSettings`.
- The existing durable backend runtime-config patterns were audited and are concern-specific (`detection_config`, `pfsense_ingest_config`), not a generic store.
- Implementation is therefore authorized to add the smallest additive table/API pair following those existing patterns, without introducing a broad generic settings framework.

Approved table shape:
- `notification_policy`
- one authoritative current-policy row
- `slack_enabled`: boolean
- `minimum_notification_severity`: enum `low|medium|high|critical`
- `notify_on_alerts`: boolean
- `notify_on_incidents`: boolean
- `slack_format`: enum `compact|detailed`
- `pfsense_destination`: string routing label
- `honeypot_destination`: string routing label
- `updated_at`: timestamptz
- `updated_by`: text/username when consistent with existing audit patterns

Rationale:
- Runtime operator policy must be shared, durable, auditable, and effective without a frontend-only browser state.
- Deploy-time env vars alone are insufficient because they are not an operator-tunable runtime policy surface.
- Typed columns keep validation explicit and avoid turning this feature into a generic dynamic configuration engine.
- Route-selecting webhook secrets remain outside this table in environment-backed integration configuration so notification policy storage stays non-secret and auditable.

Alternatives considered:
- Store notification policy in frontend settings. Rejected because it is per-browser, unaudited, and not authoritative.
- Store channel names as hardcoded constants. Rejected because the user explicitly wants runtime configurability.
- Reuse `detection_config` or `pfsense_ingest_config`. Rejected because both stores are semantically and structurally scoped to their existing concerns.

### 3a. Route-specific webhook selection is part of real Slack routing

Decision:
- Notification-policy deliveries must pass a canonical route key into the existing Slack adapter.
- For notification-policy sends only:
  - route key `pfsense` must use only `SLACK_PFSENSE_WEBHOOK_URL`
  - route key `honeypot` must use only `SLACK_HONEYPOT_WEBHOOK_URL`
- Missing route-specific webhook configuration must suppress only that route with a clear operational failure reason.
- Notification-policy sends must not fall back from one source webhook to another, and must not fall back to `SLACK_WEBHOOK_URL`.
- Existing non-policy Slack adapter usage may continue using `SLACK_WEBHOOK_URL` so unrelated playbook/test behavior remains unchanged.

Rationale:
- This is the smallest safe correction that produces real source-based routing without introducing a broad notification framework.
- It preserves the user’s requirement that detection, alert, incident, playbook, and notification-policy behavior remain otherwise unchanged.

### 4. Keep formatting bounded to compact and detailed

Decision:
- Compact format should produce a short, high-signal summary suitable for noisy analyst channels.
- Detailed format should include the compact summary plus bounded investigation context when available: severity, rule/alert type, source, MITRE, response action, and target context.

Rationale:
- This gives operators a useful runtime choice without creating a template system.
- It also preserves a clear distinction between “configuration” and “freeform content authoring.”

Alternatives considered:
- Arbitrary template editor or Slack markdown builder. Rejected as out of scope and too hard to validate safely.

### 5. Keep policy evaluation fail-closed and visible

Decision:
- If notification policy cannot be read safely, Slack notification should fail closed rather than guess.
- Outcome evidence should distinguish “policy disabled,” “below minimum severity,” “source not routed,” and “policy unavailable.”

Rationale:
- This aligns with existing guarded integration behavior and avoids accidental real notifications.

Alternatives considered:
- Fall back to direct Slack sends when policy is unavailable. Rejected because it bypasses the feature’s core purpose.

## Risks / Trade-offs

- [Policy spread across playbooks and service layer during transition] -> Mitigation: define one policy-evaluation helper/service and move all Slack delivery entrypoints through it before adding more routing rules.
- [Additive storage introduces a migration] -> Mitigation: keep the table single-purpose, single-row authoritative, typed, non-secret, and additive-only so rollback stays simple and no generic settings framework is created.
- [Route-specific webhook selection could accidentally cross-route or leak a fallback path] -> Mitigation: resolve webhook env names from canonical route keys only, never fall back across sources, and keep secret resolution inside the Slack adapter.
- [Source strings may not normalize cleanly across every current alert producer] -> Mitigation: route from the existing canonical alert source contract and treat unknown sources as non-routed until explicitly added.
- [Detailed formatting could leak too much raw context] -> Mitigation: allowlist fields, reuse existing redaction expectations, and keep format choices bounded.
- [Runtime policy might be mistaken for detection logic] -> Mitigation: specs must state that policy only consumes existing severity and source and never alters alert creation.

## Migration Plan

- Planning-only change: no deployment, VM sync, schema mutation, or source implementation occurs here.
Default policy direction:
- `slack_enabled=false` so current pfSense Slack mute remains preserved until a super-admin explicitly enables policy-driven Slack delivery.
- `minimum_notification_severity=high`
- `notify_on_alerts=true`
- `notify_on_incidents=true`
- `slack_format=compact`
- `pfsense_destination` and `honeypot_destination` default to bounded source labels rather than secrets or webhook values.
- `SLACK_PFSENSE_WEBHOOK_URL` and `SLACK_HONEYPOT_WEBHOOK_URL` are required at runtime for real notification-policy delivery for their respective routes; they are not persisted in the database or exposed through policy APIs.

Intended implementation order:
  1. Add notification policy architecture and shared backend policy service.
  2. Add the dedicated `notification_policy` table, store, and APIs.
  3. Add source-based Slack routing helper and bounded formatters.
  4. Update alert/incident notification entrypoints to call policy evaluation before Slack send.
  5. Add frontend admin/runtime configuration controls.
  6. Run focused backend/frontend validation, build, and visual verification.
- Rollback direction for future implementation:
  - Disable Slack notifications at policy level or revert to current pre-policy behavior behind a guarded feature path.
  - If a new table is introduced, keep it additive so code rollback can ignore it safely.

## Open Questions

- Which existing backend entrypoint should become the single notification-policy gateway for both alert-created and incident-created Slack delivery?
- Should analyst users have read-only visibility into effective notification policy, or should this remain super-admin-only in the runtime UI?
