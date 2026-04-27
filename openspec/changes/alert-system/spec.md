# Alert System Specification

## Database Table

Alerts are stored in the `alerts` table.

### Fields

| Field      | Type      | Description |
|-----------|-----------|-------------|
| id        | integer   | Primary key |
| alert_type| text      | Rule/type that generated the alert |
| severity  | text      | Alert severity (e.g., high, medium) |
| message   | text      | Human-readable alert description |
| source_ip | inet/text | Source IP associated with the alert |
| status    | text      | Alert state (`open` or `resolved`) |
| created_at| timestamp | Alert creation time |

---

## Alert Creation Rules

An alert is created when a detection rule determines suspicious behavior has occurred.

Examples:
- `failed_login_threshold`
- `port_scan_threshold`

---

## Status Lifecycle

Supported status values:

- `open`
- `resolved`

### Default
New alerts are created with:

- `status = open`

---

## Duplicate Prevention

Before creating a new alert, the SIEM must check whether an existing alert already exists where:

- `source_ip` matches
- `alert_type` matches
- `status = open`

If such an alert exists:
- Do NOT create a new alert

---

## Resolution Behavior

Resolved alerts remain in the database for historical tracking.

Resolving an alert:
- does NOT delete it
- does NOT remove underlying events
- only updates `status` to `resolved`

---

## Expected System Behavior

- Detection rules create alerts
- Alerts remain queryable after creation
- Analysts can distinguish active vs historical alerts using status