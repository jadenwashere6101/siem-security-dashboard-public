import { loadSimulatorRules, runDetectionSimulation } from "./detectionSimulatorService";

const rulesPayload = {
  rules: [
    {
      rule_id: "failed_login_threshold",
      display_name: "Failed Login Threshold",
      description: "Triggers on repeated failed logins.",
      active: true,
      applicable_sources: [{ source: "bank_app", source_type: "custom" }],
    },
  ],
};

const validSimulationResponse = {
  simulated: true,
  source: "bank_app",
  rule_id: "failed_login_threshold",
  stages: {
    raw_input: { status: "succeeded" },
    parser: { status: "succeeded" },
    normalized_event: { status: "succeeded" },
    detection_applicability: { status: "succeeded" },
    detection_evaluation: { status: "succeeded" },
    threshold_window_evaluation: { status: "succeeded" },
    alert_preview: { status: "succeeded" },
    mitre_mapping: { status: "succeeded" },
    soar_preview: { status: "succeeded" },
  },
};

beforeEach(() => {
  global.fetch = jest.fn();
});

describe("loadSimulatorRules", () => {
  test("loads the existing-rules list", async () => {
    fetch.mockResolvedValue({ ok: true, json: async () => rulesPayload });
    await expect(loadSimulatorRules()).resolves.toEqual(rulesPayload.rules);
    expect(fetch).toHaveBeenCalledWith("/detection-simulator/rules", { credentials: "include" });
  });

  test("rejects a malformed rules response", async () => {
    fetch.mockResolvedValue({ ok: true, json: async () => ({ rules: "not-an-array" }) });
    await expect(loadSimulatorRules()).rejects.toThrow("Invalid detection rules response");
  });

  test("surfaces the backend error message on failure", async () => {
    fetch.mockResolvedValue({ ok: false, json: async () => ({ error: "forbidden" }) });
    await expect(loadSimulatorRules()).rejects.toThrow("forbidden");
  });
});

describe("runDetectionSimulation", () => {
  test("posts exactly the given payload and returns the validated response", async () => {
    fetch.mockResolvedValue({ ok: true, json: async () => validSimulationResponse });

    const payload = {
      source: "bank_app",
      rule_id: "failed_login_threshold",
      input_format: "json",
      json_events: [{ event_type: "failed_login" }],
    };
    await expect(runDetectionSimulation(payload)).resolves.toEqual(validSimulationResponse);

    expect(fetch).toHaveBeenCalledWith("/detection-simulator/run", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  });

  test("rejects a response missing required stages", async () => {
    const incomplete = { ...validSimulationResponse, stages: { parser: { status: "succeeded" } } };
    fetch.mockResolvedValue({ ok: true, json: async () => incomplete });
    await expect(runDetectionSimulation({})).rejects.toThrow("Invalid simulation response");
  });

  test("rejects a response missing the simulated flag", async () => {
    const { simulated, ...rest } = validSimulationResponse;
    fetch.mockResolvedValue({ ok: true, json: async () => rest });
    await expect(runDetectionSimulation({})).rejects.toThrow("Invalid simulation response");
  });

  test("surfaces the backend error message on failure", async () => {
    fetch.mockResolvedValue({ ok: false, json: async () => ({ error: "Unknown rule_id" }) });
    await expect(runDetectionSimulation({})).rejects.toThrow("Unknown rule_id");
  });

  test("attaches backend validation details on Sigma subset failures", async () => {
    fetch.mockResolvedValue({
      ok: false,
      json: async () => ({
        error: "Unsupported Sigma modifier 're' on field 'UserName'",
        validation: {
          class: "unsupported_modifier",
          element: "UserName|re",
          reason: "modifier 're' is not approved",
        },
      }),
    });
    await expect(runDetectionSimulation({})).rejects.toMatchObject({
      message: "Unsupported Sigma modifier 're' on field 'UserName'",
      validation: {
        class: "unsupported_modifier",
        element: "UserName|re",
      },
    });
  });
});
