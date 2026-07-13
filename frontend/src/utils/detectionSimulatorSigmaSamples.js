// Canned sample Sigma YAML and matching sample events for the Sigma Subset
// Import mode's "Load sample" actions. These are presentation helpers only —
// the frontend never parses, maps, compiles, or evaluates Sigma YAML. The
// backend is the sole authority for validation and simulation.

export const SAMPLE_SIGMA_BANK_APP_YAML = `title: Bank failed login subset
id: 11111111-1111-1111-1111-111111111111
status: experimental
description: Strict Sigma subset example for Detection Playground training
author: playground
date: 2026/07/13
logsource:
  product: bank_app
level: high
tags:
  - attack.t1110
  - attack.t1110.001
  - credential_access
detection:
  selection_type:
    EventType: failed_login
  selection_user:
    UserName|contains: admin
  condition: selection_type and selection_user
`;

export const SAMPLE_SIGMA_BANK_APP_EVENTS_JSON = `[
  {
    "event_type": "failed_login",
    "severity": "high",
    "source_ip": "203.0.113.50",
    "message": "failed login",
    "app_name": "bank",
    "environment": "prod",
    "username": "admin_user"
  },
  {
    "event_type": "failed_login",
    "severity": "high",
    "source_ip": "203.0.113.50",
    "message": "failed login",
    "app_name": "bank",
    "environment": "prod",
    "username": "alice"
  }
]
`;
