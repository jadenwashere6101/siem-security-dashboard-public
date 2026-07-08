import { isSectionVisible, sectionsConfig } from "./sectionsConfig";

const EXPECTED_SECTION_IDS = [
  "dashboard",
  "soc-command-center",
  "blocklist",
  "threat-hunt",
  "live-logs-honeypot",
  "live-logs-bank-app",
  "live-logs-pfsense",
  "live-logs-nginx",
  "live-logs-azure",
  "live-logs-otel",
  "detection-rules",
  "admin-users",
  "admin-audit-logs",
  "soar-queue",
  "soar-incidents",
  "soar-approvals",
  "soar-playbooks",
  "soar-playbook-metrics",
  "soar-integrations",
  "soar-operations",
  "settings",
];

const roleFlagSets = {
  super_admin: {
    isSuperAdmin: true,
    isAnalyst: false,
    canTakeAlertActions: true,
  },
  analyst: {
    isSuperAdmin: false,
    isAnalyst: true,
    canTakeAlertActions: true,
  },
  viewer: {
    isSuperAdmin: false,
    isAnalyst: false,
    canTakeAlertActions: false,
  },
  unauthenticated: {
    isSuperAdmin: false,
    isAnalyst: false,
    canTakeAlertActions: false,
  },
};

const expectedVisibility = {
  dashboard: {
    super_admin: true,
    analyst: true,
    viewer: true,
    unauthenticated: true,
  },
  "soc-command-center": {
    super_admin: true,
    analyst: true,
    viewer: false,
    unauthenticated: false,
  },
  blocklist: {
    super_admin: true,
    analyst: true,
    viewer: false,
    unauthenticated: false,
  },
  "threat-hunt": {
    super_admin: true,
    analyst: true,
    viewer: false,
    unauthenticated: false,
  },
  "live-logs-honeypot": {
    super_admin: true,
    analyst: true,
    viewer: false,
    unauthenticated: false,
  },
  "live-logs-bank-app": {
    super_admin: true,
    analyst: true,
    viewer: false,
    unauthenticated: false,
  },
  "live-logs-pfsense": {
    super_admin: true,
    analyst: true,
    viewer: false,
    unauthenticated: false,
  },
  "live-logs-nginx": {
    super_admin: true,
    analyst: true,
    viewer: false,
    unauthenticated: false,
  },
  "live-logs-azure": {
    super_admin: true,
    analyst: true,
    viewer: false,
    unauthenticated: false,
  },
  "live-logs-otel": {
    super_admin: true,
    analyst: true,
    viewer: false,
    unauthenticated: false,
  },
  "detection-rules": {
    super_admin: true,
    analyst: false,
    viewer: false,
    unauthenticated: false,
  },
  "admin-users": {
    super_admin: true,
    analyst: false,
    viewer: false,
    unauthenticated: false,
  },
  "admin-audit-logs": {
    super_admin: true,
    analyst: false,
    viewer: false,
    unauthenticated: false,
  },
  "soar-queue": {
    super_admin: true,
    analyst: false,
    viewer: false,
    unauthenticated: false,
  },
  "soar-incidents": {
    super_admin: true,
    analyst: true,
    viewer: false,
    unauthenticated: false,
  },
  "soar-approvals": {
    super_admin: true,
    analyst: true,
    viewer: false,
    unauthenticated: false,
  },
  "soar-playbooks": {
    super_admin: true,
    analyst: true,
    viewer: false,
    unauthenticated: false,
  },
  "soar-playbook-metrics": {
    super_admin: true,
    analyst: true,
    viewer: false,
    unauthenticated: false,
  },
  "soar-integrations": {
    super_admin: true,
    analyst: true,
    viewer: false,
    unauthenticated: false,
  },
  "soar-operations": {
    super_admin: true,
    analyst: true,
    viewer: false,
    unauthenticated: false,
  },
  settings: {
    super_admin: true,
    analyst: true,
    viewer: true,
    unauthenticated: true,
  },
};

describe("sectionsConfig", () => {
  test("contains exactly the expected section ids", () => {
    expect(sectionsConfig).toHaveLength(21);
    expect(sectionsConfig.map((section) => section.id)).toEqual(EXPECTED_SECTION_IDS);
  });

  test("each entry defines id, label, group, and visibleWhen", () => {
    sectionsConfig.forEach((section) => {
      expect(section).toEqual(
        expect.objectContaining({
          id: expect.any(String),
          label: expect.any(String),
          group: expect.any(String),
          visibleWhen: expect.any(Function),
        })
      );
    });
  });

  test("visibleWhen matches original role gating for all sections and roles", () => {
    EXPECTED_SECTION_IDS.forEach((sectionId) => {
      Object.entries(roleFlagSets).forEach(([roleName, roleFlags]) => {
        expect(isSectionVisible(sectionId, roleFlags)).toBe(
          expectedVisibility[sectionId][roleName]
        );
      });
    });
  });

  test("live logs entries map labels to raw event source values", () => {
    const liveLogEntries = sectionsConfig.filter((section) => section.group === "live logs");

    expect(liveLogEntries).toEqual([
      expect.objectContaining({ id: "live-logs-honeypot", label: "Honeypot", source: "honeypot" }),
      expect.objectContaining({ id: "live-logs-bank-app", label: "Bank App", source: "bank_app" }),
      expect.objectContaining({ id: "live-logs-pfsense", label: "pfSense", source: "pfsense" }),
      expect.objectContaining({ id: "live-logs-nginx", label: "NGINX", source: "nginx" }),
      expect.objectContaining({ id: "live-logs-azure", label: "Azure", source: "azure_insights" }),
      expect.objectContaining({ id: "live-logs-otel", label: "OTEL", source: "opentelemetry" }),
    ]);
  });
});
