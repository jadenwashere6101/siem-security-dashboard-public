import {
  enableHalfOpenIntegrationCircuitBreaker,
  forceOpenIntegrationCircuitBreaker,
  getIntegrationStatus,
  resetIntegrationCircuitBreaker,
} from "./integrationService";

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

describe("resetIntegrationCircuitBreaker", () => {
  beforeEach(() => {
    global.fetch = jest.fn();
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  test("POST /integrations/:name/circuit-breaker/reset with reason", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          adapter: "slack",
          circuit_breaker: { state: "closed" },
        }),
    });

    await resetIntegrationCircuitBreaker("slack", "cleared after review");

    expect(global.fetch).toHaveBeenCalledTimes(1);
    const [url, options] = global.fetch.mock.calls[0];
    expect(url).toEqual(expect.stringContaining("/integrations/slack/circuit-breaker/reset"));
    expect(options.method).toBe("POST");
    expect(options.credentials).toBe("include");
    expect(options.headers["Content-Type"]).toBe("application/json");
    expect(JSON.parse(options.body)).toEqual({ reason: "cleared after review" });
  });

  test("throws using API message on failure", async () => {
    global.fetch.mockResolvedValue({
      ok: false,
      json: () => Promise.resolve({ error: "control_rejected", message: "Cooldown active" }),
    });

    await expect(resetIntegrationCircuitBreaker("email", "x")).rejects.toThrow("Cooldown active");
  });
});

describe("forceOpenIntegrationCircuitBreaker", () => {
  beforeEach(() => {
    global.fetch = jest.fn();
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  test("POST force-open", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ adapter: "webhook", circuit_breaker: { state: "open" } }),
    });

    await forceOpenIntegrationCircuitBreaker("webhook", "containment");

    const [url, options] = global.fetch.mock.calls[0];
    expect(url).toEqual(expect.stringContaining("/integrations/webhook/circuit-breaker/force-open"));
    expect(JSON.parse(options.body)).toEqual({ reason: "containment" });
  });
});

describe("enableHalfOpenIntegrationCircuitBreaker", () => {
  beforeEach(() => {
    global.fetch = jest.fn();
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  test("POST enable-half-open with override_cooldown false by default", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ adapter: "slack", circuit_breaker: { state: "half_open" } }),
    });

    await enableHalfOpenIntegrationCircuitBreaker("slack", "prep probe");

    const [, options] = global.fetch.mock.calls[0];
    expect(JSON.parse(options.body)).toEqual({
      reason: "prep probe",
      override_cooldown: false,
    });
  });

  test("POST enable-half-open passes override_cooldown true", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ adapter: "slack", circuit_breaker: { state: "half_open" } }),
    });

    await enableHalfOpenIntegrationCircuitBreaker("slack", "override", true);

    const [, options] = global.fetch.mock.calls[0];
    expect(JSON.parse(options.body)).toEqual({
      reason: "override",
      override_cooldown: true,
    });
  });
});
