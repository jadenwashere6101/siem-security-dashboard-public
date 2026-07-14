## Why

Alert severities are now normalized, but notification behavior is still too tightly coupled to whichever playbook or detection path happens to emit Slack today. That makes routing and paging behavior harder to reason about, harder to tune at runtime, and less representative of a real SOC where notification policy is separate from detection logic.

## What Changes

- Define one notification-policy capability that consumes existing alert severity and alert source instead of duplicating rule logic.
- Add runtime-configurable notification policy controls for Slack enabled/disabled, minimum notification severity, notify-on-alerts, notify-on-incidents, Slack format, and source-to-channel labels.
- Design source-based Slack routing with exactly two initial destinations: pfSense and honeypot.
- Limit Slack formatting to two bounded modes: compact and detailed.
- Keep channel names runtime configurable while preventing arbitrary per-rule routing, custom templates, or additional providers in this change.
- Reuse existing runtime configuration and integration patterns where possible, while keeping detection, SOAR guardrails, RBAC, and audit boundaries intact.

## Capabilities

### New Capabilities
- `notification-policy-and-slack-routing`: defines runtime notification policy, source-based Slack routing, compact vs detailed Slack formatting, operator configuration surfaces, and bounded delivery behavior driven by existing alert severity and source metadata.

### Modified Capabilities
- `source-aware-detection-evaluation`: clarify that downstream notification policy consumes the alert source already produced by source-aware alert creation rather than introducing a second routing source of truth.

## Impact

- **Affected backend:** notification policy service/helper layer, Slack notification integration path, runtime configuration read/write path, alert/incident notification entrypoints, and audit-safe routing/formatting helpers.
- **Affected frontend:** admin/runtime configuration UI and notification settings UI for super-admin operators.
- **Affected APIs:** likely additive admin/runtime configuration endpoints for reading and updating notification policy.
- **Affected database/migrations:** one small additive migration for a dedicated `notification_policy` table with a single authoritative current-policy row and typed non-secret columns.
- **Affected auth/session:** super-admin mutation, analyst-or-better read visibility if existing admin/runtime patterns allow it.
- **Unaffected by design:** detection thresholds, severity normalization, per-rule routing, Teams/Email/Webhook/PagerDuty delivery, notification history redesign, VM runtime work, and source code implementation in this planning change.
