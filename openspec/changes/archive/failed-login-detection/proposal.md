# Failed Login Detection Proposal

## Problem
Repeated failed login attempts may indicate brute force attacks, but raw logs do not provide structured detection.

## Solution
Implement a rule that triggers an alert when 3 or more failed login events occur from the same IP within a 15-minute window.

## Scope
- Event ingestion
- Detection logic
- Alert creation

## Success Criteria
- Alerts are triggered only when threshold is met
- Duplicate alerts are prevented
- Detection resets after time window
