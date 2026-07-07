import { loadLiveLogs } from "./liveLogsService";

describe("liveLogsService", () => {
  beforeEach(() => {
    global.fetch = jest.fn();
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  test("loads live logs with source and after_id params", async () => {
    const payload = [{ id: 2, source: "pfsense" }];
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(payload),
    });

    const result = await loadLiveLogs({ source: "pfsense", afterId: 1 });

    expect(global.fetch).toHaveBeenCalledTimes(1);
    const [url, options] = global.fetch.mock.calls[0];
    expect(url).toBe("/events/search?source=pfsense&after_id=1");
    expect(options.credentials).toBe("include");
    expect(result).toBe(payload);
  });

  test("loads source-only initial request", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve([]),
    });

    await loadLiveLogs({ source: "honeypot" });

    expect(global.fetch.mock.calls[0][0]).toBe("/events/search?source=honeypot");
  });

  test("surfaces backend error messages", async () => {
    global.fetch.mockResolvedValue({
      ok: false,
      json: () => Promise.resolve({ error: "Invalid source" }),
    });

    await expect(loadLiveLogs({ source: "bad" })).rejects.toThrow("Invalid source");
  });
});
