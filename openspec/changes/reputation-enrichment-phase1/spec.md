# Reputation Enrichment Phase 1 Spec

## Feature Overview

This change adds internal IP reputation enrichment to the SIEM so IPs accumulate behavior-based labels and scores over time.

The goal is to give analysts useful context about an IP based on historical activity already observed inside the SIEM, such as repeated brute-force behavior, scan activity, traffic anomalies, or prior blocklist status.

## Current State

- Events store:
  - `source`
  - `source_type`
  - `event_type`
- Alerts store source attribution and `alert_type`
- `blocked_ips` exists for SIEM-managed blocklist tracking
- There is currently no internal reputation or scoring system
- The UI does not currently surface behavior-based intelligence for source IPs

## Requirements

1. Reputation model
   - Do not add a new table in v1
   - Compute reputation dynamically from existing data in:
     - `alerts`
     - `events`
     - `blocked_ips`

2. Backend helper
   - Add:
     - `get_ip_reputation(source_ip)`
   - Return:
     - `reputation_score` (integer)
     - `reputation_label` (string)
     - `reputation_summary` (string)
     - `contributing_signals` (list)

3. Scoring logic
   - Keep scoring simple, deterministic, and transparent
   - Signals and weights:
     - `failed_login_threshold` → `+3`
     - `password_spraying_threshold` → `+5`
     - `successful_login_after_spray` → `+6`
     - `port_scan_threshold` → `+4`
     - `http_error_threshold` → `+2`
     - `high_request_rate_threshold` → `+3`
     - active `blocked_ips` entry → `+6`

4. Labels
   - `0` → `Normal`
   - `1–4` → `Low Suspicion`
   - `5–9` → `Suspicious`
   - `10–14` → `High Risk`
   - `15+` → `Critical`

5. Summary generation
   - Generate a short human-readable summary, for example:
     - `Multiple failed login attempts and prior blocklist entry`
     - `High request rate and repeated HTTP errors`
   - The summary should reflect actual contributing signals, not generic text

6. API changes
   - Extend:
     - `/alerts`
     - `/events/search`
   - Include:
     - `reputation_score`
     - `reputation_label`
     - `reputation_summary`
   - If practical, also include:
     - `contributing_signals`

7. UI changes

   Alerts table:
   - Add a reputation badge or column
   - Display label such as `High Risk`
   - Use compact color-coded styling from green to red

   Alert details:
   - Show:
     - score
     - label
     - summary
     - contributing signals

   Threat Hunt:
   - Include reputation info for each IP result

8. Performance constraints
   - Keep computation lightweight
   - Use simple count-based queries
   - Use indexed fields such as `source_ip`
   - Avoid broad full-table scans when filtering by a specific IP
   - Do not add caching in v1

9. Do not:
   - add external threat intelligence APIs
   - add ML/AI scoring
   - add new database tables
   - change ingestion
   - change detection logic
   - auto-block based on reputation

## Non-Goals

- No VirusTotal integration
- No AbuseIPDB integration for this feature
- No machine learning scoring
- No automatic enforcement
- No schema redesign
- No background jobs
- No caching layer in v1

## Acceptance Criteria

1. Each alert displays a reputation label.
2. Reputation score matches the expected signal counts.
3. Reputation summary is human-readable.
4. Threat Hunt results include reputation info.
5. No noticeable dashboard performance degradation.
6. No ingestion or detection behavior changes.

## Risks and Mitigations

- Risk: inaccurate scoring due to simple rules
  - Mitigation: keep the logic transparent, deterministic, and easy to tune later

- Risk: performance issues from repeated per-IP queries
  - Mitigation: use indexed `source_ip` lookups and simple count queries only

- Risk: users place too much confidence in the score
  - Mitigation: label it clearly as an internal behavioral score, not external threat intelligence

- Risk: UI clutter
  - Mitigation: use compact badges and place deeper detail in expanded views

- Risk: confusion with external reputation services
  - Mitigation: explicitly describe it as SIEM-generated reputation based on internal activity only
