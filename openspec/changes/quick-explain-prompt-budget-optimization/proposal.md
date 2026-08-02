# Proposal

## Why

Production verification for commit `8dac04a` found that Quick Explain can fail before Ollama is called because its fixed prompt overhead grew after the natural-conversation change. The `fast_triage` profile remains correctly capped at 8,000 characters, and the production context fit before the style update.

## What Changes

- Optimize only the prompt blocks used by Quick Explain / Ask Anakin quick-explain behavior.
- Replace Quick Explain's use of the full interactive persona with a compact Quick Explain persona/style block.
- Remove duplicated instructions between the base persona, natural-conversation rules, tone guidance, Quick Explain workflow guidance, and few-shot examples.
- Preserve natural, direct, casual-aware Quick Explain behavior and fail-closed prompt safety.
- Add production-like prompt-budget tests for alert, source-IP, dashboard, casual, professional, and technical Quick Explain prompts.

## Out Of Scope

- No model, profile-limit, runtime, nginx, or frontend behavior changes.
- No redesign of the shared persona for Deep Investigate, Decision Support, Repo Assistant, Generate Artifact, or SOC Briefing.
- No weakening of prompt-size safety checks.
- No VM access, deployment, commit, or push.
