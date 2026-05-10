import { getIntegrationStatus } from "./integrationService";

describe("getIntegrationStatus", () => {
  beforeEach(() => {
    global.fetch = jest.fn();
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  test("calls GET /integrations/status", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          mode: "simulation",
          simulated: true,
          real_mode_enabled: false,
          real_mode_status: "disabled",
          adapters: [],
        }),
    });

    await getIntegrationStatus();

    expect(global.fetch).toHaveBeenCalledTimes(1);
    const [url, options] = global.fetch.mock.calls[0];
    expect(url).toEqual(expect.stringContaining("/integrations/status"));
    expect(options.credentials).toBe("include");
    expect(options.method).toBeUndefined();
  });

  test("returns parsed JSON on success", async () => {
    const payload = {
      mode: "simulation",
      simulated: true,
      real_mode_enabled: false,
      real_mode_status: "disabled",
      adapters: [{ name: "slack", supported_actions: ["send_message"] }],
    };
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(payload),
    });

    const result = await getIntegrationStatus();

    expect(result).toEqual(payload);
  });

  test("throws on non-OK response", async () => {
    global.fetch.mockResolvedValue({
      ok: false,
      json: () => Promise.resolve({ error: "Forbidden" }),
    });

    await expect(getIntegrationStatus()).rejects.toThrow("Forbidden");
  });
});
