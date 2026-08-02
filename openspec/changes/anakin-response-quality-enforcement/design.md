# Design

## Tone Classification

Add a small deterministic classifier in the Anakin persona layer with three labels:

- `casual`
- `professional`
- `technical`

Classification uses only the current prompt and bounded workflow/surface context. It does not call the model and does not persist a profile.

Rules:

- User slang, contractions, casual wording, or user-initiated profanity -> `casual`.
- Precise implementation, security, protocol, detection, or engineering terminology -> `technical`.
- Otherwise -> `professional`.

Shareable workflows force professional tone:

- Generate Artifact
- SOC Briefing
- notes
- playbooks
- detection suggestions
- response recommendations

## Prompt Integration

The shared persona policy will expose a tone instruction helper. Workflow prompt builders will include the classified tone.

Decision Support, Quick Explain, Deep Investigate, and Repo Assistant metadata should include the tone where the service owns a response envelope. Generate Artifact and SOC Briefing prompts may include forced professional tone without changing schemas.

## Decision Support Contract

Decision Support prompts will require a stable structure:

1. `recommendation`
2. `why`
3. `evidence`
4. `risks`
5. `alternatives`
6. `what_would_change_my_mind`
7. `confidence`

The recommendation must be first. If the user asserts a conclusion not supported by evidence, the response must explicitly disagree in the recommendation or why field.

## Filler Enforcement

Extend acceptance beyond exact banned strings with pattern-level checks for:

- `based on ... provided/context/details`
- `important to note`
- `alert ... indicates/indicating`
- `further investigation may reveal`
- `please let me know`
- `hope this helps`
- generic closing caveats that only say conclusions may change with more information

Deep Investigate must end with a concrete next step or unresolved question, not a generic disclaimer.

## Boundaries

Decision Support remains read-only and cannot draft, preview, confirm, apply, or mutate. Generate Artifact and SOC Briefing retain professional shareable tone and strict schemas. No production runtime behavior changes are introduced.
