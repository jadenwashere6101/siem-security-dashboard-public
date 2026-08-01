# Design: Anakin Analyst Reasoning And Personality

## Shared Policy

Add a shared `core.ai.anakin_persona` module with reusable prompt sections:

- `ANAKIN_PERSONA_POLICY`: experienced Detection Engineer voice, skeptical and concise.
- `ANAKIN_REASONING_RULES`: do not repeat visible fields, distinguish fact/inference/uncertainty, challenge severity, no generic filler, prioritize one observation first.
- workflow-specific policy builders, for example `quick_explain_policy()`, `deep_investigate_policy()`, `decision_support_policy()`, `artifact_policy()`, `soc_briefing_policy()`, and `repo_assistant_policy()`.

The shared policy is reused, but each workflow owns its prompt shape. This avoids a single giant prompt while keeping behavior consistent.

## Workflow Prompt Integration

- Quick Explain / chat/explain prompts include the persona and concise reasoning rules.
- Deep Investigate correlation prompts include required support, contradiction/benign explanations, missing evidence, confidence, and next-step reasoning.
- Decision Support uses the same explain service path from the workflow orchestrator but adds recommendation-only instructions and blocks draft/apply language.
- Generate Artifact prompts include evidence-specific artifact guidance while preserving JSON-only schema instructions and validation.
- SOC Briefing prompts include prioritization and low-value-noise handling.
- Repo Assistant prompts include fact vs judgment boundaries while preserving citations.

## Testing Strategy

Prompt-contract tests inspect built prompts for required policy language and anti-pattern protections. Golden acceptance tests evaluate sample responses for properties:

- leading observation first;
- specific next check;
- support and contradiction handling;
- missing evidence and confidence;
- no generic “continue monitoring” filler;
- no unsupported escalation/blocking;
- repo fact vs judgment distinction.

Exact wording is not asserted.

## Safety And Compatibility

This change does not alter routes, auth, RBAC, tool execution limits, model profiles, runtime config, preview/confirm gates, or schema validation. Existing legacy route adapters continue using the improved shared prompt policy through the services they already call.
