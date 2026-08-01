# Proposal: Anakin Analyst Reasoning And Personality

## Summary

Upgrade Anakin's AI behavior from field-summary responses to practical Detection Engineer reasoning across the six canonical workflows. This change adds a shared persona/reasoning policy, keeps workflow-specific prompt templates separate, and adds prompt-contract and golden acceptance tests that check reasoning properties rather than exact wording.

## Motivation

The consolidated workflow architecture gives Anakin reliable routing and fewer UI entry points, but the analyst value depends on the quality of the answer. Anakin should add judgment beyond visible SIEM facts: what stands out, what weakens the initial theory, what evidence is missing, and what the analyst should inspect next.

## Goals

- Reuse one shared Detection Engineer persona/reasoning policy across relevant workflow prompts.
- Keep Quick Explain concise, conversational, bounded, and tool-free.
- Make Deep Investigate require support, contradiction/benign explanations, gaps, confidence, and prioritized next steps.
- Keep Decision Support separate from drafting and applying artifacts.
- Improve Generate Artifact prompts while preserving schemas, validation, and bounded repair.
- Make SOC Briefing prioritize analyst attention instead of listing everything.
- Make Repo Assistant distinguish repository facts from architectural judgment.
- Add golden acceptance cases for realistic SOC and repo questions using reasoning-property checks.

## Non-Goals

- No new routing architecture, buttons, or UI redesign.
- No model, runtime, provider, RBAC, sanitization, or production configuration changes.
- No VM access, deployment, commit, push, or paid fallback behavior.
- No hardcoded conclusions or canned response text.

## Scope

Mac AI source changes only:

- prompt/policy helpers under `core/ai/`;
- workflow prompt integration in existing AI services;
- prompt-contract and golden acceptance tests;
- acceptance harness quality checks.
