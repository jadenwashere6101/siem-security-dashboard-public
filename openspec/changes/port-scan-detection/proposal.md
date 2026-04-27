# Port Scan Detection Rule Proposal

## Purpose
Introduce a detection rule that identifies repeated port scan activity from a single source IP and escalates it into a medium severity alert.

---

## Problem
Individual `port_scan` events may not appear serious on their own, but repeated scans from the same IP can indicate hostile reconnaissance behavior. Without a defined rule, these events are stored but not escalated into alerts.

---

## Proposed Solution
Implement a port scan detection rule that:

- Monitors events where `event_type = port_scan`
- Groups events by `source_ip`
- Triggers when 2 or more `port_scan` events are observed from the same IP
- Generates a `medium` severity alert
- Prevents duplicate open alerts for the same IP and rule

---

## Behavior

- Detection runs in two ways:
  - Scheduled execution via APScheduler
  - Immediate execution after new event ingestion

- When the threshold is met:
  - A new alert is created with:
    - `alert_type = port_scan_threshold`
    - `severity = medium`
    - `source_ip`
    - descriptive message
    - `status = open`

- If an open alert already exists for the same `source_ip` and `alert_type`, a new alert is not created

---

## Scope

This proposal applies to:
- Events stored in the `events` table
- Detection logic in the SIEM backend
- Alert creation for repeated port scan behavior

---

## Out of Scope

- Deep packet inspection
- Frontend visualization changes
- Port-level traffic analysis beyond existing event ingestion

---

## Success Criteria

- Repeated `port_scan` events from a single IP generate a `medium` severity alert
- Duplicate open alerts are prevented
- Detection works both on scheduled runs and immediately after ingestion