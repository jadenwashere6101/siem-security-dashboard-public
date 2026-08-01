## 1. OpenSpec

- [x] 1.1 Create proposal, design, spec, and tasks for `anakin-analyst-personality-and-response-quality`.
- [x] 1.2 Run strict OpenSpec validation before implementation.

## 2. Persona And Prompt Contracts

- [x] 2.1 Strengthen the shared Anakin persona contract in `core/ai/anakin_persona.py`.
- [x] 2.2 Add tone adaptation, conservative profanity handling, no-roleplay, short-by-default, and evidence-bounded recommendation rules.
- [x] 2.3 Add explicit filler phrase and visible-field repetition prohibitions.
- [x] 2.4 Preserve separate workflow-specific policies for Quick Explain, Deep Investigate, Decision Support, Generate Artifact, SOC Briefing, and Repo Assistant.
- [x] 2.5 Preserve artifact/SOC briefing professionalism, strict schemas, read-only boundaries, repo boundaries, and no mutation claims.

## 3. Response-Quality Acceptance

- [x] 3.1 Add focused tests for shared persona reuse and no legacy generic assistant wording.
- [x] 3.2 Add tests for casual/professional/technical tone guidance and conservative profanity handling.
- [x] 3.3 Add tests for artifact professionalism and no profanity/slang in shareable outputs.
- [x] 3.4 Add tests for uncertainty quality, competing hypotheses, analyst disagreement, recommendation quality, and useful next steps.
- [x] 3.5 Add tests rejecting filler phrases and visible-field-only responses.
- [x] 3.6 Extend golden acceptance cases with property-based checks rather than exact wording.

## 4. Verification

- [x] 4.1 Run Python compilation for modified Python files.
- [x] 4.2 Run focused backend/persona tests.
- [x] 4.3 Run affected AI acceptance tests and offline acceptance harness.
- [x] 4.4 Run frontend build only if frontend files change.
- [x] 4.5 Run `git diff --check`.
- [x] 4.6 Run `openspec validate anakin-analyst-personality-and-response-quality --strict`.
- [x] 4.7 Capture `git status --short`.
