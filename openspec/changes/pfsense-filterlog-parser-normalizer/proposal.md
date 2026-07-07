## Why

pfSense firewall ingestion needs a safe parser and normalized event contract before route, listener, detection, or deployment work begins. This child spec turns the parent roadmap's first Phase 3 item into a focused parser/normalizer contract while inheriting the Phase 2.5 threat model.

## What Changes

- Define a parser/normalizer layer for pfSense syslog `filterlog` input.
- Specify syslog envelope handling, `filterlog` payload extraction, UTF-8 safety, unsafe control-character stripping, and the initial 4096-byte packet limit.
- Specify IPv4 TCP and IPv4 UDP parsing, plus safe handling for IPv6, unknown, malformed, oversized, and invalid UTF-8 input.
- Define normalized firewall event fields with `source="pfsense"` and `source_type="firewall"`.
- Propose action-to-taxonomy mapping candidates where `block` maps to future `firewall_block` and `pass` maps to future `firewall_allow`, pending later detection/taxonomy specs.
- Keep this child scope parser/normalizer only: no database writes, Flask route, UDP listener, systemd service, Azure NSG rule, VM firewall change, pfSense handoff, detection rule, commit, or push.

## Capabilities

### New Capabilities
- `pfsense-filterlog-parser-normalizer`: parser and normalized-event contract for safe pfSense syslog/filterlog ingestion.

### Modified Capabilities
- (none)

## Impact

- **Affected code later:** likely a focused adapter/normalizer module under `adapters/` plus unit tests, but no implementation is performed by this spec creation work.
- **Affected APIs:** none in this child spec; any `/ingest/pfsense` route belongs to a later child spec.
- **Affected systems:** no runtime, VM, Azure, network, database, deployment, or pfSense configuration changes.
- **Parent roadmap:** item 6.8 is marked created/in progress with an explicit parser/normalizer-only boundary note.
