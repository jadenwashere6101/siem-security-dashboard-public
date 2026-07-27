# Navigation History Workflow

The SIEM header includes workspace Back and Forward controls for analyst investigation flow. These controls restore lightweight workspace context inside the current session without introducing React Router or storing fetched datasets.

## Restored State

Workspace history restores the active workspace, meaningful selected records, dashboard alert filters, exact alert/source/target pivots, pagination, supported panel filters, and best-effort main-container scroll position. Browser Back and Forward restore SIEM-owned history entries through `window.history.state` markers.

Supported restoration includes Dashboard alert context, Response Registry navigation requests, SOC Command Center selections, Recon History filters and pagination, SOAR Queue filters and selected queue item, and existing Incidents, Approvals, and Playbooks initial-request pivots.

## Intentionally Excluded

Snapshots do not store API response datasets, secrets, transient loading/error state, AI responses, or raw service payloads. Search keystrokes and minor UI changes update the current snapshot where supported, but they do not create new history entries.

## Clearing Boundaries

Workspace history is cleared when authentication fails, logout/account switch occurs, or a restored workspace is no longer visible for the active role. Hidden or stale destinations fall back safely instead of exposing unavailable workspaces.

## Verification

Implementation verification should cover header Back/Forward disabled states, sidebar and programmatic pivots, browser Back/Forward, restored filters and selected records, best-effort scroll restoration, responsive header layout, and session clearing. VM sync is required after implementation because the production frontend bundle must be rebuilt and deployed from the Mac source of truth.
