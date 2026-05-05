# Correlation Debug Polish Spec

## Feature Overview

This change improves observability and debugging for the multi-source correlation engine.

The goal is to make it clear when correlation runs, why it creates a `correlated_activity` alert, and why it skips creating one.

## Current State

- The backend now creates `correlated_activity` alerts.
- Correlation currently requires:
  - at least 2 qualifying alerts
  - at least 2 different `alert_type` values
  - at least 2 different known `source` values
- The UI now displays correlation alerts clearly.
- Correlation logging is currently minimal.

## Requirements

1. Add clear backend logging when correlation evaluates an IP
   - log when correlation evaluation starts for a `source_ip`
   - keep logs concise and structured enough for troubleshooting

2. Log skip reasons
   - log when correlation is skipped because of:
     - not enough qualifying alerts
     - not enough distinct alert types
     - not enough distinct known sources
     - duplicate open `correlated_activity` alert already exists
     - alerts exist but not within the correlation window

3. Log success details
   - log:
     - `source_ip`
     - linked alert count
     - distinct alert types
     - distinct sources

4. Add a debug/test document
   - add:
     - `openspec/changes/correlation-debug-polish/debug-test.md`
   - include an exact repeatable manual test:
     - trigger `bank_app` `failed_login_threshold`
     - trigger `nginx` `http_error_threshold`
     - verify `correlated_activity`
   - ensure the test uses a fresh IP each time to avoid duplicate suppression interference

5. Preserve current behavior
   - do not change:
     - correlation logic
     - schema
     - frontend
     - ingestion
     - detection thresholds

6. Logging format standard
   - all correlation logs must use a consistent prefix:
     - `[CORRELATION]`
   - example patterns:
     - `[CORRELATION] Evaluating IP: <source_ip>`
     - `[CORRELATION] Skipped: <reason> | IP: <source_ip>`
     - `[CORRELATION] Success | IP: <source_ip> | alerts=<count> | types=<types> | sources=<sources>`

7. Logging levels
   - use:
     - `INFO` for evaluation start and success
     - `DEBUG` for detailed counts and intermediate data when needed
     - `WARNING` for skip reasons

## Non-Goals

- No schema changes
- No frontend changes
- No new correlation rules
- No ingestion changes
- No threshold changes
- No broad logging redesign
- No analytics dashboard for correlation logs

## Acceptance Criteria

1. Logs clearly explain correlation decisions.
2. The debug document contains repeatable manual test steps.
3. Existing correlation behavior remains unchanged.
4. Syntax check passes.

## Risks and Mitigations

- Risk: noisy logs
  - Mitigation: keep logging focused on evaluation, skip reasons, and success outcomes only

- Risk: accidentally changing correlation behavior while adding observability
  - Mitigation: limit the change to logging and documentation only, without altering decision conditions

- Risk: sensitive data leakage in logs
  - Mitigation: log only the needed fields such as `source_ip`, counts, and alert/source categories, not full payloads or raw event bodies
