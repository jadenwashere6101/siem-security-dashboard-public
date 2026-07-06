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
    id: "administration",
    label: "Administration",
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
