# anakin-response-quality-enforcement

## Summary

Make Anakin's existing response-quality persona structurally enforceable for the deployed six-workflow architecture.

## Problem

Production acceptance for commit `1d8437f` showed several response-quality gaps despite the shared persona policy:

- Decision Support does not reliably lead with the recommendation.
- Unsupported user certainty is resisted indirectly instead of clearly disagreed with.
- Casual prompts can still receive overly formal responses.
- Deep Investigate can end with disclaimer-style filler.
- Near-equivalent filler paraphrases bypass exact banned-phrase checks.

## Goals

- Add deterministic per-request tone classification.
- Pass tone into prompts and response metadata.
- Enforce Decision Support's recommendation-first response contract.
- Add prompt and property checks against semantic filler/disclaimer patterns.
- Require Deep Investigate to end with a prioritized next step or unresolved question.
- Preserve all existing workflow boundaries, schemas, preview/confirm gates, and read-only behavior.

## Non-Goals

- No workflow architecture redesign.
- No memory or long-term user tone profile.
- No model/profile/runtime configuration changes.
- No frontend redesign beyond metadata/error rendering if required.
- No VM access, deployment, commit, push, or production mutation.
