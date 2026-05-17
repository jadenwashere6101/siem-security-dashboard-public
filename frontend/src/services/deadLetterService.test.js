import {
  dismissDeadLetter,
  executeDeadLetterRetry,
  getDeadLetter,
  getDeadLetterMetrics,
  getDeadLetters,
  listDeadLetters,
  requestDeadLetterRetry,
  retryExecuteDeadLetter,
  retryRequestDeadLetter,
} from "./deadLetterService";

describe("deadLetterService", () => {
  beforeEach(() => {
    global.fetch = jest.fn();
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  test("getDeadLetters loads list with credentials and no query by default", async () => {
    const payload = { items: [], limit: 100, offset: 0 };
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(payload),
    });

    const result = await getDeadLetters();
    const [url, options] = global.fetch.mock.calls[0];

    expect(url).toBe("/dead-letters");
    expect(options.credentials).toBe("include");
    expect(result).toBe(payload);
  });

  test("listDeadLetters serializes supported filters", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ items: [], limit: 25, offset: 5 }),
    });

    await listDeadLetters({
      status: "open",
      source_type: "playbook_execution",
      failure_class: "adapter_failed",
      retryable: true,
      incident_id: 10,
      alert_id: 20,
      execution_id: 30,
      limit: 25,
      offset: 5,
      ignored: "value",
    });

    const [url] = global.fetch.mock.calls[0];
    expect(url).toContain("/dead-letters?");
    expect(url).toContain("status=open");
    expect(url).toContain("source_type=playbook_execution");
    expect(url).toContain("failure_class=adapter_failed");
    expect(url).toContain("retryable=true");
    expect(url).toContain("incident_id=10");
    expect(url).toContain("alert_id=20");
    expect(url).toContain("execution_id=30");
    expect(url).toContain("limit=25");
    expect(url).toContain("offset=5");
    expect(url).not.toContain("ignored=");
  });

  test("getDeadLetter loads detail with credentials", async () => {
    const payload = { id: 42, status: "open" };
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(payload),
    });

    const result = await getDeadLetter(42);
    const [url, options] = global.fetch.mock.calls[0];

    expect(url).toBe("/dead-letters/42");
    expect(options.credentials).toBe("include");
    expect(result).toBe(payload);
  });

  test("getDeadLetterMetrics loads metrics with credentials", async () => {
    const payload = { total: 2, by_status: { open: 1, retrying: 1 } };
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(payload),
    });

    const result = await getDeadLetterMetrics();
    const [url, options] = global.fetch.mock.calls[0];

    expect(url).toBe("/metrics/dead-letters");
    expect(options.credentials).toBe("include");
    expect(result).toBe(payload);
  });

  test("dismissDeadLetter posts optional body as JSON with credentials", async () => {
    const payload = { id: 42, status: "dismissed" };
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(payload),
    });

    const result = await dismissDeadLetter(42, { comment: "reviewed" });
    const [url, options] = global.fetch.mock.calls[0];

    expect(url).toBe("/dead-letters/42/dismiss");
    expect(options.method).toBe("POST");
    expect(options.credentials).toBe("include");
    expect(options.headers).toEqual({ "Content-Type": "application/json" });
    expect(JSON.parse(options.body)).toEqual({ comment: "reviewed" });
    expect(result).toBe(payload);
  });

  test("dismissDeadLetter posts empty object when body is omitted", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ id: 42, status: "dismissed" }),
    });

    await dismissDeadLetter(42);

    expect(JSON.parse(global.fetch.mock.calls[0][1].body)).toEqual({});
  });

  test("requestDeadLetterRetry posts retry-request with credentials", async () => {
    const payload = { id: 42, status: "retrying" };
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(payload),
    });

    const result = await requestDeadLetterRetry(42);
    const [url, options] = global.fetch.mock.calls[0];

    expect(url).toBe("/dead-letters/42/retry-request");
    expect(options.method).toBe("POST");
    expect(options.credentials).toBe("include");
    expect(options.body).toBeUndefined();
    expect(result).toBe(payload);
  });

  test("executeDeadLetterRetry posts retry-execute with credentials", async () => {
    const payload = {
      dead_letter: { id: 42, status: "retried" },
      new_execution_id: 77,
      message: "New pending playbook retry execution created. No steps have run.",
    };
    global.fetch.mockResolvedValue({
      ok: true,
      status: 201,
      json: () => Promise.resolve(payload),
    });

    const result = await executeDeadLetterRetry(42);
    const [url, options] = global.fetch.mock.calls[0];

    expect(url).toBe("/dead-letters/42/retry-execute");
    expect(options.method).toBe("POST");
    expect(options.credentials).toBe("include");
    expect(options.body).toBeUndefined();
    expect(result).toBe(payload);
  });

  test("OpenSpec retry aliases call existing retry endpoints", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ id: 42 }),
    });

    await retryRequestDeadLetter(42);
    await retryExecuteDeadLetter(43);

    expect(global.fetch.mock.calls[0][0]).toBe("/dead-letters/42/retry-request");
    expect(global.fetch.mock.calls[1][0]).toBe("/dead-letters/43/retry-execute");
  });

  test("throws backend message on non-OK response", async () => {
    global.fetch.mockResolvedValue({
      ok: false,
      status: 409,
      json: () => Promise.resolve({ message: "Dead letter must be retrying." }),
    });

    await expect(executeDeadLetterRetry(42)).rejects.toThrow(
      "Dead letter must be retrying."
    );
  });

  test("throws error field before message on non-OK response", async () => {
    global.fetch.mockResolvedValue({
      ok: false,
      status: 403,
      json: () => Promise.resolve({ error: "forbidden", message: "No access" }),
    });

    await expect(getDeadLetter(42)).rejects.toThrow("forbidden");
  });

  test("throws fallback message on non-OK malformed JSON", async () => {
    global.fetch.mockResolvedValue({
      ok: false,
      status: 500,
      json: () => Promise.reject(new SyntaxError("bad json")),
    });

    await expect(getDeadLetters()).rejects.toThrow("Unable to load dead letters");
  });

  test("returns fallback value on successful malformed JSON", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.reject(new SyntaxError("bad json")),
    });

    await expect(getDeadLetters()).resolves.toEqual({
      items: [],
      limit: 100,
      offset: 0,
    });
  });
});
