import { getPlaybookMetrics } from "./metricsService";

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
