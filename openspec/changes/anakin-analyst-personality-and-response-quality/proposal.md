# anakin-analyst-personality-and-response-quality

## Summary

Strengthen Anakin's shared persona and response-quality contract so every canonical workflow sounds like a practical Detection Engineer teammate rather than a generic assistant.

This is a prompt architecture, persona, response-contract, and acceptance-quality change. It does not change models, workflow routing, async execution, production runtime configuration, UI controls, VM services, or deployment behavior.

## Problem

The current six-workflow architecture is functional, but Anakin can still drift into generic AI assistant phrasing, visible-field repetition, over-structured explanations, or weak recommendations that do not add analyst value. That makes successful responses feel less useful than the underlying workflow architecture now supports.

## Goals

- Create one canonical reusable backend personality and response-quality contract shared by all Anakin workflows.
- Make Anakin direct, concise, practical, skeptical of weak evidence, conversational, and honest about uncertainty.
- Make responses lead with useful judgment instead of boilerplate.
- Adapt tone to the user's style while staying professional and conservative.
- Preserve professional artifact/SOC briefing output with no slang or profanity.
- Add acceptance coverage that rejects filler phrases, visible-field repetition, generic monitoring advice, and unsupported certainty.

## Non-Goals

- No model upgrade.
- No architecture redesign.
- No new workflow, route, button, queue, or deployment behavior.
- No frontend redesign unless tests reveal presentation-only wording dependencies.
- No VM access, deployment, runtime config, commit, or push.

## Constraints

- Preserve local-only mode, RBAC, read-only boundaries, preview/confirm gates, model profile routing, sanitization, audit logging, no-paid-fallback behavior, and production acceptance policy.
- Keep workflow-specific prompt templates separate.
- Do not create a theatrical persona or roleplay layer. The tone should feel like a practical engineer, not a scripted character.
- Do not make operational recommendations stronger than the supplied evidence supports.
- Keep responses short by default and deeper only when the workflow or user request calls for it.

## Production Completion

Follow `docs/anakin-production-acceptance-policy.md`. This source-only implementation may not be described as working, done, fully verified, or production-ready until deployed browser-path verification is completed after commit/deployment.
