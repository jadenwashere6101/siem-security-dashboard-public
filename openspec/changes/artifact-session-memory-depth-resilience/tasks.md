## 1. Artifact Persistence Boundary

- [x] 1.1 Implement artifact-only depth measurement and normalization before assistant-turn session-memory validation
- [x] 1.2 Preserve meaningful fields, provenance, auditability, preview-only safety, thread context, and shallow normalization metadata
- [x] 1.3 Retain the global depth limit and fail-closed behavior for arbitrary, malformed, or unsafe nested input
- [x] 1.4 Normalize only over-depth server-owned user-turn planning/context branches with auditable metadata

## 2. Verification

- [x] 2.1 Add focused unit and PostgreSQL tests for fresh and long-lived threads, nested artifact previews, and no operational apply
- [x] 2.2 Run affected session-memory, orchestration, worker, planner, acceptance, compilation, and diff checks
- [x] 2.3 Validate `artifact-session-memory-depth-resilience` with strict OpenSpec validation
- [x] 2.4 Verify long-lived artifact user-turn persistence, shallow-turn stability, affected regressions, and completion gates

## 3. Production Acceptance Gate

- [ ] 3.1 Follow `docs/anakin-production-acceptance-policy.md`: automated checks are necessary but not sufficient; verify the deployed Generate Artifact browser path before using working/done/fully verified/production-ready language, otherwise report exactly `Implementation complete; production behavior unverified.`
