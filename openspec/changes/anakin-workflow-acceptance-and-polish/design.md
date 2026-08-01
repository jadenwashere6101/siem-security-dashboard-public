# Design: Anakin Workflow Acceptance And Polish

## Acceptance Inventory

The offline AI acceptance harness remains the source of truth for AI coverage. It will include:

- canonical workflow controls by UI surface;
- explicit legacy backend adapter rows marked as compatibility, not surviving UI controls;
- representative workflow fixtures for Quick Explain, Deep Investigate, Decision Support, Generate Artifact, SOC Briefing, and Repo Assistant;
- removal guards for obsolete action IDs and labels.

## Workflow Verification

The final gate validates:

- `/ai/workflows` request/response envelope shape;
- auto-routing classification, confidence, chooser behavior, and restricted workflow exclusion;
- approved model/profile routing only;
- bounded context and tool policies;
- Deep Investigate lifecycle stages;
- Decision Support recommendation-only behavior;
- Generate Artifact schema validation, one bounded repair attempt, and preview/confirm separation;
- SOC Briefing separate manual/scheduled lifecycle;
- Repo Assistant role-aware entry and backend citations.

## UI Polish Verification

Focused frontend tests assert the approved controls on each major surface and that removed labels are absent. Responsive usability is covered by stable wrapping style contracts on the shared workflow control component and command surface, plus render tests for menus, chooser state, loading/progress, degraded/partial, and error feedback.

## Live Acceptance Preparation

The live sweep remains opt-in and production-safe. It plans representative calls only:

- `/ai/status`;
- `/ai/repo/status`;
- Quick Explain;
- Deep Investigate;
- Decision Support;
- Generate Artifact in draft/preview-only mode;
- SOC Briefing status-only by default;
- Repo Assistant factual and evaluative questions;
- auto-routing and low-confidence chooser behavior.

It must not call confirmation endpoints, persist drafts, or create manual briefing jobs unless an explicit opt-in flag is set.
