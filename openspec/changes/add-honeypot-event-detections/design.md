## Context

The SIEM already has a normalized ingest path that stores events in `events`, keeps source-specific metadata in `raw_payload`, runs detection functions from `engines/ingest_engine.py`, and returns created alerts to the route for post-commit SOAR enqueue, incident creation, and playbook scheduling. Detection rules are runtime configurable through `engines/detection_config.py`.

This change prepares only the SIEM side for a future standalone Flask honeypot. It must not create the honeypot repo, deploy services, open port `8080`, change approval gates, or change SOAR worker/playbook behavior.

## Goals / Non-Goals

**Goals:**

- Add SIEM support for four honeypot event types: `env_probe`, `admin_probe`, `scanner_detected`, and `credential_stuffing`.
- Store honeypot-specific fields in `raw_payload` and query those fields from detection functions.
- Detect `env_probe` and `admin_probe` by distinct path count per `source_ip`, not repeated hits to one path.
- Detect `credential_stuffing` by distinct username count per `source_ip` using safe metadata only.
- Keep defaults configurable through the existing `detection_config` model and preserve dashboard runtime configurability.
- Preserve normal alert creation and post-commit SOAR handoff behavior.

**Non-Goals:**

- No database schema change unless implementation proves JSONB is insufficient.
- No frontend change unless the existing generic detection rules UI cannot display new backend defaults.
- No change to integration adapters, SOAR worker, approval gates, playbooks, protected-target policy, or deployment.
- No honeypot application code or repository creation.

## Decisions

### Event Types

Add these accepted event types:

| Event Type | Purpose |
| --- | --- |
| `env_probe` | Sensitive file path probing, such as `/.env` or configuration file attempts. |
| `admin_probe` | Admin panel path probing, such as `/admin`, `/wp-admin`, or `/phpmyadmin`. |
| `scanner_detected` | Known scanner User-Agent or signature observed by the honeypot. |
| `credential_stuffing` | Login attempts using many distinct usernames from one source IP. |

### Expected raw_payload Fields

Use existing `events.raw_payload` JSON for honeypot-specific metadata:

| Field | Applies To | Notes |
| --- | --- | --- |
| `path` | `env_probe`, `admin_probe`, optional `scanner_detected` | Normalize to a non-empty path string before detection. |
| `method` | all HTTP-originated events | Optional metadata. |
| `user_agent` | all event types | Used for scanner evidence where available. |
| `scanner_signature` | `scanner_detected` | Optional normalized scanner name or matched signature. |
| `username` | `credential_stuffing` | Safe to store after trimming; used for distinct counting. |
| `password_length` | `credential_stuffing` | Safe integer metadata. |
| `credential_present` | `credential_stuffing` | Boolean marker; does not include secret material. |
| `location` | all event types | Existing optional location shape used by alert enrichment. |

Raw `password` MUST NOT be stored in `raw_payload`, alerts, logs, or messages. The ingest path for honeypot events must reject payloads containing a top-level `password` key or `raw_payload.password`.

### Detection Rule IDs and Defaults

Add these defaults to `get_detection_rule_defaults()`:

| Rule ID | Default Parameters | Severity | Behavior |
| --- | --- | --- | --- |
| `honeypot_env_probe_threshold` | `threshold=3`, `window_minutes=10` | `high` | Distinct sensitive paths per source IP. |
| `honeypot_admin_probe_threshold` | `threshold=3`, `window_minutes=10` | `medium` | Distinct admin paths per source IP. |
| `honeypot_scanner_detected` | `threshold=1`, `window_minutes=10` | `medium` | Scanner event count or signature presence per source IP. |
| `honeypot_credential_stuffing_threshold` | `threshold=5`, `window_minutes=15` | `high` | Distinct usernames per source IP. |

These IDs should follow the existing runtime configuration validation bounds. No special parameter type is needed beyond integer `threshold` and `window_minutes`.

### Detection Logic

`env_probe`:

- Query `events` where `event_type = 'env_probe'`.
- Extract `NULLIF(LOWER(TRIM(raw_payload->>'path')), '')` as the normalized path.
- Group by `source_ip`.
- Alert when `COUNT(DISTINCT normalized_path) >= threshold` within the configured window.
- Repeated requests to the same path must not satisfy the rule alone.

