# Gradual Cleanup Roadmap

This roadmap turns the current organization recommendations into small, safe Codex prompts.

## Cleanup Principles

- Prefer comments, spacing, and navigation improvements before any reordering.
- Prefer documentation clarity before structural refactor.
- Stop cleanup when diffs become noisy without adding clear readability or safety value.
- Avoid “organization” work that quietly changes execution flow, ownership, or behavior.
- Treat large files as stabilization targets first, refactor targets later.

## Step 1

**Goal**

Improve `siem_backend.py` readability with comments and spacing only.

**Exact Prompt**

```text
Safe backend readability cleanup.

Repo:
 /Users/jadengomez/Desktop/siem-security-dashboard-public

File:
 siem_backend.py

Goal:
Improve readability without changing behavior.

Rules:
- Do NOT split files.
- Do NOT move code across major sections.
- Do NOT change logic.
- Do NOT rename anything.
- Do NOT touch SQL.
- Do NOT modify routes, ingestion, detection, or correlation behavior.
- Do NOT change audit event strings.
- Do NOT change DB connection handling.

Allowed:
- Add or improve section comments
- Add small subsection comments inside existing sections
- Remove obvious duplicate blank lines
- Improve visual spacing only

After:
- Show exact diff
- Run:
  python3 -m py_compile siem_backend.py
- Do NOT commit
```

**Risk Level**

Low

**Why This Step Comes Before the Next One**

`siem_backend.py` is the largest context sink in the repo. Making it easier to scan reduces the chance of bad edits in every later backend task.

---

## Step 2

**Goal**

Improve `AlertsTable.js` readability and internal structure without changing UI behavior.

**Exact Prompt**

```text
Safe frontend readability cleanup.

Repo:
 /Users/jadengomez/Desktop/siem-security-dashboard-public

File:
 frontend/src/components/AlertsTable.js

Goal:
Improve readability without changing behavior.

Rules:
- Do NOT split files.
- Do NOT move logic into new components.
- Do NOT change rendering behavior.
- Do NOT change filtering, sorting, grouping, timeline, badge, export, note, or action behavior.
- Do NOT change API usage.
- Do NOT add dependencies.

Allowed:
- Add section comments
- Add subsection comments for style groups and UI behavior groups
- Remove obvious duplicate blank lines
- Improve visual spacing only

After:
- Show exact diff
- Run:
  cd frontend && npm run build
- Do NOT commit
```

**Risk Level**

Low

**Why This Step Comes Before the Next One**

Once the two biggest high-context files are easier to read, future AI-assisted edits become safer. After that, repo-level documentation can point to clearer file boundaries.

---

## Step 3

**Goal**

Turn the root `README.md` into a better contributor and AI navigation map.

**Exact Prompt**

```text
Safe README organization pass.

Repo:
 /Users/jadengomez/Desktop/siem-security-dashboard-public

File:
 README.md

Goal:
Keep the project overview strong while making the repo easier to navigate for contributors and AI agents.

Rules:
- Do NOT change application logic.
- Do NOT invent features that do not exist.
- Do NOT remove the main project overview.
- Keep edits concise and practical.

Add:
- a short "Repo Map" section
- backend entrypoint path
- frontend core file paths
- adapter file paths
- Azure Function file paths
- scripts overview
- docs / OpenSpec locations

After:
- Show exact diff
- Do NOT commit
```

**Risk Level**

Low

**Why This Step Comes Before the Next One**

Once the big files are easier to scan, the README can accurately guide future work without pointing people into a confusing structure.

---

## Step 4

**Goal**

Clarify Azure documentation ownership and reduce setup/debug confusion.

**Exact Prompt**

```text
Safe Azure docs clarification pass.

Repo:
 /Users/jadengomez/Desktop/siem-security-dashboard-public

Files:
- docs/azure-integration-setup.md
- siem-azure-function/AZURE_TIMER_DEBUG.md
- Optional: README.md short link only if helpful

Goal:
Make it obvious which Azure doc is for setup/demo flow and which doc is for runtime debugging.

Rules:
- Documentation only
- Do NOT change code
- Do NOT add secret values
- Keep existing useful setup and troubleshooting content
- Keep wording concise

Required:
- setup/demo guide clearly owns end-to-end plug-and-play flow
- timer debug guide clearly owns invocation/runtime troubleshooting
- keep placeholder curl examples only
- add or improve cross-links between the two docs

After:
- Show exact diff
- Do NOT commit
```

**Risk Level**

Low

**Why This Step Comes Before the Next One**

This reduces operational confusion before touching smaller technical docs and scripts. It also gives future AI sessions a clearer documentation source of truth.

---

## Step 5

**Goal**

Improve small-file discoverability across adapters and scripts with comments or lightweight docs only.

**Exact Prompt**

```text
Safe small-file organization pass.

Repo:
 /Users/jadengomez/Desktop/siem-security-dashboard-public

Files likely:
- adapters/azure_insights_adapter.py
- adapters/otel_adapter.py
- adapters/nginx_adapter.py
- scripts/ingest_log_files.py
- Optional: docs or README pointer for script purpose

Goal:
Improve discoverability and future AI-assisted editing without changing behavior.

Rules:
- Do NOT change logic
- Do NOT change normalization behavior
- Do NOT change script behavior
- Do NOT add dependencies
- Do NOT extract shared utilities yet

Allowed:
- add short module-level comments
- add tiny comments explaining supported input shapes or intended scope
- add script-purpose notes
- improve spacing only

After:
- Show exact diff
- Run:
  python3 -m py_compile adapters/azure_insights_adapter.py adapters/otel_adapter.py adapters/nginx_adapter.py scripts/ingest_log_files.py
- Do NOT commit
```

**Risk Level**

Low

**Why This Step Comes Before the Next One**

By this point, the major hotspots and docs are clearer. This final small-file pass helps future AI tools work faster without jumping too early into real refactors.
