/**
 * Concise analyst-facing labels for canonical response dispositions / actions.
 */

import { outcomeLabel } from "./responseOutcomeDisplay";

const DISPOSITION_LABELS = {
  observed: "Observed",
  monitored: "Monitored",
  escalated: "Escalated",
  pending: "Pending",
  blocklist_tracked: "Blocked (tracking)",
  rejected: "Rejected",
  failed: "Failed",
  expired: "Expired",
  removed: "Removed",
};

const ACTION_LABELS = {
  block_ip: "Block requested",
  monitor: "Monitored",
  flag_high_priority: "Escalated",
  stop_monitor: "Monitoring stopped",
  remove_tracking: "Tracking removed",
  add_note: "Note recorded",
};

export function dispositionSummaryLabel(disposition) {
  if (!disposition) return null;
  return DISPOSITION_LABELS[disposition] || String(disposition).replace(/_/g, " ");
}

export function actionSummaryLabel(action) {
  if (!action) return null;
  return ACTION_LABELS[action] || String(action).replace(/_/g, " ");
}

export function summarizeAlertResponseState(alert) {
  if (!alert) return { label: "No response recorded", detail: null };
  const action = alert.response_action || null;
  const outcome = alert.response_outcome || null;
  const status = alert.response_status || null;

  // Canonical ResponseOutcome is authoritative over legacy alerts.response_status.
  if (outcome && outcome.execution_mode) {
    return {
      label: outcomeLabel(outcome),
      detail: actionSummaryLabel(action),
    };
  }

  if (!action) {
    return { label: "No response recorded", detail: null };
  }
  if (status === "awaiting_approval" || status === "pending") {
    return {
      label: "Pending approval",
      detail: actionSummaryLabel(action),
    };
  }
  if (status === "failed" || status === "rejected") {
    return {
      label: status === "rejected" ? "Rejected" : "Failed",
      detail: actionSummaryLabel(action),
    };
  }
  return {
    label: actionSummaryLabel(action) || "Response recorded",
    detail: status ? `Legacy status (non-authoritative): ${status}` : null,
  };
}

export const LIFECYCLE_INDEPENDENCE_COPY =
  "Alert status, incident status, response disposition, approval state, and playbook execution " +
  "state are independent. Tracking an IP in the Blocklist or monitoring an indicator does not " +
  "automatically resolve the alert or close the incident.";

export function formatCanonicalActionSuccess(result, action) {
  if (!result || typeof result !== "object") {
    return `Action "${action}" completed successfully`;
  }
  const parts = [];
  if (result.message) {
    parts.push(result.message);
  } else if (result.outcome_label) {
    parts.push(`Outcome: ${result.outcome_label}`);
  } else {
    parts.push(`Action "${action}" completed successfully`);
  }
  if (result.idempotent) {
    parts.push("(idempotent reuse)");
  }
  if (result.blocked_ip_id != null) {
    parts.push(`Blocklist ID ${result.blocked_ip_id}`);
  }
  if (result.registry_record_id != null) {
    parts.push(`Registry #${result.registry_record_id}`);
  }
  if (result.incident_id != null) {
    parts.push(`Incident #${result.incident_id}`);
  }
  if (result.enforcement === "none" || result.enforcement === "tracking_only") {
    parts.push("No firewall or host enforcement.");
  }
  return parts.join(" · ");
}
