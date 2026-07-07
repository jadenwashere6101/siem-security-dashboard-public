export const sectionsConfig = [
  {
    id: "dashboard",
    label: "Dashboard",
    group: "overview",
    visibleWhen: () => true,
  },
  {
    id: "soc-command-center",
    label: "SOC Command Center",
    group: "soc",
    visibleWhen: ({ canTakeAlertActions }) => canTakeAlertActions,
  },
  {
    id: "blocklist",
    label: "Blocklist",
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
    id: "live-logs-honeypot",
    label: "Honeypot",
    group: "live logs",
    source: "honeypot",
    visibleWhen: ({ canTakeAlertActions }) => canTakeAlertActions,
  },
  {
    id: "live-logs-bank-app",
    label: "Bank App",
    group: "live logs",
    source: "bank_app",
    visibleWhen: ({ canTakeAlertActions }) => canTakeAlertActions,
  },
  {
    id: "live-logs-pfsense",
    label: "pfSense",
    group: "live logs",
    source: "pfsense",
    visibleWhen: ({ canTakeAlertActions }) => canTakeAlertActions,
  },
  {
    id: "live-logs-nginx",
    label: "NGINX",
    group: "live logs",
    source: "nginx",
    visibleWhen: ({ canTakeAlertActions }) => canTakeAlertActions,
  },
  {
    id: "live-logs-azure",
    label: "Azure",
    group: "live logs",
    source: "azure_insights",
    visibleWhen: ({ canTakeAlertActions }) => canTakeAlertActions,
  },
  {
    id: "live-logs-otel",
    label: "OTEL",
    group: "live logs",
    source: "opentelemetry",
    visibleWhen: ({ canTakeAlertActions }) => canTakeAlertActions,
  },
  {
    id: "detection-rules",
    label: "Detection Rules",
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
];

export const isSectionVisible = (sectionId, roleFlags) => {
  const section = sectionsConfig.find((entry) => entry.id === sectionId);
  return section ? section.visibleWhen(roleFlags) : false;
};
