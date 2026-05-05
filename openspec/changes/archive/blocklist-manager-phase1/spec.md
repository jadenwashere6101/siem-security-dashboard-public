# Blocklist Manager Phase 1 Spec

## Feature Overview

This change adds a blocklist manager foundation to the SIEM for safely tracking blocked IPs in the application.

The goal is to let analysts and administrators record, review, and remove blocked IPs with audit logging, without applying real firewall or host-level enforcement in this phase.

## Current State

- Alerts already support response actions such as:
  - `block_ip`
  - `monitor`
  - `flag_high_priority`
- Audit logging already exists.
- Alerts now store `source` and `source_type`.
- There is currently no dedicated `blocked_ips` table.
- There is currently no blocklist manager UI or API.
- Existing `block_ip` behavior is simulated and logged, not enforced.

## Requirements

1. Add table:
   - `blocked_ips`
   - fields:
     - `id SERIAL PRIMARY KEY`
     - `ip_address INET NOT NULL`
     - `reason TEXT`
     - `status TEXT NOT NULL DEFAULT 'active'`
     - `created_by TEXT`
     - `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
     - `expires_at TIMESTAMPTZ NULL`
     - `source_alert_id INTEGER NULL REFERENCES alerts(id) ON DELETE SET NULL`

2. Add backend endpoints:
   - `GET /blocked-ips`
   - `POST /blocked-ips`
   - `PATCH /blocked-ips/<id>/unblock`

3. RBAC:
   - `analyst` and `super_admin` can view the blocklist
   - `analyst` and `super_admin` can add blocked IPs
   - `analyst` and `super_admin` can unblock active entries
   - `viewer` cannot modify blocklist data

4. Validation:
   - require a valid IP address
   - reject empty IP values
   - reject localhost and loopback ranges
   - reject private/internal ranges for now
   - prevent duplicate active block entries for the same IP

5. Audit logging:
   - add audit events:
     - `block_ip_added`
     - `block_ip_removed`
   - audit details should include:
     - IP address
     - reason
     - actor
     - `source_alert_id` when present

6. UI:
   - add a Blocklist Manager panel or table
   - display:
     - IP
     - status
     - reason
     - `created_by`
     - `created_at`
     - `expires_at`
   - add a manual `Add Blocked IP` form
   - add an `Unblock` button for active entries
   - keep styling consistent with the current dark dashboard theme

7. Integration with existing alert action:
   - when the existing `Block IP` action is used from an alert, it should create a `blocked_ips` row
   - it should no longer be only a simulated response log action
   - it must still avoid executing any real firewall or system commands in this phase

8. Do not:
   - run firewall commands
   - modify `ufw`, `iptables`, or `nftables`
   - block SSH
   - change ingestion logic
   - change detection logic
   - add automatic blocking
   - change bank app, nginx, Azure, or OTEL ingestion behavior

## Non-Goals

- No real firewall enforcement
- No host-level networking changes
- No automatic blocking from detectors
- No scheduled block expiration enforcement
- No CIDR/range blocking in v1
- No external firewall integration
- No changes to detection rules
- No ingestion pipeline changes

## Acceptance Criteria

1. `analyst` and `super_admin` can add an IP to the blocklist.
2. Duplicate active block entries are rejected cleanly.
3. Private, loopback, and internal IPs are rejected.
4. Active blocked IPs are visible in the UI.
5. Active entries can be unblocked.
6. Block and unblock actions are written to the audit log.
7. Existing alert `Block IP` action creates a blocklist record.
8. No real firewall rules are applied.

## Risks and Mitigations

- Risk: the feature could imply real enforcement when it is only application-level tracking
  - Mitigation: label it clearly as a SIEM-managed blocklist record, not an active firewall control

- Risk: trusted or internal IPs could be blocked accidentally
  - Mitigation: reject loopback and private/internal ranges in v1

- Risk: duplicate records create operational confusion
  - Mitigation: reject duplicate active blocks for the same IP

- Risk: insufficient audit trail for block and unblock actions
  - Mitigation: require dedicated audit events with actor, IP, reason, and related alert context

- Risk: users may assume blocklist entries are actively enforced at the network level
  - Mitigation: clearly label this as a SIEM-managed blocklist (tracking only) and defer real enforcement to a future firewall integration phase
