# Scheduled SOC Briefing Runtime VM Handoff

Use only after an approved Mac commit/push. Do not edit source on the VM.

## VM Steps

1. Confirm VM worktree is clean with `git status --short`.
2. Sync only the approved commit using the Mac/VM source-of-truth policy.
3. Run `bash scripts/deploy_backend_vm.sh --dry-run-migrations`.
4. Run `bash scripts/deploy_backend_vm.sh`.
5. Confirm `soc-briefing-worker.timer` and `soc-briefing-worker.service` were installed by the deployment helper.
6. Inspect `systemctl status soc-briefing-worker.timer --no-pager`.
7. Inspect `systemctl cat soc-briefing-worker.service soc-briefing-worker.timer --no-pager`.
8. Confirm backend health and `/metrics/soc-briefing-worker` through an authenticated analyst or super-admin session.

## Expected Runtime State

- Existing schedules are disabled by default unless deliberately configured later.
- The timer may run the foundation worker, but it does not generate briefing content, send Slack, call paid providers, or mutate production data.
- Missing AI Gateway or Mini PC readiness is recorded as blocked/unavailable runtime state.

## Rollback

Stop and disable the timer and service, restore the prior approved commit through the normal VM sync process, rerun the deployment helper, and preserve additive runtime tables unless a separate approved rollback is provided.
