# Scheduled SOC Briefing Runtime VM Handoff

Use only after an approved Mac commit/push. Do not edit source on the VM.

## VM Steps

1. Confirm VM worktree is clean with `git status --short`.
2. Sync only the approved commit using the Mac/VM source-of-truth policy.
3. Run `bash scripts/deploy_backend_vm.sh --dry-run-migrations`.
4. Run `bash scripts/deploy_backend_vm.sh`.
5. Confirm migration `0027_soc_briefing_delivery_attempts.sql` is present in the approved source before applying migrations.
6. Confirm `soc-briefing-worker.timer` and `soc-briefing-worker.service` were installed by the deployment helper.
7. Inspect `systemctl status soc-briefing-worker.timer --no-pager`.
8. Inspect `systemctl cat soc-briefing-worker.service soc-briefing-worker.timer --no-pager`.
9. Confirm backend health and `/metrics/soc-briefing-worker` through an authenticated analyst or super-admin session.
10. Confirm an analyst or super-admin can open the SOC Briefings workspace and read saved history/detail records after migrations are applied.

## Expected Runtime State

- Existing schedules are disabled by default unless deliberately configured later.
- The timer may run bounded read-only investigations and persist structured briefing content.
- Saved briefing history is sourced from `soc_briefings`; Slack delivery status is sourced from `soc_briefing_delivery_attempts`.
- Optional Slack summaries are best-effort. Disabled, blocked, failed, or retry-scheduled Slack state must not change or remove the saved briefing.
- The timer and briefing UI must not call paid providers outside policy, create drafts, execute SOAR actions, approve/deny work, mutate incidents or notes, or mutate production data.
- Missing AI Gateway or Mini PC readiness is recorded as blocked/unavailable runtime state, and saved evidence/partial briefing state remains durable.
- Microsoft Teams delivery remains out of scope.

## Rollback

Stop and disable the timer and service, restore the prior approved commit through the normal VM sync process, rerun the deployment helper, and preserve additive runtime tables unless a separate approved rollback is provided.
