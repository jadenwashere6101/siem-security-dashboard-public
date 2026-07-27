import { getSocBriefing, listSocBriefings } from "./socBriefingService";

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

  test("throws API error messages on failure", async () => {
    global.fetch.mockResolvedValue({
      ok: false,
      json: () => Promise.resolve({ error: "forbidden", message: "No access" }),
    });

    await expect(listSocBriefings()).rejects.toThrow("forbidden");
  });
});
