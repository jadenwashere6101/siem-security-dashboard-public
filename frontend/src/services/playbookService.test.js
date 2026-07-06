import {
  createPlaybookDefinition,
  updatePlaybookDefinition,
  setPlaybookDefinitionEnabled,
} from "./playbookService";

// Mock fetch
global.fetch = jest.fn();

beforeEach(() => {
  jest.clearAllMocks();
});

describe("createPlaybookDefinition", () => {
  test("sends POST request to /playbooks", async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: jest.fn().mockResolvedValueOnce({ id: "new_pb", name: "Test" }),
    });

    const payload = {
      id: "new_pb",
      name: "Test",
      enabled: false,
      trigger_config: {},
      steps: [],
    };

    await createPlaybookDefinition(payload);

    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining("/playbooks"),
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
      })
    );
  });

  test("sends expected JSON body", async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: jest.fn().mockResolvedValueOnce({ id: "new_pb" }),
    });

    const payload = {
      id: "new_pb",
      name: "Test playbook",
      enabled: true,
      trigger_config: { alert_type: "x" },
      steps: [{ action: "monitor" }],
    };

    await createPlaybookDefinition(payload);

    const call = global.fetch.mock.calls[0];
    const body = call[1].body;
    expect(body).toEqual(JSON.stringify(payload));
  });

  test("throws error on non-OK response", async () => {
    global.fetch.mockResolvedValueOnce({
      ok: false,
      json: jest.fn().mockResolvedValueOnce({ error: "Invalid ID" }),
    });

    await expect(
      createPlaybookDefinition({ id: "pb", name: "Test" })
    ).rejects.toThrow();
  });
});

describe("updatePlaybookDefinition", () => {
  test("sends PUT request to /playbooks/<id>", async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: jest.fn().mockResolvedValueOnce({ id: "pb_one" }),
    });

    const payload = { name: "Updated" };
    await updatePlaybookDefinition("pb_one", payload);

    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining("/playbooks/pb_one"),
      expect.objectContaining({
        method: "PUT",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
      })
    );
  });

  test("URL-encodes the ID", async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: jest.fn().mockResolvedValueOnce({ id: "pb-one" }),
    });

    await updatePlaybookDefinition("pb-one", { name: "Test" });

    const url = global.fetch.mock.calls[0][0];
    expect(url).toContain("pb-one");
  });

  test("sends expected JSON body", async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: jest.fn().mockResolvedValueOnce({ id: "pb_one" }),
    });

    const payload = {
      name: "Updated Name",
      enabled: false,
      trigger_config: { min_severity: "HIGH" },
      steps: [],
    };

    await updatePlaybookDefinition("pb_one", payload);

    const call = global.fetch.mock.calls[0];
    const body = call[1].body;
    expect(body).toEqual(JSON.stringify(payload));
  });

  test("throws error on non-OK response", async () => {
    global.fetch.mockResolvedValueOnce({
      ok: false,
      json: jest.fn().mockResolvedValueOnce({ error: "Not found" }),
    });

    await expect(
      updatePlaybookDefinition("pb_one", { name: "Test" })
    ).rejects.toThrow();
  });
});

describe("setPlaybookDefinitionEnabled", () => {
  test("sends PATCH request to /playbooks/<id>/enabled", async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: jest.fn().mockResolvedValueOnce({ id: "pb_one", enabled: true }),
    });

    await setPlaybookDefinitionEnabled("pb_one", true);

    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining("/playbooks/pb_one/enabled"),
      expect.objectContaining({
        method: "PATCH",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
      })
    );
  });

  test("sends { enabled: true } payload", async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: jest.fn().mockResolvedValueOnce({ id: "pb_one", enabled: true }),
    });

    await setPlaybookDefinitionEnabled("pb_one", true);

    const call = global.fetch.mock.calls[0];
    const body = call[1].body;
    expect(body).toEqual(JSON.stringify({ enabled: true }));
  });

  test("sends { enabled: false } payload", async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: jest.fn().mockResolvedValueOnce({ id: "pb_one", enabled: false }),
    });

    await setPlaybookDefinitionEnabled("pb_one", false);

    const call = global.fetch.mock.calls[0];
    const body = call[1].body;
    expect(body).toEqual(JSON.stringify({ enabled: false }));
  });

  test("throws error on non-OK response", async () => {
    global.fetch.mockResolvedValueOnce({
      ok: false,
      json: jest.fn().mockResolvedValueOnce({ error: "Not found" }),
    });

    await expect(
      setPlaybookDefinitionEnabled("pb_one", true)
    ).rejects.toThrow();
  });
});
