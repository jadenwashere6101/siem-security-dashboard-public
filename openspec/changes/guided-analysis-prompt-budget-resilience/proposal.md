## Why

Deep Investigation can gather valid evidence yet fail before guided-analysis synthesis because independently bounded prompt sections exceed the profile's 14,000-character limit when combined. The synthesis boundary must guarantee a fitting prompt and preserve a useful grounded outcome when mandatory content alone cannot fit.

## What Changes

- Build guided-analysis synthesis prompts within the selected profile budget, accounting for the complete serialized prompt.
- Preserve the current question, task and entity context, essential evidence, source provenance, truncation disclosure, grounding instructions, and read-only safety policy.
- Compact optional conversation history and lower-priority evidence before mandatory content.
- Return a deterministic, source-cited partial answer from validated evidence when mandatory synthesis content cannot fit, without invoking a provider.
- Record prompt-budget measurements and compaction/fallback status for verification.
- Keep the existing profile limit, planner ownership, routing, provider assignments, and Anthropic behavior unchanged.

## Capabilities

### New Capabilities
- `guided-analysis-prompt-budgeting`: Defines bounded guided-analysis synthesis and grounded deterministic fallback behavior.

### Modified Capabilities

None.

## Impact

The change is limited to the guided investigation synthesis boundary, its focused tests, and acceptance coverage. It changes no API contract, database schema, frontend, provider, planner, routing, or runtime configuration.
