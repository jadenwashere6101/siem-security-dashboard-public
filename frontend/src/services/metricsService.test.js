import {
  getApprovalMetrics,
  getIncidentMetrics,
  getNotificationDeliveryMetrics,
  getPlaybookMetrics,
  getPlaybookWorkerMetrics,
} from "./metricsService";

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

describe("SOAR operational metric fetchers", () => {
  beforeEach(() => {
    global.fetch = jest.fn();
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  test("getIncidentMetrics calls GET /metrics/incidents with session credentials", async () => {
    const payload = {
      total_count: 3,
      open_count: 1,
      open_high_critical_count: 1,
      by_status: { open: 1, investigating: 1, resolved: 1, closed: 0 },
      by_severity: { CRITICAL: 1, HIGH: 1, MEDIUM: 1, LOW: 0 },
      newest_incident_at: "2026-05-17T12:00:00+00:00",
      oldest_open_incident_at: "2026-05-17T10:00:00+00:00",
    };
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(payload),
    });

    const result = await getIncidentMetrics();

    expect(result).toEqual(payload);
    expect(global.fetch).toHaveBeenCalledTimes(1);
    const [url, options] = global.fetch.mock.calls[0];
    expect(url).toContain("/metrics/incidents");
    expect(options).toEqual({ credentials: "include" });
  });

  test("getApprovalMetrics calls GET /metrics/approvals with session credentials", async () => {
    const payload = {
      total_count: 4,
      pending_count: 2,
      by_status: { pending: 2, approved: 1, denied: 1, expired: 0 },
      newest_approval_at: "2026-05-17T12:00:00+00:00",
      oldest_pending_approval_at: "2026-05-17T09:00:00+00:00",
    };
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(payload),
    });

    const result = await getApprovalMetrics();

    expect(result).toEqual(payload);
    expect(global.fetch).toHaveBeenCalledTimes(1);
    const [url, options] = global.fetch.mock.calls[0];
    expect(url).toContain("/metrics/approvals");
    expect(options).toEqual({ credentials: "include" });
  });

  test("getIncidentMetrics throws backend message on non-OK response", async () => {
    global.fetch.mockResolvedValue({
      ok: false,
      status: 403,
      json: () => Promise.resolve({ error: "forbidden" }),
    });

    await expect(getIncidentMetrics()).rejects.toThrow("forbidden");
  });

  test("getIncidentMetrics includes operational scope when requested", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ total_count: 0 }),
    });

    await getIncidentMetrics({ operationalScope: "since_tuning" });

    expect(global.fetch.mock.calls[0][0]).toContain("operational_scope=since_tuning");
  });

  test("getApprovalMetrics throws fallback message on non-OK malformed JSON", async () => {
    global.fetch.mockResolvedValue({
      ok: false,
      status: 500,
      json: () => Promise.reject(new SyntaxError("bad json")),
    });

    await expect(getApprovalMetrics()).rejects.toThrow(
      "Unable to load approval metrics"
    );
  });

  test("metric fetchers return fallback value on successful malformed JSON", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.reject(new SyntaxError("bad json")),
    });

    await expect(getIncidentMetrics()).resolves.toEqual({});
  });

  test("getPlaybookWorkerMetrics calls GET /metrics/playbook-worker with session credentials", async () => {
    const payload = {
      daemon_health: { status: "unknown", worker_heartbeat_available: false },
      queue_depth: { pending: 1, running: 2, awaiting_approval: 0, active_total: 3 },
      running: { total: 2, active_leased: 1, stale: 1, missing_lease: 0 },
      stale_running_count: 1,
      recent: { failed_executions: 1, active_dead_letters: 2 },
      recovery: { total_recovery_count: 3, recovered_execution_count: 1 },
    };
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(payload),
    });

    const result = await getPlaybookWorkerMetrics();

    expect(result).toEqual(payload);
    expect(global.fetch).toHaveBeenCalledTimes(1);
    const [url, options] = global.fetch.mock.calls[0];
    expect(url).toContain("/metrics/playbook-worker");
    expect(options).toEqual({ credentials: "include" });
  });

  test("getPlaybookWorkerMetrics throws fallback message on non-OK malformed JSON", async () => {
    global.fetch.mockResolvedValue({
      ok: false,
      status: 500,
      json: () => Promise.reject(new SyntaxError("bad json")),
    });

    await expect(getPlaybookWorkerMetrics()).rejects.toThrow(
      "Unable to load playbook worker metrics"
    );
  });
});
