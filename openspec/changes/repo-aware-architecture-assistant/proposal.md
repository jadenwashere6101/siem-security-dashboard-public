## Why

The AI roadmap now needs a developer-facing assistant that can answer repository architecture questions without confusing current source-of-truth rules with historical handoffs, archived specs, generated reports, or stale planning notes. Phase 2 should help maintain and extend the SIEM safely by grounding answers in current repository files and explicit project policies, while staying read-only and separate from analyst triage.

## What Changes

- Add a repo-aware architecture assistant capability for internal development and maintenance questions.
- Define a canonical repository source hierarchy covering current policy docs, active OpenSpecs, accepted specs, source code, schemas, migrations, tests, and selected current runbooks.
- Define excluded or low-trust sources such as archived OpenSpecs, historical handoffs, generated Sonar exports, build artifacts, caches, runtime files, and secrets.
- Add retrieval/indexing behavior that uses current files, source metadata, freshness checks, and citations instead of fine-tuning.
- Add grounded insufficient-evidence behavior so the assistant refuses to answer when current sources do not support a claim.
- Reuse the Phase 1A AI gateway and Phase 1B response/metadata patterns where appropriate without reusing analyst SIEM chat as the primary developer tool.
- Keep the assistant read-only: no shell execution, database access, source modification, autonomous cleanup, commits, pushes, deployment, or VM access.
- Allow only focused documentation corrections where stale current docs would materially confuse retrieval.

## Capabilities

### New Capabilities

- `repo-aware-architecture-assistant`: Read-only internal developer assistant that retrieves current repository context, applies trust rules, and returns source-cited architecture answers.

### Modified Capabilities

(none)

## Impact

- Backend: new repo-assistant retrieval/indexing/service modules under the existing AI package or a clearly scoped adjacent package, plus thin authenticated route(s) if implemented as an internal app feature.
- Frontend/internal tooling: either a developer-only UI surface that reuses shared AI response display patterns or a separate internal command/tool endpoint; analyst triage UI is not expanded by this phase.
- Repository docs: optional narrowly targeted corrections or metadata markers for stale docs that would otherwise be indexed as current truth.
- Database/runtime: no schema migration, no direct database access, no production writes, no background inference, no VM work, and no paid provider requirement.
