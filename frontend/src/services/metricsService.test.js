import { getPlaybookMetrics, getNotificationDeliveryMetrics } from "./metricsService";

describe("getPlaybookMetrics", () => {
  beforeEach(() => {
    global.fetch = jest.fn();
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  test("calls GET /metrics/playbooks", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          total_executions: 0,
          by_status: {
            pending: 0,
            running: 0,
            awaiting_approval: 0,
            success: 0,
            failed: 0,
            abandoned: 0,
          },
          by_playbook_id: [],
          recent: { window_hours: 24, success: 0, failed: 0 },
          approval_gated: { awaiting_approval: 0, with_linked_approval: 0 },
        }),
    });

    await getPlaybookMetrics();

    expect(global.fetch).toHaveBeenCalledTimes(1);
    const [url, options] = global.fetch.mock.calls[0];
    expect(url).toEqual(expect.stringContaining("/metrics/playbooks"));
    expect(options.credentials).toBe("include");
    expect(options.method).toBeUndefined();
  });

  test("returns parsed JSON on success", async () => {
    const payload = {
      total_executions: 5,
      by_status: {
        pending: 1,
        running: 0,
        awaiting_approval: 1,
        success: 2,
        failed: 1,
        abandoned: 0,
      },
      by_playbook_id: [{ playbook_id: "pb_a", total: 3, by_status: {} }],
      recent: { window_hours: 24, success: 2, failed: 1 },
      approval_gated: { awaiting_approval: 1, with_linked_approval: 2 },
    };
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(payload),
    });

    const result = await getPlaybookMetrics();

    expect(result).toEqual(payload);
  });

  test("throws on non-OK response", async () => {
    global.fetch.mockResolvedValue({
      ok: false,
      json: () => Promise.resolve({ error: "Forbidden" }),
    });

    await expect(getPlaybookMetrics()).rejects.toThrow("Forbidden");
  });
});

describe("getNotificationDeliveryMetrics", () => {
  beforeEach(() => {
    global.fetch = jest.fn();
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  test("calls GET /metrics/notifications", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          total_delivery_attempts: 0,
          by_provider: {},
          by_mode: { simulation: 0, real: 0 },
          by_status: { pending: 0, success: 0, failed: 0, timeout: 0, blocked: 0 },
          by_adapter_name: {},
          recent: {
            window_hours: 24,
            success: 0,
            failed: 0,
            timeout: 0,
            blocked: 0,
            time_basis: "",
          },
          circuit_breaker_state_counts: {
            closed: 0,
            open: 0,
            half_open: 0,
            unknown: 0,
            invalid: 0,
          },
        }),
    });

    await getNotificationDeliveryMetrics();

    expect(global.fetch).toHaveBeenCalledTimes(1);
    const [url, options] = global.fetch.mock.calls[0];
    expect(url).toContain("/metrics/notifications");
    expect(options.credentials).toBe("include");
  });

  test("returns parsed JSON on success", async () => {
    const payload = {
      total_delivery_attempts: 5,
      by_provider: { slack: 3, teams: 2 },
      by_mode: { simulation: 4, real: 1 },
      by_status: { pending: 1, success: 1, failed: 1, timeout: 1, blocked: 1 },
      by_adapter_name: { slack: 3, teams: 2 },
      recent: {
        window_hours: 24,
        success: 1,
        failed: 1,
        timeout: 1,
        blocked: 1,
        time_basis: "UTC window",
      },
      circuit_breaker_state_counts: {
        closed: 1,
        open: 2,
        half_open: 1,
        unknown: 0,
        invalid: 0,
      },
    };
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(payload),
    });

    const result = await getNotificationDeliveryMetrics();

    expect(result).toEqual(payload);
  });

  test("throws on non-OK response", async () => {
    global.fetch.mockResolvedValue({
      ok: false,
      json: () => Promise.resolve({ error: "Forbidden" }),
    });

    await expect(getNotificationDeliveryMetrics()).rejects.toThrow();
  });
});
