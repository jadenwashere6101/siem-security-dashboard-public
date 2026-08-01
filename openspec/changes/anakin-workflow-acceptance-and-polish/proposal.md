# Proposal: Anakin Workflow Acceptance And Polish

## Summary

Add the final completion gate for the Anakin redesign. This change verifies the six canonical workflows, consolidated frontend controls, safety boundaries, response-quality behavior, and production-safe live acceptance plan without adding new AI features or changing the architecture.

## Motivation

The previous Anakin changes introduced shared workflow orchestration, consolidated UI controls, and a Detection Engineer persona. Before live acceptance testing, the project needs a hard gate that proves every remaining AI entry point maps to one canonical workflow, removed legacy controls cannot silently return, workflow contracts remain safe, and the offline acceptance harness is aligned with the new architecture.

## Goals

- Treat the six workflows as the acceptance inventory unit.
- Preserve exact mapping from each remaining frontend AI control to one workflow.
- Fail if obsolete frontend action IDs or low-value legacy controls return.
- Add realistic representative fixtures for all six workflows.
- Validate envelopes, routing, profile/model selection, context bounds, failure states, lifecycle stages, and safety boundaries.
- Validate response-quality properties without exact wording.
- Document and expose a production-safe representative live sweep matrix.
- Keep frontend polish checks focused on labels, menus, chooser/progress/error states, and responsive wrapping.

## Non-Goals

- No new AI workflows or features.
- No redesign of routing, buttons, or model selection.
- No VM access, deployment, commit, push, model install, or runtime configuration changes.
- No broad unrelated refactor.
