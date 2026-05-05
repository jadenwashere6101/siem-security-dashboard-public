# Failed Login Detection Spec

## Rule Definition
Trigger an alert when:
- event_type = failed_login
- count >= 3
- within 15 minutes
- grouped by source_ip

## Data Source
events table:
- event_type
- source_ip
- created_at

## Detection Logic
1. Filter events in last 15 minutes
2. Group by source_ip
3. Count occurrences
4. Trigger alert if count >= 3

## Alert Behavior
- alert_type: failed_login_threshold
- severity: high
- message: "3 failed login attempts detected from <IP>"

## Duplicate Prevention
If an open alert already exists for that IP:
- do NOT create another alert
