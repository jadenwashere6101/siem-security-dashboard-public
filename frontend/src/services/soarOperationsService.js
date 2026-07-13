import { getApiErrorMessage, parseJsonResponse } from "../utils/apiResponse";
import { buildSiemPath } from "../utils/siemPath";

const fallbackSummary = {
  window_hours: 24,
  counts: {
    running_playbooks: 0,
    awaiting_approval_playbooks: 0,
    active_playbooks: 0,
    pending_approvals: 0,
    recently_expired_denied: 0,
    failed_executions: 0,
    actionable_dead_letters: 0,
  },
  running_playbooks: { count: 0, running_count: 0, awaiting_approval_count: 0, items: [] },
  pending_approvals: { count: 0, items: [] },
  recently_expired_denied: { count: 0, window_hours: 24, items: [] },
  failed_executions: { count: 0, items: [] },
  actionable_dead_letters: { count: 0, open_count: 0, items: [] },
  legacy_expected_backlog: { open_count: 0, review_mode: "individual_reason_logged_dismissal_only" },
};

export async function loadSoarOperationsSummary() {
  const res = await fetch(buildSiemPath("/metrics/soar-operations"), {
    credentials: "include",
  });
  const data = await parseJsonResponse(res, fallbackSummary);

  if (!res.ok) {
    throw new Error(
      getApiErrorMessage(data, "Unable to load SOAR operations summary", ["error"])
    );
  }

  return data;
}