`admin_probe`:

- Same structure as `env_probe`, using `event_type = 'admin_probe'`.
- Alert on distinct admin paths per `source_ip`.

`scanner_detected`:

- Query `events` where `event_type = 'scanner_detected'`.
- Alert when event count per `source_ip` meets the configured threshold within the configured window.
- Include `user_agent` or `scanner_signature` as evidence when available, but do not require either if the honeypot already classified the event.

`credential_stuffing`:

- Query `events` where `event_type = 'credential_stuffing'`.
- Extract `NULLIF(LOWER(TRIM(raw_payload->>'username')), '')` as the normalized username.
- Group by `source_ip`.
- Alert when `COUNT(DISTINCT normalized_username) >= threshold` within the configured window.
- Ignore rows without a usable username.
- Use only `username`, `password_length`, and `credential_present`; never query or preserve raw passwords.

Each detector should follow the existing pattern: read effective config, skip if inactive if current helpers support inactive rules, avoid duplicate open alerts for the same `source_ip` and `alert_type`, enrich reputation/location consistently, insert an alert, and return alert dictionaries for post-commit handling.

### Ingest / Dispatch Flow

The implementation should add the new event types to the ingest whitelist and route accepted honeypot events through `ingest_normalized_event()`. Dispatch in `engines/ingest_engine.py` should call only the relevant honeypot detector for each honeypot event type, then preserve existing correlation fan-out for any created alerts.

The integration adapter behavior is explicitly out of scope. If a `/ingest/honeypot` adapter already exists or is added in a separate change, it should stamp `source="honeypot"` and `source_type="honeypot"` before calling the normalized ingest engine. This change must not weaken API key validation.

### SOAR Handoff Behavior

No SOAR worker, queue, playbook, approval, adapter, or protected-target code should change. Honeypot detections should return alert dictionaries in the same shape as existing detectors so existing route-level post-commit calls to `enqueue_committed_alerts()`, incident creation, and playbook scheduling continue through the normal alert creation flow.

### Test Strategy

- Ingest acceptance: valid honeypot event types pass whitelist validation and are stored.
- Ingest rejection: invalid event types still fail; raw password fields in honeypot payloads fail.
- Source stamping: stored honeypot events and alerts preserve `source="honeypot"` and `source_type="honeypot"` when supplied by the normalized ingest input.
- Detection thresholds:
  - `env_probe` fires at `COUNT(DISTINCT path) >= 3`.
  - Repeated `env_probe` hits to one path do not fire.
  - `admin_probe` fires at `COUNT(DISTINCT path) >= 3`.
  - Repeated `admin_probe` hits to one path do not fire.
  - `scanner_detected` fires at its configured threshold.
  - `credential_stuffing` fires at `COUNT(DISTINCT username) >= 5`.
- Runtime config: overrides from `detection_config` affect thresholds/windows.
- SOAR preservation: created honeypot alerts are returned in `alerts_created` so existing post-commit handoff tests can prove enqueue behavior remains normal.

## Risks / Trade-offs

- JSONB field extraction is slower than dedicated columns -> keep thresholds and windows small for v1; add indexes or columns later only if real traffic demonstrates a bottleneck.
- Honeypot path strings may include query strings or encoded variants -> normalize conservatively and document any remaining ambiguity.
- Scanner signatures can become stale -> keep the SIEM rule based on honeypot classification and count, leaving signature maintenance to the honeypot project.
- Raw credential handling is high risk -> reject raw password keys and add regression tests before any public honeypot deployment.
- Adding new alert types may affect SOAR volume -> preserve existing approval/protected-target gates and tune thresholds through `detection_config`.

## Migration Plan

Implement as additive backend changes. No schema migration is planned. Rollback by reverting the whitelist, dispatch, defaults, detector functions, and tests added for this change.

## Open Questions

- Should honeypot events enter through the existing `/ingest` route during implementation tests, or should `/ingest/honeypot` be specified in a later adapter-focused change?
- Should `scanner_detected` default severity be `medium` or `high` once real scanner volume is observed?
