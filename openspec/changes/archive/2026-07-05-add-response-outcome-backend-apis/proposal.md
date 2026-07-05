# Proposal: Response Outcome Backend APIs

## Problem

The parent roadmap `openspec/changes/clarify-soar-response-outcomes` defines canonical SOAR response outcomes across backend APIs and UI surfaces. Phase 6 Slice 1 already implemented and verified the shared serializer helpers plus alert list/detail `response_outcome` payloads.

The remaining backend API surfaces still return subsystem-specific status fields. That prevents downstream UI work from consistently answering the parent roadmap question: what response was selected, what happened, and whether anything was actually executed.

## Goal

Complete the remaining Phase 6 backend API contract work after alert APIs by additively exposing canonical response outcome payloads on existing backend routes.

## Scope

- Response action log API payloads.
- SOAR queue status, recent/list, and detail payloads.
- Playbook execution list/detail payloads.
- Approval request list/detail/decision payloads.
- Notification delivery list/detail payloads.
- Incident list/detail/timeline payloads.
- Source-IP context payloads.
- Attack Map/source-IP popup backend payloads if a dedicated backend route exists.
- Blocklist Manager payloads.
- Metrics endpoints used by SOC Command Center aggregation.
- API contract tests for every updated route.

## Out of Scope

- No frontend work.
- No migrations expected.
- No new canonical tables or linkage columns.
- No runtime behavior changes beyond read-only API serialization.
- No queue, playbook, approval, notification, incident, blocklist, detection, or correlation behavior changes.
- No child decisions.
- No write-mode backfill.
- No real firewall enforcement.
- No commits or pushes.

## Parent Roadmap Reference

This child change implements the remaining backend API portion of Phase 6 from `openspec/changes/clarify-soar-response-outcomes` after alert APIs. The parent remains the master roadmap/spec. This child change is the active implementation spec for the remaining Phase 6 backend API response-outcome work.

## Success Criteria

- Existing legacy response fields remain present and unchanged.
- Updated route payloads add `response_outcome` or explicitly named canonical outcome aggregate fields.
- Entity payloads always include `response_outcome`; it is `null` when no canonical outcome exists.
- List endpoints avoid N+1 canonical outcome queries.
- Existing helpers in `core/soar_response_outcomes.py` are reused instead of duplicating outcome semantics.
- Routes that do not exist are documented and skipped or deferred rather than invented.
- Every updated route has focused API contract coverage.
