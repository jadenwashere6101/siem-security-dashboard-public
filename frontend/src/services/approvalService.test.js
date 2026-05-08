import {
  getApproval,
  listApprovals,
  submitApprovalDecision,
} from "./approvalService";

describe("approvalService", () => {
  beforeEach(() => {
    global.fetch = jest.fn();
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  test("listApprovals fetches approvals without default query params", async () => {
    const payload = { approvals: [], count: 0 };
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(payload),
    });

    const result = await listApprovals();
    const [url, options] = global.fetch.mock.calls[0];

    expect(url).toBe("/approvals");
    expect(options.credentials).toBe("include");
    expect(result).toBe(payload);
  });

  test("listApprovals includes supported filters", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ approvals: [], count: 0 }),
    });

    await listApprovals({
      status: "pending",
      incidentId: 10,
      queueId: 20,
      limit: 25,
      offset: 5,
    });
    const url = global.fetch.mock.calls[0][0];

    expect(url).toContain("status=pending");
    expect(url).toContain("incident_id=10");
    expect(url).toContain("queue_id=20");
    expect(url).toContain("limit=25");
    expect(url).toContain("offset=5");
  });

  test("listApprovals omits all status filter", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ approvals: [], count: 0 }),
    });

    await listApprovals({ status: "all" });

    expect(global.fetch.mock.calls[0][0]).not.toContain("status=");
  });

  test("listApprovals surfaces backend errors", async () => {
    global.fetch.mockResolvedValue({
      ok: false,
      json: () => Promise.resolve({ error: "approval list unavailable" }),
    });

    await expect(listApprovals()).rejects.toThrow("approval list unavailable");
  });

  test("getApproval fetches approval detail", async () => {
    const payload = { approval: { id: 42, status: "pending" } };
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(payload),
    });

    const result = await getApproval(42);
    const [url, options] = global.fetch.mock.calls[0];

    expect(url).toBe("/approvals/42");
    expect(options.credentials).toBe("include");
    expect(result).toBe(payload);
  });

  test("getApproval surfaces backend errors", async () => {
    global.fetch.mockResolvedValue({
      ok: false,
      json: () => Promise.resolve({ error: "approval not found" }),
    });

    await expect(getApproval(999)).rejects.toThrow("approval not found");
  });

  test("submitApprovalDecision posts approve decision with optional reason", async () => {
    const payload = { approval: { id: 42, status: "approved" } };
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(payload),
    });

    const result = await submitApprovalDecision(42, {
      decision: "approved",
      reason: " approved for containment ",
    });
    const [url, options] = global.fetch.mock.calls[0];

    expect(url).toBe("/approvals/42/decision");
    expect(options.method).toBe("POST");
    expect(options.credentials).toBe("include");
    expect(options.headers).toEqual({ "Content-Type": "application/json" });
    expect(JSON.parse(options.body)).toEqual({
      decision: "approved",
      reason: "approved for containment",
    });
    expect(result).toBe(payload);
  });

  test("submitApprovalDecision posts deny decision with empty reason safely", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ approval: { id: 42, status: "denied" } }),
    });

    await submitApprovalDecision(42, { decision: "denied" });

    expect(JSON.parse(global.fetch.mock.calls[0][1].body)).toEqual({
      decision: "denied",
      reason: "",
    });
  });

  test("submitApprovalDecision surfaces invalid transition errors", async () => {
    global.fetch.mockResolvedValue({
      ok: false,
      json: () => Promise.resolve({ error: "approval request is not pending" }),
    });

    await expect(
      submitApprovalDecision(42, { decision: "approved", reason: "" })
    ).rejects.toThrow("approval request is not pending");
  });
});
