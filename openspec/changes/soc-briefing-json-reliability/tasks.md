## 1. OpenSpec

- [x] 1.1 Create proposal, design, spec, and tasks for `soc-briefing-json-reliability`.
- [x] 1.2 Run strict OpenSpec validation before implementation.

## 2. SOC Briefing Structured Output Reliability

- [x] 2.1 Review Generate Artifact validation/repair pattern and apply a matching bounded one-repair architecture to SOC Briefing synthesis.
- [x] 2.2 Add structured briefing validation for summary, required section keys, and array section values.
- [x] 2.3 Add exactly one bounded repair call for malformed, truncated, or schema-invalid briefing output.
- [x] 2.4 Preserve deterministic partial fallback when repair fails.
- [x] 2.5 Preserve evidence refs, read-only behavior, local-only/no-paid-fallback safety, and non-mutating metadata.
- [x] 2.6 Make the minimal justified completion-token budget adjustment and document it in the spec/design.

## 3. Tests And Acceptance

- [x] 3.1 Add focused tests for valid structured output and unchanged success behavior.
- [x] 3.2 Add tests for malformed JSON repaired successfully and repair invoked exactly once.
- [x] 3.3 Add tests for unrecoverable malformed output failing cleanly.
- [x] 3.4 Add tests for missing required sections, non-array sections, and truncated output.
- [x] 3.5 Add tests proving no fabricated sections/evidence and bounded repair metadata.

## 4. Verification

- [x] 4.1 Run Python compilation for modified modules.
- [x] 4.2 Run focused SOC briefing backend tests.
- [x] 4.3 Run affected acceptance tests.
- [x] 4.4 Run `git diff --check`.
- [x] 4.5 Run `openspec validate soc-briefing-json-reliability --strict`.
- [x] 4.6 Capture `git status --short`.
