import { loadSoarQueueItem, runSoarWorkerOnce } from "./soarQueueService";

describe("runSoarWorkerOnce", () => {
  beforeEach(() => {
    global.fetch = jest.fn();
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  test("posts one simulation worker batch request without mode", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          mode: "simulation",
          batch_size: 10,
          summary: { processed: 0, success: 0, failed: 0, skipped: 0, requeued: 0 },
          results: [],
        }),
    });

    const result = await runSoarWorkerOnce({ batchSize: 10 });

    expect(global.fetch).toHaveBeenCalledTimes(1);
    const [url, options] = global.fetch.mock.calls[0];
    expect(url).toBe("/admin/soar/worker/run-once");
    expect(options.method).toBe("POST");
    expect(options.credentials).toBe("include");
    expect(options.headers).toEqual({ "Content-Type": "application/json" });
    expect(JSON.parse(options.body)).toEqual({ batch_size: 10 });
    expect(JSON.parse(options.body)).not.toHaveProperty("mode");
    expect(result.mode).toBe("simulation");
  });

  test("surfaces backend error messages", async () => {
    global.fetch.mockResolvedValue({
      ok: false,
      json: () => Promise.resolve({ error: "SOAR worker admin run is simulation-only" }),
    });

    await expect(runSoarWorkerOnce({ batchSize: 10 })).rejects.toThrow(
      "SOAR worker admin run is simulation-only"
    );
  });
});

describe("loadSoarQueueItem", () => {
  beforeEach(() => {
    global.fetch = jest.fn();
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  test("loads queue item detail with credentials include", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          id: 42,
          alert_id: null,
          action: "block_ip",
          status: "pending",
          idempotency_key: "abc123",
        }),
    });

    const result = await loadSoarQueueItem(42);
    const [url, options] = global.fetch.mock.calls[0];

    expect(url).toBe("/admin/soar/queue/42");
    expect(options.credentials).toBe("include");
    expect(result.id).toBe(42);
    expect(result.alert_id).toBeNull();
  });

  test("surfaces queue item detail errors", async () => {
    global.fetch.mockResolvedValue({
      ok: false,
      json: () => Promise.resolve({ error: "Queue item not found" }),
    });

    await expect(loadSoarQueueItem(999)).rejects.toThrow("Queue item not found");
  });
});
