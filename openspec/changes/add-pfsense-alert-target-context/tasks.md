## 1. OpenSpec And Contract

- [x] 1.1 Add the `pfsense-alert-target-context` capability spec describing the persisted `context.target_context` contract, per-alert-family behavior, and Alert Details rendering requirements.
- [x] 1.2 Validate `add-pfsense-alert-target-context` with `openspec validate --strict` before implementation begins.

## 2. Backend Target Context Snapshot

- [x] 2.1 Add `target_context` snapshots to `pfsense_firewall_repeated_deny` and `pfsense_firewall_suspicious_allow` using their existing single-target fields.
- [x] 2.2 Add deterministic top-target aggregation and `target_context` snapshots to `pfsense_firewall_port_scan` and `pfsense_firewall_noisy_source` without changing detection behavior.
- [x] 2.3 Preserve existing top-level pfSense context keys and existing alert API transport while exposing the additive `target_context` shape.

## 3. Frontend Target Context Rendering

- [x] 3.1 Add a compact read-only `Target Context` section to `AlertDetailsPanel` for pfSense alerts only.
- [x] 3.2 Distinguish exact target fields from aggregate top-target fields and render `Unavailable` only when no target evidence exists.
- [x] 3.3 Preserve the existing `Why this fired` section, non-pfSense behavior, and narrow-layout accessibility.

## 4. Verification

- [x] 4.1 Add detector tests covering `target_context` shape for repeated deny, suspicious allow, port scan, and noisy source.
- [x] 4.2 Add aggregation tests proving top-target correctness for port scan and noisy source.
- [x] 4.3 Add alert API contract coverage confirming existing alert payloads expose the additive `context.target_context` shape.
- [x] 4.4 Add `AlertDetailsPanel` rendering tests for single-target, aggregate-target, unavailable, and non-pfSense cases.
- [x] 4.5 Run focused backend/frontend verification, Python compilation, frontend build, `openspec validate add-pfsense-alert-target-context --strict`, and `git diff --check`.
