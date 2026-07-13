## Context

Version 1 of the Detection Simulator safely replays existing production detectors inside one rollback-only transaction. Version 2 added a bounded temporary-rule mode that reuses parser/normalizer, alert preview, MITRE preview, SOAR preview, explainability, pipeline visualization, and zero-write guarantees while evaluating only pasted events.

Version 3 needs to add Sigma interview and training value without widening the execution surface. The user explicitly does not want a custom DSL in this change, does not want a second detection engine, and does not want production-rule creation or persistence. The completed architecture audit for this session already narrowed the safe direction: treat Sigma as an input format that compiles into a bounded internal rule model and then execute only through the existing temporary-rule simulator path.

## Goals / Non-Goals

**Goals:**

- Add safe Sigma YAML import and simulation to the existing Detection Playground.
- Preserve one evaluator, one rollback-only transaction boundary, one pasted-event-only execution model, and one preview/explainability surface.
- Support a strict Sigma subset with explicit validation, source mapping, field mapping, and normalized internal-rule preview.
- Expand the Version 2 internal rule model only as much as needed for Sigma selections and simple boolean composition.
- Keep Version 1 and existing Version 2 behavior unchanged when Sigma mode is not used.

**Non-Goals:**

- Custom user-facing DSL design or implementation.
- A second detection engine, a general Sigma execution engine, or production-detector parity claims.
- Sigma correlation rules, aggregation language, backend-specific Sigma extensions, wildcard selection expansion, regex, or unsupported modifiers.
- Rule persistence, import/export, scheduled simulation, Sigma-to-production conversion, arbitrary Python, arbitrary SQL, or VM deployment work in this change.

## Decisions

### Keep the existing temporary-rule evaluator as the only execution path

Sigma import should terminate in the same rollback-safe simulator mode that Version 2 already uses. The backend should parse YAML, validate the Sigma subset, map it to canonical source and normalized fields, compile it into a bounded internal rule object, and then hand that object to the existing temporary-rule simulation path.

Alternative considered: a separate Sigma evaluator. Rejected because it would duplicate safety boundaries, duplicate explainability work, and create semantic drift between “temporary rule” and “Sigma rule” results.

### Expand the internal rule model minimally instead of executing raw Sigma semantics

The current Version 2 contract assumes exactly one condition. Sigma subset support needs a small internal expansion:

- a bounded predicate tree with `all`, `any`, and `not` nodes;
- leaf predicates expressed in the same normalized-field/operator/value style Version 2 already uses;
- optional metadata for provenance and preview: `title`, `id`, `status`, `description`, `author`, `date`, `level`, `tags`, `attack_tags`, and `logsource`;
- the existing aggregation block retained only as an optional future-compatible structure, but unused for Version 3 Sigma because Sigma aggregation/timeframe are out of scope.

Everything else should remain bounded exactly as Version 2 already is: canonical source, canonical source type, compatible input format, optional event-type narrowing, severity, request-scoped evaluation, and preview-only outcomes.

Alternative considered: compile Sigma directly into the current one-condition contract. Rejected because even simple Sigma conditions require multiple selections and boolean composition.

### Support only a strict Sigma subset and reject everything else explicitly

Version 3 should support:

- safe YAML parsing;
- metadata fields `title`, `id`, `status`, `description`, `author`, `date`;
- `logsource` only when it resolves to one of the six canonical sources;
- `level`, `tags`, and ATT&CK tags;
- `detection` selections with exact matches, lists, and safe string modifiers `contains`, `startswith`, `endswith`;
- simple `condition` expressions using named selections with `and`, `or`, and `not`.

Version 3 should reject with explicit errors:

- regex and regex-like modifiers;
- wildcard selection expansion such as `1 of`, `all of`, or `selection*`;
- Sigma correlation rules and aggregation syntax;
- unsupported modifiers and backend-specific Sigma extensions;
- ambiguous logsource mappings;
- unsupported or unmappable fields.

Alternative considered: claiming broader Sigma compatibility while silently dropping unsupported parts. Rejected because it would mislead analysts and make the simulator unsafe to trust.

### Use validator-owned field and logsource mapping tables

Field mapping should be declarative and fail closed. The backend should own:

- canonical source/logsource mapping rules;
- per-source allowed normalized fields;
- allowed Sigma aliases per normalized field;
- explicit unsupported-field and ambiguous-mapping error messages.

Mapping failures should explain what was provided, why it failed, and what this SIEM accepts instead. The frontend should render those backend-authored errors and should not invent mappings client-side.

Alternative considered: permissive best-effort remapping. Rejected because silent coercion would blur what the analyst actually wrote.

### Keep the editor simple and reuse existing result surfaces

Version 3 does not need Monaco or CodeMirror. A constrained textarea with line/column validation feedback and a normalized-rule preview is sufficient. The UI should add a Sigma mode beside existing simulator modes, reuse the current pipeline visualization and explainability components, and show explicit rollback/non-persistence disclosure.

Alternative considered: adding a full code editor dependency in the first version. Rejected because the core value is backend validation and simulation semantics, not editor richness.

## Risks / Trade-offs

- [Unsafe YAML parsing] → Use a safe loader only, plus payload-size, key-depth, and shape validation before compilation.
- [Semantic drift between Sigma and playground execution] → Compile Sigma into the same internal evaluator path used by temporary rules; do not create a second executor.
- [Analysts assume full Sigma compatibility] → Label the feature as a strict Sigma subset import and return explicit unsupported-feature errors.
- [Ambiguous logsource or field mappings] → Require exact or declaratively approved mappings; reject ambiguity with source-specific error messages.
- [Internal model grows into a general query language] → Limit expansion to predicate trees plus existing bounded preview metadata; keep aggregation/timeframe out of scope.
- [Version 1 or Version 2 regressions] → Add explicit regression coverage proving both existing modes remain unchanged.

## Migration Plan

1. Mac AI expands the internal temporary-rule model and request/response contract only as needed for Sigma subset compilation.
2. Mac AI adds safe YAML parsing, strict subset validation, logsource/field mapping, and compiler tests.
3. Mac AI wires compiled Sigma rules into the existing rollback-safe simulator path and verifies zero-write, no-external-call, and no-worker-visibility behavior.
4. Mac AI extends the Detection Simulator UI with Sigma mode, editor/import input, validation feedback, normalized preview, and shared pipeline/explainability rendering.
5. Mac AI runs focused tests, affected regressions, frontend build, browser verification, `git diff --check`, and `openspec validate add-sigma-subset-import-to-detection-playground --strict`, then prepares a VM deployment handoff plan without accessing the VM.

No migration is expected. Rollback remains code-only because the feature must not add persistence.

## Open Questions

- Should the backend add a dedicated `sigma_yaml` request field in addition to generic text input, or should Sigma mode continue to submit through the existing `input_text` pattern with a mode discriminator?
- Should ATT&CK tag handling support only canonical `attack.txxxx` tags in Version 3, or also a small alias set if current Sigma examples in practice require it?
- If the backend lacks an already-approved safe YAML parser dependency, should this change add `PyYAML` with `safe_load`, or choose another narrowly scoped parser?
