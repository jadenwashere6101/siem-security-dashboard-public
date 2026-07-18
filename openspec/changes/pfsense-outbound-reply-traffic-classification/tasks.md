## 1. Shared Classification

- [x] 1.1 Add one deterministic helper that classifies relevant pfSense TCP traffic as `initiation_like`, `reply_or_teardown_like`, `ambiguous`, or `not_applicable`.
- [x] 1.2 Ensure the helper returns a concise reason and bounded evidence fields suitable for detector and analyst-context reuse.
- [x] 1.3 Add focused tests for SYN initiation, SYN+ACK response, ACK-only response, FIN+ACK teardown, RST+ACK teardown, missing flags, protected-host service-port to remote-ephemeral-port traffic, and ambiguous shapes.

## 2. Port Scan And Repeated Deny Interpretation

- [x] 2.1 Update `pfsense_firewall_port_scan` so reply-or-teardown-like outbound protected-host traffic does not count as source-driven scan breadth by itself.
- [x] 2.2 Preserve current inbound external scan behavior and legitimate outbound initiation detection.
- [x] 2.3 Update `pfsense_firewall_repeated_deny` so reply-style outbound protected-host bursts remain visible but are not hostile, incident-eligible, or containment-eligible by default.
- [x] 2.4 Replace compromised-host wording for this packet class with plain-English response or teardown wording.
- [x] 2.5 Add focused detector tests for reply-only, initiation-only, inbound scan, and mixed-traffic cases.

## 3. Incident And Analyst Context

- [x] 3.1 Keep incident gating aligned with pfSense detector operational flags so reply-only outbound protected-host traffic cannot create a prospective incident by itself.
- [x] 3.2 Keep approval and containment ineligible for reply-only outbound protected-host traffic unless stronger local evidence exists.
- [x] 3.3 Add additive analyst-context and why-fired fields exposing traffic-role classification, concise reasoning, and supporting packet facts.
- [x] 3.4 Add focused tests proving reply-only cases stay visible but non-incident-worthy while stronger corroboration restores eligibility.

## 4. Validation

- [x] 4.1 Run `python3 -m py_compile` on changed backend and test files.
- [x] 4.2 Run focused pfSense detector, incident, and alert-context tests.
- [x] 4.3 Run `openspec validate pfsense-outbound-reply-traffic-classification --strict`.
- [x] 4.4 Run `git diff --check`.
