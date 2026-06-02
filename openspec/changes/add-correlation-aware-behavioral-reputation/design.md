## Context

`core/ip_helpers.py:get_ip_reputation()` currently computes internal SIEM behavioral reputation from alert history for a `source_ip`. It counts six base detection alert types and active blocklist entries:

- `failed_login_threshold`: 3 points each
- `password_spraying_threshold`: 5 points each
- `successful_login_after_spray`: 6 points each
- `port_scan_threshold`: 4 points each
- `http_error_threshold`: 2 points each
- `high_request_rate_threshold`: 3 points each
- active `blocked_ips`: 6 points each

Labels are derived from the final score:

- `<= 0`: `Normal`
- `<= 4`: `Low Suspicion`
- `<= 9`: `Suspicious`
- `<= 14`: `High Risk`
- `> 14`: `Critical`

Correlation alert types currently contribute no direct score:

- `correlated_activity`
- `spray_then_success_pattern`
- `web_to_app_attack_pattern`
- `cloud_app_error_pattern`

These alerts are higher-confidence escalation signals, but they are usually produced from existing base alerts. Adding their full point values without a cap would double-count the same behavior and could inflate scores unfairly.

## Goals / Non-Goals

**Goals:**

- Keep all existing base detection weights and label thresholds unchanged.
- Add a conservative correlation escalation bonus.
- Cap the total correlation bonus per `source_ip` at 8 points.
- Make the bonus visible in `contributing_signals`.
- Preserve the current `behavioral_reputation` response shape.
- Keep the change scoped to reputation scoring and focused tests.

**Non-Goals:**

- Do not change detection rule logic.
- Do not change correlation matching logic.
- Do not change alert schemas or database schema.
- Do not change SOAR queue, playbook, approval, retry, or audit behavior.
- Do not change external threat-intelligence reputation storage or display.
- Do not redesign frontend reputation components.

## Decisions

### Current Scoring Formula

Today:

```text
base_score =
  failed_login_threshold_count * 3
+ password_spraying_threshold_count * 5
+ successful_login_after_spray_count * 6
+ port_scan_threshold_count * 4
+ http_error_threshold_count * 2
+ high_request_rate_threshold_count * 3
+ active_blocked_ip_count * 6

total_score = base_score
```

The query counts all matching alert rows for the `source_ip` using the current helper semantics. This change should not introduce new status, time-window, or severity filters unless a focused implementation audit proves the current helper already applies them elsewhere.

### Proposed Scoring Formula

Add a separate correlation bonus:

```text
raw_correlation_bonus =
  correlated_activity_count * 4
+ spray_then_success_pattern_count * 5
+ web_to_app_attack_pattern_count * 6
+ cloud_app_error_pattern_count * 4

correlation_bonus = min(raw_correlation_bonus, 8)

total_score = base_score + correlation_bonus
```

Proposed conservative bonuses:

- `correlated_activity`: +4
- `spray_then_success_pattern`: +5
- `web_to_app_attack_pattern`: +6
- `cloud_app_error_pattern`: +4

The 8-point cap prevents multiple correlation alerts derived from the same underlying event chain from causing unbounded score inflation.

### Contributing Signals Behavior

Existing base detection signals should remain unchanged.

When one or more correlation alert types exist for the `source_ip`, `contributing_signals` should include a transparent correlation bonus signal. The signal should preserve the existing fields that consumers already expect and may include extra fields for clarity:

```json
{
  "signal": "correlation_escalation_bonus",
  "label": "Correlation Escalation Bonus",
  "count": 2,
  "weight": "capped",
  "total": 8,
  "raw_total": 11,
  "cap": 8,
  "cap_applied": true,
  "correlation_alert_types": [
    {"alert_type": "web_to_app_attack_pattern", "count": 1, "bonus": 6, "raw_total": 6},
    {"alert_type": "spray_then_success_pattern", "count": 1, "bonus": 5, "raw_total": 5}
  ]
}
```

`total` must represent the applied score contribution, not the uncapped raw score. `raw_total` and `cap_applied` explain when capping reduced the applied score. This keeps the API shape stable while making the cap auditable.

### Score Examples

- Base detection only: unchanged. One `password_spraying_threshold` alert remains 5 points and label `Suspicious`.
- Correlation only: one `spray_then_success_pattern` alert gives 0 base + 5 correlation bonus = 5, label `Suspicious`.
- Base plus correlation: base score 14 plus one `spray_then_success_pattern` gives 14 + 5 = 19, label `Critical`.
- Multiple correlations: one `web_to_app_attack_pattern` and one `spray_then_success_pattern` produce raw bonus 11, capped to 8.

### API Compatibility

The top-level behavioral reputation object should remain stable:

```json
{
  "score": 0,
  "label": "Normal",
  "source": "internal_siem_behavior",
  "summary": "...",
  "contributing_signals": []
}
```

The scoring helper may expose additional optional fields inside a contributing signal, but it must not remove existing signal fields or rename the existing reputation fields. No frontend changes are expected if components render `contributing_signals` generically.

## Risks / Trade-offs

- Score inflation from derived alerts -> Mitigated by applying one capped correlation bonus per source IP.
- Double-counting prerequisite alerts -> Mitigated by preserving base scoring and treating correlation as a capped escalation layer, not another uncapped base signal.
- UI confusion around capped values -> Mitigated by including `raw_total`, `cap`, and `cap_applied` in the correlation contributing signal.
- API consumer assumptions about numeric `weight` -> Mitigate during implementation by checking frontend/tests; use a numeric-compatible representation if consumers require it.
- Historical alert accumulation remains unchanged -> This spec intentionally preserves current helper semantics and does not introduce retention or recency logic.
- Ambiguous severity expectations -> The cap makes correlation meaningful without turning every repeated derived pattern into automatic critical reputation.
