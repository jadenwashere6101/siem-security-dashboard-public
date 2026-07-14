import {
  loadIncidentDetail,
  loadIncidentTimeline,
  loadIncidents,
  updateIncidentStatus,
} from "./incidentService";

describe("incidentService", () => {
  beforeEach(() => {
    global.fetch = jest.fn();
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  test("loadIncidents fetches incidents with default query params", async () => {
    const payload = { incidents: [], count: 0 };
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(payload),
    });

    const result = await loadIncidents();
    const [url, options] = global.fetch.mock.calls[0];

    expect(url).toBe("/incidents");
    expect(options.credentials).toBe("include");
    expect(result).toBe(payload);
  });

  test("loadIncidents includes active status filter", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ incidents: [], count: 0 }),
    });

    await loadIncidents({ status: "open" });

    expect(global.fetch.mock.calls[0][0]).toContain("status=open");
  });

  test("loadIncidents omits all status filter", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ incidents: [], count: 0 }),
    });

    await loadIncidents({ status: "all" });

    expect(global.fetch.mock.calls[0][0]).not.toContain("status=");
  });

  test("loadIncidents includes active severity filter", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ incidents: [], count: 0 }),
    });

    await loadIncidents({ severity: "HIGH" });

    expect(global.fetch.mock.calls[0][0]).toContain("severity=HIGH");
  });

  test("loadIncidents includes both filters", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ incidents: [], count: 0 }),
    });

    await loadIncidents({ status: "open", severity: "CRITICAL" });
    const url = global.fetch.mock.calls[0][0];

    expect(url).toContain("status=open");
    expect(url).toContain("severity=CRITICAL");
  });

  test("loadIncidents includes operational scope when requested", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ incidents: [], count: 0 }),
    });

    await loadIncidents({ operationalScope: "since_tuning" });

    expect(global.fetch.mock.calls[0][0]).toContain("operational_scope=since_tuning");
  });

  test("loadIncidents surfaces backend errors", async () => {
    global.fetch.mockResolvedValue({
      ok: false,
      json: () => Promise.resolve({ error: "incident list unavailable" }),
    });

    await expect(loadIncidents()).rejects.toThrow("incident list unavailable");
  });

  test("loadIncidentDetail fetches incident detail", async () => {
    const payload = { incident: { id: 42, title: "Incident 42" } };
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(payload),
    });

    const result = await loadIncidentDetail(42);
    const [url, options] = global.fetch.mock.calls[0];

    expect(url).toBe("/incidents/42");
    expect(options.credentials).toBe("include");
    expect(result).toBe(payload);
  });

  test("loadIncidentDetail surfaces backend errors", async () => {
    global.fetch.mockResolvedValue({
      ok: false,
      json: () => Promise.resolve({ error: "incident not found" }),
    });

    await expect(loadIncidentDetail(999)).rejects.toThrow("incident not found");
  });

  test("loadIncidentTimeline fetches incident timeline", async () => {
    const payload = {
      timeline: [
        {
          timestamp: "2026-05-10T18:25:00Z",
          event_type: "playbook_step_completed",
          source: "playbook_execution",
          summary: "Simulated adapter step completed",
        },
      ],
    };
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(payload),
    });

    const result = await loadIncidentTimeline(42);
    const [url, options] = global.fetch.mock.calls[0];

    expect(url).toBe("/incidents/42/timeline");
    expect(options.credentials).toBe("include");
    expect(result).toBe(payload);
  });

  test("loadIncidentTimeline surfaces backend errors", async () => {
    global.fetch.mockResolvedValue({
      ok: false,
      json: () => Promise.resolve({ error: "timeline unavailable" }),
    });

    await expect(loadIncidentTimeline(42)).rejects.toThrow("timeline unavailable");
  });

  test("updateIncidentStatus posts status update", async () => {
    const payload = { incident: { id: 42, status: "investigating" } };
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(payload),
    });

    const result = await updateIncidentStatus(42, "investigating");
    const [url, options] = global.fetch.mock.calls[0];

    expect(url).toBe("/incidents/42/status");
    expect(options.method).toBe("POST");
    expect(options.credentials).toBe("include");
    expect(options.headers).toEqual({ "Content-Type": "application/json" });
    expect(JSON.parse(options.body)).toEqual({ status: "investigating" });
    expect(result).toBe(payload);
  });

  test("updateIncidentStatus surfaces invalid transition errors", async () => {
    global.fetch.mockResolvedValue({
      ok: false,
      json: () => Promise.resolve({ error: "invalid status transition" }),
    });

    await expect(updateIncidentStatus(42, "open")).rejects.toThrow(
      "invalid status transition"
    );
  });
});
