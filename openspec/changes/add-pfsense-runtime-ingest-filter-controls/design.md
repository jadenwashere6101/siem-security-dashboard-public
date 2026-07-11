## Context

**Owner: Mac AI.** The repo already separates pfSense collection into a UDP listener, pure parser/normalizer, authenticated Flask route, and centralized ingest. The listener enforces sender allow-list, packet bounds, and rate limits; the parser supports IPv4 TCP/UDP `block` and `pass`; `/ingest/pfsense` validates, geolocates, opens a DB connection, and calls `ingest_normalized_event()`. Detection configuration provides code defaults, DB overrides, validation, super-admin routes, audit logging, and per-use runtime reads, but its UI edits only numeric parameters and explicitly cannot toggle `active`.

The proposal’s “all pfSense logs” premise is corrected: this scope controls filterlog firewall traffic only. DNS means TCP/UDP destination port 53. Actual resolver queries, IPv6, DHCP, VPN, authentication, and system logs remain separate future capabilities.

## Goals / Non-Goals

**Goals:**

- Retain all blocks and inbound sensitive-port allows by default; drop routine allows before geolocation and storage.
- Provide validated, audited, restartless super-admin configuration with safe code defaults.
- Use one sensitive-port list for retention and suspicious-allow detection.
- Make supported IPv4 ICMP filterlog traffic classifiable.
- Provide truthful filtered responses and bounded decision observability without retaining dropped payloads.

**Non-Goals:**

- Direct DB access from the listener, a second ingest pipeline, or raw dropped-event storage.
- DNS resolver query/domain parsing, IPv6, non-filterlog pfSense sources, packet replay guarantees, or real firewall actions.
- VM deployment, external pfSense configuration, commits, or pushes.

## Decisions

1. **Filter in the authenticated backend route after normalization/validation.** The listener remains DB-free and posts normalized events. `/ingest/pfsense` opens its DB connection, loads effective policy, evaluates the event, and returns before `_add_location_to_normalized_event()` and `ingest_normalized_event()` when filtered. Filtering inside the listener would require DB credentials or a second configuration control plane; filtering after centralized ingest would be too late.

2. **Use a dedicated configuration table and one authoritative store.** `pfsense_ingest_config` follows the detection-config pattern: known keys, enabled state, JSON parameters, updater, timestamp, code defaults, merge/validation, and fallback status. Known categories are `block_events`, `inbound_sensitive_port_allows`, `all_allow_events`, `dns_traffic`, and `icmp_traffic`; the sensitive-port list is a validated parameter of the sensitive-allow category. Unknown keys and parameters are rejected.

3. **Read policy per request for exact restartless behavior.** Expected volume is low enough for a bounded indexed configuration read per normalized request. No TTL cache means the next request after a committed PATCH observes the update. A future cache requires explicit invalidation semantics and performance evidence.

4. **Use deterministic OR precedence.** A valid event is retained when any enabled category matches. Defaults: all block events enabled; inbound sensitive-port allows enabled; all allows, DNS traffic, and ICMP allow traffic disabled. `all_allow_events` retains any supported `pass`. `dns_traffic` means TCP/UDP `pass` with destination port 53. `icmp_traffic` retains ICMP `pass`; ICMP blocks are already retained by the block category. Routine unmatched allows are filtered.

5. **Fail closed to safe code defaults.** Missing table/rows, DB lookup error, or invalid overrides produce a sanitized warning and evaluate with defaults—not “retain all” and not “drop all.” Authentication and normalized schema failures remain rejected, not filtered.

6. **Make sensitive ports canonical.** Move the current detector constant into the effective pfSense ingest policy contract. Both retention and `_generate_pfsense_suspicious_allow_alerts_core` use the effective list from the same transaction/cursor. Default ports reconcile existing detector intent with requested management/datastore coverage: `21,22,23,25,135,445,1433,3306,3389,5432,5900,6379,27017`.

7. **Bound ICMP expansion.** Extend only common IPv4 ICMP filterlog layouts. Ports become optional for ICMP and required for TCP/UDP. Preserve protocol/type/code where available. Unsupported layouts and IPv6 continue to return bounded parse failures.

8. **Distinguish outcomes without retaining dropped payloads.** Backend returns `201` for ingested and `202` with `status=filtered`, category/reason, and no echoed payload for filtered. The listener recognizes the response outcome and counts `ingested`, `filtered`, `rejected`, and `backend_failed` separately. Backend aggregate counters are bounded/in-memory or metrics-native and expose counts by decision reason; no per-drop DB row is allowed.

9. **Add a dedicated super-admin panel.** Administration gets “pfSense Ingest Filters,” using existing dark-theme panel/service patterns. Toggles and port edits are validated server-side, audited with old/new safe values, reload effective state after save, and disclose defaults/fallback/last updater. Detection Rules remains separate.

## Risks / Trade-offs

- [Filtering removes evidence later found useful] → conservative block retention, explicit safe defaults, observable counters, audited changes, and an emergency all-allows toggle.
- [One DB read per event adds load] → one indexed bounded query set; measure before introducing caching.
- [UDP loss is mistaken for filtering] → listener counters keep rejected/rate-limited/parse-failed/backend-failed distinct from backend-filtered.
- [Canonical port edits change detection behavior] → UI discloses shared effect; integration tests prove retention and suspicious-allow alignment.
- [ICMP field layouts vary] → fixture-driven bounded support; reject unknown variants rather than guessing.
- [In-memory counters reset] → expose reset/start timestamp and document that counters are operational aggregates, not durable evidence.

## Migration Plan

1. Mac Phase 1 adds migration/schema snapshot, store/defaults/validation, policy evaluator, route ordering, canonical detector ports, ICMP parsing, response/statistics accounting, and backend tests.
2. Mac Phase 2 adds admin API/UI, audit/observability presentation, cross-layer matrices, production build, documentation, and VM handoff.
3. VM child performs clean deployment, migration, backend/listener/frontend rollout, synthetic verification, restartless changes, rollback rehearsal, and readiness approval.
4. Rollback UI and route controls through the approved prior commit; preserve the additive config table. If source rollback is required, safe previous behavior resumes only after production log forwarding is paused to prevent unfiltered storage growth.

## Open Questions

- None blocking. Actual DNS resolver queries and IPv6 are explicitly deferred to dedicated future specs.
