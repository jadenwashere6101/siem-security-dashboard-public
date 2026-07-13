## 1. Internal Rule Model and Sigma Contract

- [x] 1.1 (Mac AI) Define the Version 3 Sigma request/response contract, including simulation mode marker, Sigma text input shape, normalized internal-rule preview shape, and backend-authored validation error payloads.
- [x] 1.2 (Mac AI) Expand the bounded internal playground rule model only as needed for Sigma metadata plus simple boolean predicate trees over normalized field predicates.
- [x] 1.3 (Mac AI) Preserve the existing temporary-rule evaluator as the only execution path and document that Sigma compilation feeds only that path.
- [x] 1.4 (Mac AI) Add contract tests proving unsupported request shapes, persisted-rule behavior, and alternate execution-path behavior are rejected.

## 2. Safe YAML Parsing and Sigma Validation

- [x] 2.1 (Mac AI) Add safe backend YAML parsing with explicit malformed-YAML, size-limit, and bounded-structure validation.
- [x] 2.2 (Mac AI) Implement strict Sigma subset validation for supported metadata, supported selections, supported list values, supported modifiers, and simple `and` / `or` / `not` condition syntax.
- [x] 2.3 (Mac AI) Reject regex, wildcard selection expansion, Sigma correlation rules, Sigma aggregation/timeframe syntax, unsupported modifiers, backend-specific Sigma extensions, and other out-of-scope constructs with explicit errors.
- [x] 2.4 (Mac AI) Add focused backend tests for valid Sigma rules, malformed YAML, unsupported modifiers, unsupported conditions, and unsupported constructs.

## 3. Logsource Mapping, Field Mapping, and Compilation

- [x] 3.1 (Mac AI) Implement validator-owned Sigma `logsource` mapping to the six canonical simulator sources and fail closed on ambiguity.
- [x] 3.2 (Mac AI) Implement source-aware field alias mapping from supported Sigma fields into normalized simulator fields, including explicit rejection of unsupported or unmappable fields.
- [x] 3.3 (Mac AI) Parse `tags` and supported ATT&CK tags into normalized preview metadata without broadening execution semantics.
- [x] 3.4 (Mac AI) Compile supported Sigma selections and simple boolean conditions into the minimally expanded internal rule model and expose that compiled form in a normalized internal-rule preview.
- [x] 3.5 (Mac AI) Add focused tests for logsource mapping, field alias mapping, ATT&CK tag handling, and internal compilation output.

## 4. Backend Simulation Reuse and Safety Regression

- [x] 4.1 (Mac AI) Wire compiled Sigma rules into the existing rollback-only temporary-rule simulator path without creating a second evaluator.
- [x] 4.2 (Mac AI) Reuse existing parser/normalizer, pasted-event-only evaluation, alert preview, MITRE preview, SOAR preview, explainability, and pipeline-stage response contracts for Sigma mode.
- [x] 4.3 (Mac AI) Prove Sigma simulations preserve zero durable writes, no worker-visible rows, no production-rule mutation, no external integrations, and no arbitrary execution.
- [x] 4.4 (Mac AI) Add regression tests proving existing Version 1 and existing Version 2 simulator modes remain unchanged.

## 5. Frontend Sigma Mode and Shared Result Surfaces

- [x] 5.1 (Mac AI) Extend the Detection Simulator workspace with a `Sigma YAML` mode and a constrained text editor/import surface without adding a full code-editor dependency by default.
- [x] 5.2 (Mac AI) Render backend-authored Sigma validation feedback, mapping errors, and normalized internal-rule preview without performing client-side Sigma evaluation.
- [x] 5.3 (Mac AI) Reuse existing pipeline visualization, explainability, alert preview, MITRE preview, SOAR preview, and rollback disclosure for Sigma mode.
- [x] 5.4 (Mac AI) Add focused frontend tests for Sigma mode submission, validation rendering, normalized preview rendering, accessibility, responsive layout, and no-new-console-error behavior.

## 6. Quality Gates and Deployment Handoff Plan

- [x] 6.1 (Mac AI) Run focused backend tests, focused frontend tests, affected regressions, and the frontend production build; record the exact results.
- [x] 6.2 (Mac AI) Run browser verification for Sigma mode plus regression checks for existing simulator modes; record any environment limitations explicitly.
- [x] 6.3 (Mac AI) Run `git diff --check` and `openspec validate add-sigma-subset-import-to-detection-playground --strict`.
- [x] 6.4 (Mac AI) Confirm no migration is included unless implementation discovers a hard requirement and stops for review.
- [x] 6.5 (Mac AI) Prepare a VM deployment handoff plan covering expected files, backend-then-frontend deployment order, read-only production-safe checks, and rollback expectations, without accessing the VM.
