# Proposal

## Why

Production verification for commit `b1446b1` showed that tone classification and prompt delivery are present, but the small local model still often responds formally to casual interactive prompts. Decision Support also has a narrow enforcement bug: recommendation-first detection does not recognize markdown-formatted labels such as `**Recommendation:**`.

## What Changes

- Strengthen the shared interactive Anakin persona with a concise natural-conversation contract.
- Add a small number of few-shot examples for interactive workflows so the 3B model sees the desired contrast between robotic and natural responses.
- Add positive response-quality rules that require each paragraph to add reasoning, uncertainty, evidence, or a concrete next step.
- Preserve formal/shareable behavior for Generate Artifact, SOC Briefing, notes, playbooks, detection changes, and response recommendations.
- Fix Decision Support recommendation-first enforcement to recognize markdown headings, bullets, numbering, punctuation, and whitespace.
- Add focused prompt-contract and property tests for natural style, anti-filler behavior, and markdown recommendation ordering.

## Out Of Scope

- No workflow redesign.
- No memory or conversation continuity.
- No model/profile/runtime configuration changes.
- No frontend redesign.
- No VM access, deployment, commit, or push.
