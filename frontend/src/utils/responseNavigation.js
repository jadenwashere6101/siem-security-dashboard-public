/**
 * Cross-workspace navigation targets for Response Registry and related SOAR views.
 * Uses App activeSection architecture (no React Router).
 */

export const REGISTRY_SECTION_ID = "response-registry";

export function buildRegistryNavigation({
  view = "all",
  q = "",
  relatedAlertId = null,
  relatedIncidentId = null,
  relatedPlaybookExecutionId = null,
  relatedApprovalRequestId = null,
  sourceIp = "",
} = {}) {
  const indicator = String(q || sourceIp || "").trim();
  return {
    sectionId: REGISTRY_SECTION_ID,
    view,
    q: indicator,
    relatedAlertId: relatedAlertId == null || relatedAlertId === "" ? null : Number(relatedAlertId),
    relatedIncidentId:
      relatedIncidentId == null || relatedIncidentId === ""
        ? null
        : Number(relatedIncidentId),
    relatedPlaybookExecutionId:
      relatedPlaybookExecutionId == null || relatedPlaybookExecutionId === ""
        ? null
        : Number(relatedPlaybookExecutionId),
    relatedApprovalRequestId:
      relatedApprovalRequestId == null || relatedApprovalRequestId === ""
        ? null
        : Number(relatedApprovalRequestId),
  };
}

export function registryNavFromSourceIp(sourceIp, extras = {}) {
  return buildRegistryNavigation({
    view: extras.view || "all",
    sourceIp,
    relatedAlertId: extras.relatedAlertId,
    relatedIncidentId: extras.relatedIncidentId,
    relatedPlaybookExecutionId: extras.relatedPlaybookExecutionId,
    relatedApprovalRequestId: extras.relatedApprovalRequestId,
  });
}

export function registryNavFromAlert(alert) {
  if (!alert) return buildRegistryNavigation();
  return buildRegistryNavigation({
    view: "all",
    sourceIp: alert.source_ip,
    relatedAlertId: alert.id,
  });
}

export function registryNavFromIncident(incident) {
  if (!incident) return buildRegistryNavigation();
  return buildRegistryNavigation({
    view: "all",
    sourceIp: incident.source_ip,
    relatedIncidentId: incident.id,
  });
}

/** Map SOC Command Center attention labels to authoritative workspaces. */
export const ATTENTION_NAV_TARGETS = {
  "Stale running executions": { sectionId: "soar-playbooks" },
  "Pending approvals": { sectionId: "soar-approvals", statusFilter: "pending" },
  "Open or retrying dead letters": { sectionId: "soar-operations" },
  "Failed playbooks": { sectionId: "soar-playbooks" },
  "Notification failures": { sectionId: "soar-operations" },
  "Queue pressure": { sectionId: "soar-queue" },
  "Degraded integrations": { sectionId: "soar-integrations" },
};

export function attentionNavTarget(label) {
  return ATTENTION_NAV_TARGETS[label] || { sectionId: "soar-operations" };
}
