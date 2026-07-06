import { isSectionVisible, sectionsConfig } from "./sectionsConfig";

const EXPECTED_SECTION_IDS = [
  "dashboard",
  "soc-command-center",
  "blocklist",
  "threat-hunt",
  "administration",
  "soar-queue",
  "soar-incidents",
  "soar-approvals",
  "soar-playbooks",
  "soar-playbook-metrics",
  "soar-integrations",
  "soar-operations",
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
  administration: {
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
};

describe("sectionsConfig", () => {
  test("contains exactly the 12 existing section ids", () => {
    expect(sectionsConfig).toHaveLength(12);
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
});
