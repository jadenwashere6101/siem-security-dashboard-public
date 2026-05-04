# Backend package refactor plan

Status snapshot: package layout is largely migrated; **three flat `backend_*.py` engine modules remain** at the repo root. Full test suite has stayed green through the moves (**116 passed**, **2 warnings**).

---

## 1. Completed moves (current)

- **`core/`** — `auth`, `audit_helpers`, `db`, `extensions`, `ip_helpers`
- **`helpers/`** — `api_guards`, `enrichment_helpers`, `ingest_normalizers`, `pdf_helpers`, `query_helpers`, `reporting_helpers`
- **`routes/`** — `auth_routes`, `admin_routes`, `alert_mutation_routes`, `alerts_events_routes`, `blocklist_routes`, `ingest_routes`, `reporting_routes`
- **`engines/`** — `detection_config.py` (detection rule config / DB-backed helpers)

App shell remains **`siem_backend.py`** (Flask factory, blueprints, health, static catch-all).

---

## 2. Current package structure (high level)

| Package | Role |
|---------|------|
| `core/` | Auth, audit, DB connection factory, shared limiter, IP/reputation/response helpers |
| `helpers/` | Pure or low-coupling helpers (enrichment, CSV/query, PDF, normalizers, API key guards) |
| `routes/` | Flask blueprints (HTTP surface) |
| `engines/` | Detection configuration module (moved); engine orchestration still partly flat (see below) |

---

## 3. Remaining flat backend files (verified)

Repo root still contains exactly these three (glob verified):

- `backend_detection_engine.py`
- `backend_correlation_engine.py`
- `backend_ingest_engine.py`

Everything else from the earlier “flat `backend_*`” refactor wave now lives under `core/`, `helpers/`, `routes/`, or `engines/detection_config.py`.

---

## 4. Pause before SOAR

Stop further **package relocation** (especially engines) before SOAR work so that:

- Playbooks, automation, and response flows can land without fighting large import-tree and merge churn.
- Behavioral tests stay stable; SOAR changes will already touch orchestration and alert/action boundaries.

The refactor goal for the **library vs surface** split is already achieved for core/helpers/routes/detection config.

---

## 5. Why the last three files are “later” (risky)

They **can** be moved under `engines/` (or similar) in a **dedicated** phase, but they are **not** low-risk drive-by moves:

- **Tests patch them by legacy module path** (e.g. `patch("backend_detection_engine.lookup_ip_reputation", ...)`, ingest orchestration patches on `backend_ingest_engine.*`).
- **Tests import** `backend_detection_engine` and `backend_correlation_engine` directly for behavioral coverage.
- **`backend_ingest_engine`** re-imports correlation entrypoints onto its own module namespace so `unittest.mock` can substitute them; moving the real body without updating patch targets can **silently stop mocks from applying** even if some tests still pass.

---

## 6. Next future step: dedicated engine migration phase

Schedule **one focused PR/phase** for engine migration **separate from SOAR** feature work. That phase should include:

- Inventory of all `patch("backend_*engine`…)` and direct `import backend_*engine` usages.
- Mechanical move + **explicit** patch/import updates in the **same** change set.
- Full + focused pytest runs (see below).

Do **not** interleave this with SOAR delivery unless SOAR explicitly requires the new layout.

---

## 7. Verification commands (current state)

From repo root:

```bash
cd /Users/jadengomez/Desktop/siem-security-dashboard-public
python3 -m pytest tests/ -q
```

Optional verbosity:

```bash
python3 -m pytest tests/ -v --tb=short
```

---

## 8. Future engine migration — warnings

- **Patch targets:** Update every `patch("backend_…")` string to match the **module where the running code resolves** the name (not a dead re-export shim).
- **Avoid shims that void mocks:** A thin `backend_*` wrapper that re-exports from `engines/*` while implementation calls `lookup_ip_reputation` from **`engines.*`’s own globals** can leave tests patching the **wrong** module — mocks appear to run but **do not** affect code under test.
- **Test count:** Keep the suite at **116** passing (fix failures; do not “fix” by dropping tests).
- **Focused runs** after engine moves:

```bash
python3 -m pytest tests/test_ingest_normalized_event.py -v --tb=short
python3 -m pytest tests/test_correlated_activity.py tests/test_targeted_correlation.py -v --tb=short
python3 -m pytest tests/test_failed_login_detection.py tests/test_port_scan_detection.py -v --tb=short
```

(Expand the detection list to all `tests/test_*_detection.py` files as needed.)

---

## Related docs

- `docs/MODULARIZATION_HANDOFF.md` — broader modularization history and boundaries.
