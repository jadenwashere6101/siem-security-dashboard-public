# Design

## Persona Layer

The existing shared persona remains the single source for Anakin behavior. This change adds an interactive natural-conversation layer used only by:

- Quick Explain
- Ask Anakin
- Deep Investigate
- Decision Support
- Repo Assistant

Shareable workflows keep professional tone and do not receive casual examples.

## Few-Shot Examples

Add a very small example block to interactive prompts. The examples demonstrate:

- casual question answered naturally without forced slang;
- unsupported blocking assumption answered with direct disagreement;
- robotic phrasing to avoid.

The examples are intentionally short to keep prompt budgets bounded and are framed as style examples, not reusable conclusions.

## Positive Enforcement

The acceptance harness extends exact banned phrases with property checks:

- every paragraph should add reasoning, evidence, uncertainty, or a concrete next step;
- visible-field-only restatement fails;
- generic closing disclaimers fail;
- robotic preambles fail.

These checks complement prompt rules instead of relying only on a phrase blacklist.

## Decision Support Ordering

Recommendation-first enforcement normalizes candidate labels by stripping:

- markdown bold/italic punctuation;
- heading markers;
- bullets and ordered-list prefixes;
- blockquote markers;
- repeated punctuation and whitespace.

The helper recognizes semantic recommendation labels without treating unrelated labels such as `Evidence recommendation source:` as the recommendation section.

## Safety

The change is prompt/style and deterministic formatting only. It preserves read-only boundaries, artifact validation, preview/confirm gates, local-only routing, RBAC, sanitization, and no-paid-fallback behavior.
