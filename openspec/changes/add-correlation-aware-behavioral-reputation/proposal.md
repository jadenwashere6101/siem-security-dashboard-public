## Why

Behavioral reputation currently scores only base detection alert types in `core/ip_helpers.py:get_ip_reputation()`. Correlation alerts such as `spray_then_success_pattern` and `web_to_app_attack_pattern` represent higher-confidence attack patterns, but they contribute 0 directly, so a critical correlation alert can appear behaviorally low-risk when no base signal has been counted for the same source IP.

Naively scoring correlation alerts as normal independent signals would overstate risk because correlation alerts are derived from underlying prerequisite alerts. The scoring model needs to recognize correlation as an escalation signal without creating runaway double-counting.

## What Changes

- Add correlation-aware behavioral reputation scoring for:
  - `correlated_activity`
  - `spray_then_success_pattern`
  - `web_to_app_attack_pattern`
  - `cloud_app_error_pattern`
- Preserve the existing base detection signal scoring exactly.
- Add a capped correlation/escalation bonus on top of the existing base score.
- Cap the maximum correlation bonus per `source_ip` at 8 points.
- Show the applied correlation bonus transparently in `contributing_signals`.
- Preserve the existing `behavioral_reputation` API response shape.
- Do not change alert schemas, database schema, detection logic, correlation matching logic, SOAR behavior, or frontend behavior unless implementation discovers a direct compatibility issue.

## Capabilities

### New Capabilities
- `correlation-aware-behavioral-reputation`: Behavioral reputation can account for correlation alert types through a capped escalation bonus while preserving base signal scoring.

### Modified Capabilities
- `behavioral-reputation`: Existing SIEM behavioral reputation scoring is extended to include a capped correlation bonus and transparent contributing signal details.

## Impact

- Backend scoring helper: `core/ip_helpers.py:get_ip_reputation()`.
- Alert API behavior indirectly, because `/alerts` includes `behavioral_reputation` derived from `get_ip_reputation()`.
- Backend tests for behavioral reputation scoring and alert API response contracts.
- No schema migration is expected.
- No frontend change is expected if `behavioral_reputation.contributing_signals` remains backward-compatible.
