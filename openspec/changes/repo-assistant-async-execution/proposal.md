# repo-assistant-async-execution

## Summary

Move normal Repo Assistant answer generation off synchronous nginx-held requests and into durable queued/polling execution.

## Problem

Production testing after commit `1d8437f` confirmed `POST /ai/repo/chat` can exceed nginx's 60-second proxy timeout while the `developer_assistant` profile allows up to 120 seconds.

## Goals

- Preserve immediate live-SIEM boundary responses without queueing or repository retrieval.
- Queue normal factual, architectural, and evaluative repo questions.
- Poll request status until terminal.
- Reuse existing durable Anakin workflow request architecture where safe.
- Preserve super-admin RBAC, repo-only retrieval, backend-owned citations, developer_assistant profile, and no-paid-fallback behavior.

## Non-Goals

- No normal Anakin auto-routing for Repo Assistant.
- No new memory or conversation continuity.
- No repo content exposure to unauthorized users.
- No VM access, deployment, commit, push, or runtime configuration changes.
