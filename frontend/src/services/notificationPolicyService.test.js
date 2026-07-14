import {
  loadNotificationPolicy,
  testNotificationPolicyRoute,
  updateNotificationPolicy,
} from "./notificationPolicyService";

beforeEach(() => {
  global.fetch = jest.fn();
});

test("loads notification policy with credentials", async () => {
  fetch.mockResolvedValue({ ok: true, json: async () => ({ slack_enabled: false }) });
  await loadNotificationPolicy();
  expect(fetch).toHaveBeenCalledWith(
    "/admin/notification-policy",
    expect.objectContaining({ credentials: "include" })
  );
});

test("patches notification policy with typed fields", async () => {
  fetch.mockResolvedValue({ ok: true, json: async () => ({ slack_enabled: true }) });
  const payload = {
    slack_enabled: true,
    minimum_severity: "critical",
    notify_on_alerts: false,
    notify_on_incidents: true,
    slack_format: "detailed",
    pfsense_destination: "#soc-pfsense",
    honeypot_destination: "#soc-honeypot",
  };
  await updateNotificationPolicy(payload);
  expect(fetch).toHaveBeenCalledWith(
    "/admin/notification-policy",
    expect.objectContaining({
      method: "PATCH",
      body: JSON.stringify(payload),
    })
  );
});

test("surfaces safe backend validation errors", async () => {
  fetch.mockResolvedValue({ ok: false, json: async () => ({ error: "routing label required" }) });
  await expect(updateNotificationPolicy({ pfsense_destination: "" })).rejects.toThrow(
    "routing label required"
  );
});

test("posts notification policy route tests", async () => {
  fetch.mockResolvedValue({ ok: true, json: async () => ({ success: true }) });
  await testNotificationPolicyRoute("pfsense");
  expect(fetch).toHaveBeenCalledWith(
    "/admin/notification-policy/test/pfsense",
    expect.objectContaining({ method: "POST", credentials: "include" })
  );
});
