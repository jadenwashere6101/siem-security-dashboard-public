## 1. Audit Current Reputation Behavior

- [ ] 1.1 Re-read `core/ip_helpers.py:get_ip_reputation()` and confirm the existing base detection weights, active blocklist weight, score labels, and contributing signal shape.
- [ ] 1.2 Identify existing tests that assert behavioral reputation scoring or `/alerts` API `behavioral_reputation` output.
- [ ] 1.3 Confirm frontend consumers tolerate additive fields inside `behavioral_reputation.contributing_signals` or choose a numeric-compatible signal shape if needed.

## 2. Implement Correlation Bonus

- [ ] 2.1 Add correlation alert type bonus configuration for `correlated_activity`, `spray_then_success_pattern`, `web_to_app_attack_pattern`, and `cloud_app_error_pattern`.
- [ ] 2.2 Query correlation alert counts for the requested `source_ip` without changing existing base detection query semantics.
- [ ] 2.3 Compute `raw_correlation_bonus` from configured correlation bonuses.
- [ ] 2.4 Apply `correlation_bonus = min(raw_correlation_bonus, 8)`.
- [ ] 2.5 Add the capped correlation bonus to the existing base reputation score.
- [ ] 2.6 Add a transparent correlation bonus entry to `contributing_signals` when correlation alerts contribute points.
- [ ] 2.7 Preserve existing reputation field names, label thresholds, base signal entries, and summary behavior unless tests require a narrowly scoped adjustment.

## 3. Tests

- [ ] 3.1 Add or update tests proving base detection scoring remains unchanged.
- [ ] 3.2 Add a correlation-only test proving a single `spray_then_success_pattern` contributes the configured capped-bonus path.
- [ ] 3.3 Add a base-plus-correlation test proving the final score is base score plus applied correlation bonus.
- [ ] 3.4 Add a cap test proving multiple correlation alerts cannot contribute more than 8 total correlation points.
- [ ] 3.5 Add a contributing-signals test proving the applied bonus, raw bonus, cap, cap-applied state, and contributing correlation alert types are visible.
- [ ] 3.6 Update `/alerts` API contract tests only if the behavioral reputation response assertion needs to account for the new correlation signal.

## 4. Verification

- [ ] 4.1 Run `python3 -m py_compile core/ip_helpers.py routes/alerts_events_routes.py`.
- [ ] 4.2 Run focused backend tests covering behavioral reputation and alerts API contracts.
- [ ] 4.3 Run `git diff --check`.
- [ ] 4.4 Run `git status --short`.
- [ ] 4.5 Do not commit or push until the implementation is reviewed.
