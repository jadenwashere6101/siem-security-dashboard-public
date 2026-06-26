# Honeypot SIEM Integration

Status: planned

This document tracks the SIEM-side contract for the standalone Flask honeypot integration.

## Planned Ingest Route

- Route: `/ingest/honeypot`
- Auth: `X-API-Key` required
- Source stamping: SIEM adapter sets `source="honeypot"` and `source_type="honeypot"`
- Password handling: raw passwords must be rejected and never stored

## Planned Event Types

| Event Type | Purpose | Detection |
| --- | --- | --- |
| `env_probe` | Sensitive file path probing | `COUNT(DISTINCT path) >= 3` in 10 minutes |
| `admin_probe` | Admin panel path probing | `COUNT(DISTINCT path) >= 3` in 10 minutes |
| `scanner_detected` | Known scanner User-Agent | Immediate alert |
| `credential_stuffing` | Many usernames from one source IP | `COUNT(DISTINCT username) >= 5` in 15 minutes |

## Planning Files

- Human roadmap: `/Users/jadengomez/Desktop/HONEYPOT/honeypot-roadmap-v4.html`
- Implementation checklist: `/Users/jadengomez/Desktop/HONEYPOT/HONEYPOT_IMPLEMENTATION.md`
- AI handoff: `/Users/jadengomez/Desktop/HONEYPOT/AI_HANDOFF.md`
- Location map: `/Users/jadengomez/Desktop/HONEYPOT/HONEYPOT_LOCATIONS.txt`
