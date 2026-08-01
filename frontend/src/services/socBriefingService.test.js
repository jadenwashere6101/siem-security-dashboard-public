import {
  getSocBriefing,
  getSocBriefingControl,
  getManualSocBriefingRunStatus,
  listSocBriefings,
  runSocBriefingNow,
  updateSocBriefingMode,
  updateSocBriefingPause,
} from "./socBriefingService";

describe("socBriefingService", () => {
  beforeEach(() => {
    global.fetch = jest.fn();
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  test("lists SOC briefings with bounded filters", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ items: [], limit: 10, offset: 0, total: 0 }),
    });

    await listSocBriefings({
      search: "auth",
      content_status: "ready",
      delivery_status: "sent",
      provider_status: "local",
      limit: 10,
      offset: 20,
    });

    const [url, options] = global.fetch.mock.calls[0];
    expect(url).toContain("/soc-briefings");
    expect(url).toContain("search=auth");
    expect(url).toContain("content_status=ready");
    expect(url).toContain("delivery_status=sent");
    expect(url).toContain("provider_status=local");
    expect(url).toContain("limit=10");
    expect(url).toContain("offset=20");
    expect(options.credentials).toBe("include");
  });

  test("loads one SOC briefing detail", async () => {
    const payload = { id: 7, sections: {}, deliveries: [] };
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(payload),
    });

    const result = await getSocBriefing(7);

    expect(result).toEqual(payload);
    expect(global.fetch.mock.calls[0][0]).toContain("/soc-briefings/7");
  });

  test("loads SOC briefing control status", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ mode: "manual_only", schedules_paused: true }),
    });

    await getSocBriefingControl();

    const [url, options] = global.fetch.mock.calls[0];
    expect(url).toContain("/soc-briefings/control");
    expect(options.credentials).toBe("include");
  });

  test("updates mode, pause state, and run-now with explicit methods", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ ok: true }),
    });

    await updateSocBriefingMode("scheduled_autonomous");
    await updateSocBriefingPause(false, "");
    await runSocBriefingNow();

    expect(global.fetch.mock.calls[0][0]).toContain("/soc-briefings/control/mode");
    expect(global.fetch.mock.calls[0][1]).toEqual(
      expect.objectContaining({
        method: "PUT",
        credentials: "include",
        body: JSON.stringify({ mode: "scheduled_autonomous" }),
      })
    );
    expect(global.fetch.mock.calls[1][0]).toContain("/soc-briefings/control/pause");
    expect(global.fetch.mock.calls[1][1]).toEqual(
      expect.objectContaining({
        method: "PUT",
        credentials: "include",
        body: JSON.stringify({ schedules_paused: false, pause_reason: "" }),
      })
    );
    expect(global.fetch.mock.calls[2][0]).toContain("/soc-briefings/run-now");
    expect(global.fetch.mock.calls[2][1]).toEqual(expect.objectContaining({ method: "POST", credentials: "include" }));
  });

  test("loads manual run lifecycle status with optional job id", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ job: { id: 44 }, lifecycle: { status: "queued" } }),
    });

    const result = await getManualSocBriefingRunStatus(44);

    expect(result.job.id).toBe(44);
    expect(global.fetch.mock.calls[0][0]).toContain("/soc-briefings/manual-run/status?job_id=44");
    expect(global.fetch.mock.calls[0][1]).toEqual(expect.objectContaining({ credentials: "include" }));
  });

  test("throws API error messages on failure", async () => {
    global.fetch.mockResolvedValue({
      ok: false,
      json: () => Promise.resolve({ error: "forbidden", message: "No access" }),
    });

    await expect(listSocBriefings()).rejects.toThrow("forbidden");
  });
});
