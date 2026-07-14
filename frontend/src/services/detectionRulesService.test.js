import {
  loadDetectionRules,
  loadPfsenseDetectionHealth,
  updateDetectionRule,
} from "./detectionRulesService";

beforeEach(() => {
  global.fetch = jest.fn();
});

afterEach(() => {
  jest.restoreAllMocks();
});

test("loads detection rules with credentials", async () => {
  const rules = [{ rule_id: "failed_login_threshold" }];
  fetch.mockResolvedValue({ ok: true, json: async () => rules });

  await expect(loadDetectionRules()).resolves.toEqual(rules);
  expect(fetch).toHaveBeenCalledWith("/admin/detection-rules", {
    credentials: "include",
  });
});

test("loads pfSense detection health with credentials", async () => {
  const rows = [{ rule_id: "pfsense_firewall_port_scan" }];
  fetch.mockResolvedValue({ ok: true, json: async () => rows });

  await expect(loadPfsenseDetectionHealth()).resolves.toEqual(rows);
  expect(fetch).toHaveBeenCalledWith("/admin/detection-rules/pfsense-health", {
    credentials: "include",
  });
});

test("loads pfSense detection health with operational scope when requested", async () => {
  const rows = [{ rule_id: "pfsense_firewall_port_scan" }];
  fetch.mockResolvedValue({ ok: true, json: async () => rows });

  await expect(loadPfsenseDetectionHealth({ operationalScope: "since_tuning" })).resolves.toEqual(rows);
  expect(fetch).toHaveBeenCalledWith("/admin/detection-rules/pfsense-health?operational_scope=since_tuning", {
    credentials: "include",
  });
});

test("sends parameter-only updates with the legacy-compatible payload", async () => {
  fetch.mockResolvedValue({ ok: true, json: async () => ({}) });

  await updateDetectionRule("failed_login_threshold", { threshold: 4, window_minutes: 15 });

  expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({
    parameters: { threshold: 4, window_minutes: 15 },
  });
});

test("sends active-only updates without resetting parameters", async () => {
  fetch.mockResolvedValue({ ok: true, json: async () => ({ active: false }) });

  await updateDetectionRule("failed_login_threshold", undefined, false);

  expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ active: false });
});

test("surfaces API update errors", async () => {
  fetch.mockResolvedValue({ ok: false, json: async () => ({ error: "Update rejected" }) });
  await expect(updateDetectionRule("failed_login_threshold", undefined, false)).rejects.toThrow(
    "Update rejected"
  );
});
