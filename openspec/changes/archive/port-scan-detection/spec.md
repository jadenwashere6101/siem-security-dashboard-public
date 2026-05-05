# Port Scan Detection Specification

## Detection Rule

Trigger a detection when:

- `event_type = port_scan`
- 2 or more matching events exist
- Events share the same `source_ip`

Current implementation threshold:
- 2 or more `port_scan` events from the same IP

---

## Data Source

Detection reads from the `events` table in PostgreSQL.

Relevant fields:

| Field       | Description |
|------------|------------|
| event_type | Event category used for rule filtering |
| source_ip  | Originating IP address used for grouping |
| created_at | Timestamp of event creation |

---

## Detection Logic

1. Query events where:
   - `event_type = 'port_scan'`

2. Group events by:
   - `source_ip`

3. Count matching events for each IP

4. If count >= 2:
   - Trigger port scan detection

---

## Alert Creation

When detection is triggered, create an alert with the following values:

| Field       | Value |
|------------|------|
| alert_type | `port_scan_threshold` |
| severity   | `medium` |
| source_ip  | Detected IP |
| message    | `"<count> port scan events detected from <IP>"` |
| status     | `open` |

---

## Duplicate Prevention

Before creating a new alert, check for an existing alert where:

- `source_ip` matches
- `alert_type = port_scan_threshold`
- `status = open`

If such an alert exists:
- Do NOT create another alert

---

## Execution Model

Detection runs in two ways:

### 1. Scheduled Execution
- Triggered periodically through APScheduler

### 2. Immediate Execution
- Triggered during the ingestion flow after a new event is accepted and stored

---

## Expected System Behavior

- Valid `port_scan` events are stored in the `events` table
- Detection identifies repeated `port_scan` activity by IP
- A single open `medium` severity alert is created per IP
- Additional open duplicates are prevented until the alert is resolved

---

## Notes

- Current implementation does not apply a time window to port scan detection
- Detection is based on repeated `port_scan` event count from the same `source_ip`