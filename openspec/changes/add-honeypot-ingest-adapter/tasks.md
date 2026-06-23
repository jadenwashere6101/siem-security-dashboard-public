## 1. Adapter Contract

- [ ] 1.1 Add `POST /ingest/honeypot` to the existing ingest blueprint.
- [ ] 1.2 Enforce the existing ingest API key guard before parsing or normalizing honeypot payloads.
- [ ] 1.3 Define the adapter allowlist: `env_probe`, `admin_probe`, `scanner_detected`, `credential_stuffing`, and `http_error`.
- [ ] 1.4 Reject invalid JSON, missing `event_type`, missing `source_ip`, invalid `source_ip`, and unsupported event types.

## 2. Normalization

- [ ] 2.1 Map flat honeypot payloads into the `ingest_normalized_event()` contract.
- [ ] 2.2 Stamp `source="honeypot"` and `source_type="honeypot"` internally.
- [ ] 2.3 Map input `timestamp` to normalized `event_timestamp`.
- [ ] 2.4 Generate severity from the adapter's event-type severity mapping.
- [ ] 2.5 Generate safe analyst-facing messages without echoing raw request bodies or credentials.
- [ ] 2.6 Generate `app_name` and `environment`, defaulting safely when omitted.
- [ ] 2.7 Preserve known honeypot fields in `raw_payload`.
- [ ] 2.8 Preserve future safe honeypot metadata in `raw_payload`.

## 3. Credential Safety

- [ ] 3.1 Reject top-level `password` fields before calling `ingest_normalized_event()`.
- [ ] 3.2 Reject nested `password` fields before calling `ingest_normalized_event()`.
- [ ] 3.3 Allow safe credential metadata: `username`, `password_length`, and `credential_present`.
- [ ] 3.4 Ensure validation errors do not log or return raw credential values.

## 4. http_error Handling

- [ ] 4.1 Normalize honeypot `http_error` as SIEM `http_error`.
- [ ] 4.2 Confirm implementation does not translate honeypot `http_error` into `normal_activity`, `env_probe`, or `admin_probe`.
- [ ] 4.3 Confirm `http_error` reaches the existing normalized ingest dispatch without schema or detection engine changes beyond any already-approved event support.

## 5. Flow Preservation

- [ ] 5.1 Reuse `ingest_normalized_event()` for storage and detection dispatch.
- [ ] 5.2 Reuse the existing route-level transaction commit pattern.
- [ ] 5.3 Reuse existing post-commit SOAR enqueue, incident creation, and playbook scheduling calls.
- [ ] 5.4 Confirm no SOAR worker, approval gate, playbook, queue, protected-target, integration adapter, correlation, frontend, or schema files are changed for this adapter.

## 6. Tests

- [ ] 6.1 Add tests for valid API key, missing API key, and wrong API key.
- [ ] 6.2 Add tests for accepting each supported honeypot event type.
- [ ] 6.3 Add tests for rejecting unsupported event types.
- [ ] 6.4 Add tests for rejecting missing or invalid `source_ip`.
- [ ] 6.5 Add tests proving `source` and `source_type` are stamped as `honeypot`.
- [ ] 6.6 Add tests proving `timestamp` maps to `event_timestamp`.
- [ ] 6.7 Add tests proving severity, message, app name, and environment are generated.
- [ ] 6.8 Add tests proving known and future safe metadata are preserved in `raw_payload`.
- [ ] 6.9 Add tests proving top-level and nested raw password fields are rejected.
- [ ] 6.10 Add tests proving safe credential metadata is accepted.
- [ ] 6.11 Add tests proving honeypot `http_error` remains normalized `http_error`.
- [ ] 6.12 Add tests proving returned alerts still flow through `alerts_created`.

## 7. Verification

- [ ] 7.1 Run `python3 -m py_compile routes/ingest_routes.py helpers/ingest_normalizers.py engines/ingest_engine.py`.
- [ ] 7.2 Run focused pytest for the honeypot adapter route.
- [ ] 7.3 Run focused regression pytest for existing ingest route contracts.
- [ ] 7.4 Confirm no schema migration was added.
- [ ] 7.5 Confirm no frontend, honeypot repo, SOAR worker, approval, playbook, queue, protected-target, integration adapter, or correlation behavior changed.
- [ ] 7.6 Do not commit or push until reviewed.
