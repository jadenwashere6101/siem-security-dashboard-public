import {
  listApprovalNotificationDeliveries,
  listIncidentNotificationDeliveries,
  listNotificationDeliveries,
} from "./notificationDeliveryService";

describe("listNotificationDeliveries", () => {
  beforeEach(() => {
    global.fetch = jest.fn();
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  test("calls GET /notification-deliveries with no query when filters empty", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ items: [], limit: 100, offset: 0 }),
    });

    await listNotificationDeliveries();

    expect(global.fetch).toHaveBeenCalledTimes(1);
    const [url, options] = global.fetch.mock.calls[0];
    expect(url).toContain("/notification-deliveries");
    expect(options.credentials).toBe("include");
  });

  test("builds query string from filters", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ items: [], limit: 50, offset: 0 }),
    });

    await listNotificationDeliveries({
      playbook_execution_id: 42,
      provider: "slack",
      mode: "simulation",
      status: "success",
      correlation_id: "corr-1",
      incident_id: 9,
      approval_request_id: 3,
      adapter_name: "slack",
      limit: 25,
      offset: 5,
    });

    const [url] = global.fetch.mock.calls[0];
    expect(url).toContain("playbook_execution_id=42");
    expect(url).toContain("provider=slack");
    expect(url).toContain("mode=simulation");
    expect(url).toContain("status=success");
    expect(url).toContain("correlation_id=corr-1");
    expect(url).toContain("incident_id=9");
    expect(url).toContain("approval_request_id=3");
    expect(url).toContain("adapter_name=slack");
    expect(url).toContain("limit=25");
    expect(url).toContain("offset=5");
  });

  test("returns parsed JSON on success", async () => {
    const payload = {
      items: [{ id: 1, provider: "slack", mode: "simulation" }],
      limit: 50,
      offset: 0,
    };
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(payload),
    });

    const result = await listNotificationDeliveries({ playbook_execution_id: 1 });

    expect(result).toEqual(payload);
  });

  test("throws on non-OK response", async () => {
    global.fetch.mockResolvedValue({
      ok: false,
      json: () => Promise.resolve({ error: "forbidden", message: "No access" }),
    });

    await expect(listNotificationDeliveries()).rejects.toThrow();
  });

  test("lists notification deliveries for an incident through the existing endpoint", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ items: [], limit: 25, offset: 0 }),
    });

    await listIncidentNotificationDeliveries(7, { limit: 25 });

    const [url] = global.fetch.mock.calls[0];
    expect(url).toContain("/notification-deliveries");
    expect(url).toContain("incident_id=7");
    expect(url).toContain("limit=25");
  });

  test("lists notification deliveries for an approval through the existing endpoint", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ items: [], limit: 25, offset: 0 }),
    });

    await listApprovalNotificationDeliveries(11, { limit: 25 });

    const [url] = global.fetch.mock.calls[0];
    expect(url).toContain("/notification-deliveries");
    expect(url).toContain("approval_request_id=11");
    expect(url).toContain("limit=25");
  });
});
