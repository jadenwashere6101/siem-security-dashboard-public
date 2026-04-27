 # MITRE ATT&CK Alert Enrichment Spec

  ## Feature Overview

  This change adds MITRE ATT&CK enrichment to SIEM alerts so alerts display standardized
  technique and tactic context.

  The scope is intentionally phased:

  - Phase 1 adds backend enrichment to alert API responses
  - Phase 2 adds compact frontend display in alert details
  - Phase 3 adds MITRE context to PDF incident reports

  The goal is to make alerts look more like real SOC/SIEM output without changing detection
  behavior or requiring a schema change in v1.

  ## Current State

  - Alerts currently expose fields such as:
      - alert_type
      - severity
      - source_ip
      - message
      - status
      - created_at
  - Detection rules include:
      - failed_login_threshold
      - port_scan_threshold
  - IP reputation-related alerts exist or are displayed as suspicious_ip_reputation.
  - Alerts do not currently include MITRE ATT&CK technique or tactic information.
  - PDF reports do not currently include MITRE ATT&CK mappings.

  ## MITRE Mapping Table

  | alert_type | technique_id | technique_name | tactic |
  |---|---|---|---|
  | failed_login_threshold | T1110 | Brute Force | Credential Access |
  | port_scan_threshold | T1046 | Network Service Discovery | Discovery |
  | suspicious_ip_reputation | T1595 | Active Scanning | Reconnaissance |

  ## Backend Requirements

  ### Phase 1

  - Add a backend helper or dictionary that maps alert_type to MITRE ATT&CK data.
  - Enrich alert API responses with:
      - mitre_technique_id
      - mitre_technique_name
      - mitre_tactic
  - Do not require database schema changes in v1.
  - Do not change alert creation logic.
  - Do not change detection logic.
  - If an alert type has no mapping:
      - return null values
      - or omit safely in a consistent way

  ## Frontend Requirements

  ### Phase 2

  - Display MITRE ATT&CK information in alert details only.
  - Keep the UI compact and consistent with the existing dark SIEM styling.
  - Do not clutter the main alert table with extra MITRE columns in v1.
  - Display should include:
      - technique ID
      - technique name
      - tactic
  - If MITRE enrichment is missing, the UI should degrade gracefully without errors.

  ## PDF Report Requirements

  ### Phase 3

  - Include MITRE ATT&CK technique and tactic information in PDF incident reports.
  - Keep PDF presentation readable and aligned with the existing report style.
  - TXT report output remains unchanged in this phase unless explicitly expanded later.

  ## Compatibility Requirements

  - Do not change existing API endpoints.
  - Do not break existing alerts without MITRE mapping.
  - Do not require database migration in v1.
  - Do not change authentication or RBAC behavior.
  - Do not change alert creation, ingestion, or rule execution behavior.
  - MITRE enrichment must be additive only.

  ## Acceptance Criteria

  - Backend alert responses include MITRE fields for mapped alert types.
  - failed_login_threshold returns:
      - T1110
      - Brute Force
      - Credential Access
  - port_scan_threshold returns:
      - T1046
      - Network Service Discovery
      - Discovery
  - suspicious_ip_reputation returns:
      - T1595
      - Active Scanning
      - Reconnaissance
  - Unmapped alert types do not break API responses.
  - Frontend alert details show MITRE ATT&CK context when available.
  - PDF incident reports include MITRE ATT&CK context when available.
  - TXT reports remain unchanged.

  ## Non-Goals

  This change does not include:

  - database schema changes in v1
  - dynamic ATT&CK lookups from an external service
  - ATT&CK navigator integration
  - ATT&CK heatmaps
  - changes to detection logic
  - changes to alert creation logic
  - adding MITRE columns to the main alert table
  - TXT report expansion in this phase
