# Workspace Navigation & Detail UX — Frontend Deployment Handoff

Owner: **VM AI** (after explicit commit/push/deploy authorization).  
Mac change: `fix-workspace-navigation-and-detail-ux` (complete).

Mac source of truth: `/Users/jadengomez/Projects/siem-security-dashboard-public`  
VM runtime: `jaden@4.204.25.149:/home/jaden/siem-security-dashboard`

**NOT AUTHORIZED to deploy from this handoff alone.** Wait for an explicit deploy request naming an approved commit SHA.

## Change summary

Frontend-only: destination-aware workspace navigation (scroll/focus on the real `<main>` container) and responsive master-detail detail panes for Incidents, Playbooks, and SOAR Operations/Dead Letters. No backend, schema, migration, or service changes.

## Prerequisites

1. Mac implementation validated (tests, `npm run build`, OpenSpec strict validate, `git diff --check`).
2. Explicit authorization to **commit**, then **push**, then **deploy** the approved commit.
3. VM worktree clean (`git status --short` empty).
4. Approved commit SHA recorded before sync.

## Approved artifact requirement

- Deploy only the Mac-built frontend artifact from the approved commit:
  - Build on Mac: `cd frontend && npm run build`
  - Artifact path: `frontend/build/`
- Do **not** rebuild from a dirty or divergent VM tree.
- Backend restart: **not required**.
- Migrations: **none**.

## Deployment sequence (after authorization)

1. **Clean-tree check (VM)**
   ```bash
   cd /home/jaden/siem-security-dashboard
   git status --short
   ```
   Stop if any output.

2. **Sync approved commit**
   ```bash
   git fetch origin
   git reset --hard <APPROVED_COMMIT_SHA>
   ```
   Confirm `git rev-parse HEAD` matches the approved SHA.

3. **Deploy frontend artifact** (from Mac build of that SHA)
   ```bash
   rsync -avz --delete \
     -e "ssh -i ~/.ssh/jadeng15.pem" \
     /Users/jadengomez/Projects/siem-security-dashboard-public/frontend/build/ \
     jaden@4.204.25.149:/home/jaden/siem-security-dashboard/frontend/build/
   ```

4. **UI smoke (sanitized)**
   - Sidebar: switch workspaces → lands at top; focus on workspace heading.
   - SOC Command Center: ordinary nav and Pending approvals / Open in Response Registry.
   - Related alerts / Response Registry deep links retain source-IP and correlation IDs.
   - Incidents, Playbooks, Dead Letters: View opens adjacent/stacked detail; Close returns focus.
   - Dark theme and narrow viewport: detail stacks below list; no horizontal overflow.
   - Reduced motion: scroll behavior is instant (`auto`), not animated.

## Rollback

- Redeploy the previous approved frontend artifact / prior commit’s `frontend/build/`.
- No data rollback. No migration reverse.

## Stop conditions

- Dirty VM worktree.
- Approved SHA missing or HEAD mismatch.
- Any request to edit VM source, add React Router, or change APIs for this feature.
