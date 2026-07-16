import { actionSummaryLabel, dispositionSummaryLabel } from "./responseStateLabels";

export function registryOutcomeLabel({
  currentDisposition = null,
  latestOutcome = null,
  latestRequestedAction = null,
  enforcement = null,
  safeMetadata = {},
} = {}) {
  const outcome = String(latestOutcome || "").trim().toLowerCase();
  const action = String(latestRequestedAction || "").trim().toLowerCase();
  const disposition = String(currentDisposition || "").trim().toLowerCase();
  const mode = String(enforcement || "").trim().toLowerCase();

  if (outcome === "awaiting_approval" || outcome === "pending" || disposition === "pending") {
    return "Awaiting Approval";
  }
  if (disposition === "monitored" || action === "monitor") {
    return "Monitoring";
  }
  if (
    mode === "tracking_only" ||
    disposition === "blocklist_tracked" ||
    outcome === "tracking_recorded" ||
    outcome === "idempotent_reuse"
  ) {
    return "Tracking Only";
  }
  if (safeMetadata?.simulated === true || outcome === "simulated") {
    return "Simulated";
  }
  if (outcome === "skipped" || outcome === "policy_blocked") {
    return "Skipped";
  }
  if (outcome === "failed" || disposition === "failed") {
    return "Failed";
  }
  if (
    outcome === "rejected" ||
    disposition === "rejected" ||
    outcome === "removed" ||
    outcome === "recorded"
  ) {
    return "Not Actioned";
  }
  if (outcome === "succeeded" || outcome === "escalated" || outcome === "renewed") {
    return "Executed";
  }
  return "Not Actioned";
}

export function registryOutcomeTone(label) {
  if (label === "Executed") return "success";
  if (label === "Awaiting Approval" || label === "Monitoring" || label === "Tracking Only") {
    return "warning";
  }
  if (label === "Simulated") return "info";
  if (label === "Skipped" || label === "Not Actioned") return "neutral";
  if (label === "Failed") return "danger";
  return "neutral";
}

export function registryActionLabel(action, disposition) {
  return actionSummaryLabel(action) || dispositionSummaryLabel(disposition) || "No response recorded";
}

export function registryInvestigateTarget(detail, fallback = {}) {
  const primaryIncidentId =
    detail?.relationships?.incidents?.primary_id ?? fallback.relatedIncidentId ?? null;
  if (primaryIncidentId != null) {
    return { kind: "incident", id: Number(primaryIncidentId), label: "Investigate related incident." };
  }

  const primaryAlertId = detail?.relationships?.alerts?.primary_id ?? fallback.relatedAlertId ?? null;
  if (primaryAlertId != null) {
    return {
      kind: "alert",
      id: Number(primaryAlertId),
      sourceIp:
        detail?.primary_alert?.source_ip ||
        detail?.record?.indicator_value ||
        fallback.sourceIp ||
        "",
      label: "Investigate originating alert.",
    };
  }

  const sourceIp = String(
    detail?.primary_alert?.source_ip ||
      detail?.primary_incident?.source_ip ||
      detail?.record?.indicator_value ||
      fallback.sourceIp ||
      ""
  ).trim();
  if (sourceIp) {
    return {
      kind: "source_ip",
      sourceIp,
      label: "Investigate source/IP context.",
    };
  }

  return {
    kind: "none",
    label: "No related incident, alert, or source/IP context is available for investigation.",
  };
}

export function registryRecommendedNextStep(detail, fallback = {}) {
  const investigateTarget = registryInvestigateTarget(detail, fallback);
  const latestEvent = detail?.latest_event || {};
  const currentDisposition = detail?.record?.current_disposition || "";
  const approvalStatus = String(detail?.primary_approval_request?.status || "").trim().toLowerCase();

  if (approvalStatus === "pending" || latestEvent.outcome === "awaiting_approval") {
    return "Awaiting analyst approval.";
  }
  if (investigateTarget.kind === "incident") {
    return "Investigate related incident.";
  }
  if (investigateTarget.kind === "alert") {
    return "Investigate originating alert.";
  }
  if (currentDisposition === "monitored") {
    return "Monitoring active.";
  }
  return "No further analyst action required.";
}
