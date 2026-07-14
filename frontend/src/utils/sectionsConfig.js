import { LIVE_LOG_SECTIONS } from "./sourceMetadata";

export const sectionsConfig = [
  {
    id: "dashboard",
    label: "Dashboard",
    group: "overview",
    visibleWhen: () => true,
  },
  {
    id: "source-health",
    label: "Source Health",
    group: "overview",
    visibleWhen: ({ canTakeAlertActions }) => canTakeAlertActions,
  },
  {
    id: "soc-command-center",
    label: "SOC Command Center",
    group: "soc",
    visibleWhen: ({ canTakeAlertActions }) => canTakeAlertActions,
  },
  {
    id: "severity-response-matrix",
    label: "Severity & Response Matrix",
    group: "soc",
    visibleWhen: ({ canTakeAlertActions }) => canTakeAlertActions,
  },
  {
    id: "response-registry",
    label: "Response Registry",
    group: "soc",
    visibleWhen: ({ canTakeAlertActions }) => canTakeAlertActions,
  },
  {
    id: "threat-hunt",
    label: "Threat Hunt",
    group: "soc",
    visibleWhen: ({ canTakeAlertActions }) => canTakeAlertActions,
  },
  {
    id: "detection-simulator",
    label: "Detection Simulator",
    group: "soc",
    visibleWhen: ({ canTakeAlertActions }) => canTakeAlertActions,
  },
  ...LIVE_LOG_SECTIONS,
  {
    id: "detection-rules",
    label: "Detection Rules",
    group: "administration",
    visibleWhen: ({ isSuperAdmin }) => isSuperAdmin,
  },
  {
    id: "pfsense-ingest-filters",
    label: "pfSense Ingest Filters",
    group: "administration",
    visibleWhen: ({ isSuperAdmin }) => isSuperAdmin,
  },
  {
    id: "notification-policy",
    label: "Notification Policy",
    group: "administration",
    visibleWhen: ({ isSuperAdmin }) => isSuperAdmin,
  },
  {
    id: "admin-users",
    label: "User Management",
    group: "administration",
    visibleWhen: ({ isSuperAdmin }) => isSuperAdmin,
  },
  {
    id: "admin-audit-logs",
    label: "Audit Logs",
    group: "administration",
    visibleWhen: ({ isSuperAdmin }) => isSuperAdmin,
  },
  {
    id: "soar-queue",
    label: "SOAR Queue",
    group: "soar",
    visibleWhen: ({ isSuperAdmin }) => isSuperAdmin,
  },
  {
    id: "soar-incidents",
    label: "SOAR Incidents",
    group: "soar",
    visibleWhen: ({ canTakeAlertActions }) => canTakeAlertActions,
  },
  {
    id: "soar-approvals",
    label: "SOAR Approvals",
    group: "soar",
    visibleWhen: ({ canTakeAlertActions }) => canTakeAlertActions,
  },
  {
    id: "soar-playbooks",
    label: "SOAR Playbooks",
    group: "soar",
    visibleWhen: ({ canTakeAlertActions }) => canTakeAlertActions,
  },
  {
    id: "soar-playbook-metrics",
    label: "SOAR Metrics",
    group: "soar",
    visibleWhen: ({ canTakeAlertActions }) => canTakeAlertActions,
  },
  {
    id: "soar-integrations",
    label: "SOAR Integrations",
    group: "soar",
    visibleWhen: ({ canTakeAlertActions }) => canTakeAlertActions,
  },
  {
    id: "soar-operations",
    label: "SOAR Operations",
    group: "soar",
    visibleWhen: ({ canTakeAlertActions }) => canTakeAlertActions,
  },
  {
    id: "settings",
    label: "Settings",
    group: "settings",
    visibleWhen: () => true,
  },
];

export const isSectionVisible = (sectionId, roleFlags) => {
  const section = sectionsConfig.find((entry) => entry.id === sectionId);
  return section ? section.visibleWhen(roleFlags) : false;
};

/**
 * Legacy standalone Blocklist nav/landing IDs normalize to Response Registry.
 * Returns { sectionId, registryView } without creating a second state source.
 */
export const normalizeWorkspaceDestination = (sectionId) => {
  const normalized = String(sectionId || "").trim();
  if (normalized === "blocklist") {
    return { sectionId: "response-registry", registryView: "blocklist_tracking" };
  }
  return { sectionId: normalized, registryView: null };
};
