## 1. Ingest Preparation

- [ ] 1.1 Update the ingest event whitelist to accept `env_probe`, `admin_probe`, `scanner_detected`, and `credential_stuffing`.
- [ ] 1.2 Add honeypot credential payload validation that rejects raw `password` keys before storage.
- [ ] 1.3 Confirm accepted honeypot events can be stored through the normalized ingest path with `source` and `source_type` preserved from the normalized input.

## 2. Detection Configuration

- [ ] 2.1 Add `honeypot_env_probe_threshold` defaults to `engines/detection_config.py`.
- [ ] 2.2 Add `honeypot_admin_probe_threshold` defaults to `engines/detection_config.py`.
- [ ] 2.3 Add `honeypot_scanner_detected` defaults to `engines/detection_config.py`.
- [ ] 2.4 Add `honeypot_credential_stuffing_threshold` defaults to `engines/detection_config.py`.
- [ ] 2.5 Verify the existing runtime detection rules API can read and update the new rule IDs without frontend changes.

## 3. Detection Engine

- [ ] 3.1 Add an `env_probe` detector that alerts on distinct `raw_payload.path` count per source IP.
- [ ] 3.2 Add an `admin_probe` detector that alerts on distinct `raw_payload.path` count per source IP.
- [ ] 3.3 Add a `scanner_detected` detector that alerts on scanner event count or scanner signature evidence per source IP.
- [ ] 3.4 Add a `credential_stuffing` detector that alerts on distinct `raw_payload.username` count per source IP.
- [ ] 3.5 Ensure each detector avoids duplicate open alerts for the same source IP and alert type.
- [ ] 3.6 Ensure each detector returns alert dictionaries compatible with the existing post-commit handoff flow.

## 4. Dispatch

- [ ] 4.1 Import the new detector functions in `engines/ingest_engine.py`.
- [ ] 4.2 Wire `env_probe` to the env probe detector.
- [ ] 4.3 Wire `admin_probe` to the admin probe detector.
- [ ] 4.4 Wire `scanner_detected` to the scanner detector.
- [ ] 4.5 Wire `credential_stuffing` to the credential stuffing detector.
- [ ] 4.6 Preserve existing correlation fan-out and SOAR handoff return behavior.

## 5. Tests

- [ ] 5.1 Add tests proving each new event type is accepted and stored.
- [ ] 5.2 Add tests proving missing or invalid event types are still rejected.
- [ ] 5.3 Add tests proving raw password payloads are rejected and safe credential metadata is accepted.
- [ ] 5.4 Add tests proving `env_probe` fires at `COUNT(DISTINCT path) >= 3`.
- [ ] 5.5 Add tests proving repeated `env_probe` hits to one path do not fire.
- [ ] 5.6 Add tests proving `admin_probe` fires at `COUNT(DISTINCT path) >= 3`.
- [ ] 5.7 Add tests proving repeated `admin_probe` hits to one path do not fire.
- [ ] 5.8 Add tests proving `scanner_detected` fires at the configured threshold.
- [ ] 5.9 Add tests proving `credential_stuffing` fires at `COUNT(DISTINCT username) >= 5`.
- [ ] 5.10 Add tests proving repeated credential attempts for one username do not fire.
- [ ] 5.11 Add tests proving detection config overrides affect at least one honeypot rule.
- [ ] 5.12 Add tests proving honeypot alerts are returned in `alerts_created` for normal post-commit SOAR handoff.

## 6. Verification

- [ ] 6.1 Run `python3 -m py_compile routes/ingest_routes.py engines/ingest_engine.py engines/detection_engine.py engines/detection_config.py`.
- [ ] 6.2 Run focused pytest for honeypot ingest and detection tests.
- [ ] 6.3 Run focused regression pytest for existing ingest and detection tests touched by dispatch/config changes.
- [ ] 6.4 Confirm no database schema migration was added unless explicitly justified.
- [ ] 6.5 Confirm no frontend, SOAR worker, playbook, approval gate, integration adapter, deployment, Azure, or honeypot repo files changed.
- [ ] 6.6 Do not commit or push until the spec and implementation are reviewed.
