## 1. Adapter Contract

- [x] 1.1 Add `POST /ingest/honeypot` to the existing ingest blueprint.
- [x] 1.2 Enforce the existing ingest API key guard before parsing or normalizing honeypot payloads.
- [x] 1.3 Define the adapter allowlist: `env_probe`, `admin_probe`, `scanner_detected`, `credential_stuffing`, and `http_error`.
- [x] 1.4 Reject invalid JSON, missing `event_type`, missing `source_ip`, invalid `source_ip`, and unsupported event types.

## 2. Normalization

- [x] 2.1 Map flat honeypot payloads into the `ingest_normalized_event()` contract.
- [x] 2.2 Stamp `source="honeypot"` and `source_type="honeypot"` internally.
- [x] 2.3 Map input `timestamp` to normalized `event_timestamp`.
- [x] 2.4 Generate severity from the adapter's event-type severity mapping.
- [x] 2.5 Generate safe analyst-facing messages without echoing raw request bodies or credentials.
- [x] 2.6 Generate `app_name` and `environment`, defaulting safely when omitted.
- [x] 2.7 Preserve known honeypot fields in `raw_payload`.
- [x] 2.8 Preserve future safe honeypot metadata in `raw_payload`.

## 3. Credential Safety

- [x] 3.1 Reject top-level `password` fields before calling `ingest_normalized_event()`.
- [x] 3.2 Reject nested `password` fields before calling `ingest_normalized_event()`.
- [x] 3.3 Allow safe credential metadata: `username`, `password_length`, and `credential_present`.
- [x] 3.4 Ensure validation errors do not log or return raw credential values.

## 4. http_error Handling

- [x] 4.1 Normalize honeypot `http_error` as SIEM `http_error`.
- [x] 4.2 Confirm implementation does not translate honeypot `http_error` into `normal_activity`, `env_probe`, or `admin_probe`.
- [x] 4.3 Confirm `http_error` reaches the existing normalized ingest dispatch without schema or detection engine changes beyond any already-approved event support.

## 5. Flow Preservation

- [x] 5.1 Reuse `ingest_normalized_event()` for storage and detection dispatch.
- [x] 5.2 Reuse the existing route-level transaction commit pattern.
- [x] 5.3 Reuse existing post-commit SOAR enqueue, incident creation, and playbook scheduling calls.
- [x] 5.4 Confirm no SOAR worker, approval gate, playbook, queue, protected-target, integration adapter, correlation, frontend, or schema files are changed for this adapter.

## 6. Tests

- [x] 6.1 Add tests for valid API key, missing API key, and wrong API key.
- [x] 6.2 Add tests for accepting each supported honeypot event type.
- [x] 6.3 Add tests for rejecting unsupported event types.
- [x] 6.4 Add tests for rejecting missing or invalid `source_ip`.
- [x] 6.5 Add tests proving `source` and `source_type` are stamped as `honeypot`.
- [x] 6.6 Add tests proving `timestamp` maps to `event_timestamp`.
- [x] 6.7 Add tests proving severity, message, app name, and environment are generated.
- [x] 6.8 Add tests proving known and future safe metadata are preserved in `raw_payload`.
- [x] 6.9 Add tests proving top-level and nested raw password fields are rejected.
- [x] 6.10 Add tests proving safe credential metadata is accepted.
- [x] 6.11 Add tests proving honeypot `http_error` remains normalized `http_error`.
- [x] 6.12 Add tests proving returned alerts still flow through `alerts_created`.

## 7. Verification

- [x] 7.1 Run `python3 -m py_compile routes/ingest_routes.py helpers/ingest_normalizers.py engines/ingest_engine.py`.
- [x] 7.2 Run focused pytest for the honeypot adapter route.
- [x] 7.3 Run focused regression pytest for existing ingest route contracts.
- [x] 7.4 Confirm no schema migration was added.
- [x] 7.5 Confirm no frontend, honeypot repo, SOAR worker, approval, playbook, queue, protected-target, integration adapter, or correlation behavior changed.
- [x] 7.6 Do not commit or push until reviewed.
