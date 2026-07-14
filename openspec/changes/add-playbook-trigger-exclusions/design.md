## Context

The current playbook engine evaluates a flat `trigger_config` against alert fields using AND semantics over a fixed set of recognized keys. Missing keys are treated as match-all, and unknown keys are ignored. `core-v1-reputation-investigation` therefore matches any alert whose severity and reputation meet its thresholds, including pfSense alerts that already route into dedicated pfSense playbooks.

The overlap is architectural, not channel-specific. The same pfSense alert can create both the generic reputation execution and the dedicated pfSense execution. That means duplicate orchestration work even if one notification step is muted. The fix must narrow matching, not just suppress one side effect.

Constraints:

- Keep the playbook engine and existing trigger model.
- Do not redesign SOAR routing or reputation scoring.
- Do not add schema changes.
- Keep `pfsense_firewall_noisy_source` eligible for the generic reputation playbook because no dedicated pfSense playbook owns it today.

## Goals / Non-Goals

**Goals:**

- Add one minimal negative-scope trigger primitive for alert-type exclusions.
- Prevent generic playbooks from matching alert types already owned by dedicated playbooks.
- Preserve the generic reputation playbook's reusable behavior for all non-excluded alert types.
- Fail closed on malformed exclusion configuration.

**Non-Goals:**

- Redesign the playbook engine into a richer query language.
- Add include/exclude support for arbitrary fields.
- Change Slack behavior as the primary fix.
- Tune pfSense detections, reputation thresholds, or AbuseIPDB logic.
- Introduce database migrations or new tables.

## Decisions

### Add `exclude_alert_types` as an optional trigger key

Use one new trigger key:

```json
{
  "reputation_score_min": 40,
  "min_severity": "low",
  "exclude_alert_types": [
    "pfsense_firewall_port_scan",
    "pfsense_firewall_repeated_deny",
    "pfsense_firewall_suspicious_allow"
  ]
}
```

Rationale:

- It preserves the current generic trigger shape and adds only the missing negative scope.
- It removes overlap without enumerating every alert type the reputation playbook is allowed to see.
- It scales cleanly when dedicated playbooks own small subsets of alert types but generic playbooks remain broad by design.

Alternative rejected: removing `notify_slack`. That only hides duplicate notifications and still leaves duplicate playbook executions and overlapping automation history.

Alternative rejected: increasing `reputation_score_min` or `min_severity`. That changes behavior based on current data distribution instead of fixing the ownership boundary.

Alternative rejected: positive `alert_type` allowlist. That makes the generic reputation playbook less reusable, requires constant maintenance, and inverts the intended architecture.

### Evaluate exclusions before positive criteria

Matcher behavior should fail immediately when `alert.alert_type` is in `exclude_alert_types`, then continue with the existing AND evaluation for the remaining supported keys.

Rationale:

- It is the clearest mental model: excluded types never enter the rest of the trigger.
- It avoids accidental partial matches that look valid in logs or tests.
- It keeps the implementation local to the existing trigger evaluator.

### Tighten validation only for the new field

Definition-save validation should continue accepting object-shaped `trigger_config`, but it must validate `exclude_alert_types` when present:

- array only
- non-empty strings only
- case-insensitive comparison at match time
- duplicates rejected or normalized consistently

The rest of trigger validation should remain unchanged for this change.

Rationale:

- This is the minimum needed to make exclusions predictable.
- It avoids turning a small fix into a broad trigger-language rewrite.

### Update only the initial consumer that needs it

The first and only seeded consumer in this change is `core-v1-reputation-investigation`. Its exclusions must be exactly:

- `pfsense_firewall_port_scan`
- `pfsense_firewall_repeated_deny`
- `pfsense_firewall_suspicious_allow`

`pfsense_firewall_noisy_source` remains eligible because no dedicated pfSense playbook owns it.

Rationale:

- The overlap was verified only for these owned pfSense alert types.
- This keeps the change incremental and evidence-based.

## Risks / Trade-offs

- `[Unknown trigger keys are currently ignored]` → Validate `exclude_alert_types` explicitly and document that the change adds one recognized key rather than relying on informal config.
- `[Future teams may overuse exclusions instead of designing clear ownership]` → Document exclusions as a narrow boundary tool for generic-vs-dedicated overlap, not a substitute for playbook design.
- `[Ownership can drift if new dedicated pfSense playbooks are added later]` → Add documentation and tests around the current exclusion list, and treat future additions as explicit follow-up changes.
- `[Case or formatting mismatches in alert types could cause silent misses]` → Define case-insensitive matching and reject blank values.

## Migration Plan

No database migration is required.

Implementation rollout:

1. Add trigger validation and matching support for `exclude_alert_types`.
2. Update the seeded `core-v1-reputation-investigation` definition.
3. Run focused backend tests for route validation, matcher behavior, and seeded playbook matching.
4. Deploy as a normal backend source-only change when explicitly authorized.

Rollback:

- Revert the source change and redeploy the previous backend commit.
- No schema or persisted data rollback is needed.

## Open Questions

- None for this scoped change. The exclusion list and the initial consumer are already verified.
