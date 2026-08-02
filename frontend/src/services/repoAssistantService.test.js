import { getRepoAssistantRequest, getRepoAssistantStatus, sendRepoAssistantMessage } from "./repoAssistantService";

beforeEach(() => {
  global.fetch = jest.fn();
});

afterEach(() => {
  jest.restoreAllMocks();
});

test("getRepoAssistantStatus fetches status with credentials and abort signal", async () => {
  const controller = new AbortController();
  fetch.mockResolvedValue({
    ok: true,
    json: async () => ({ status: "available", indexed_files: 7 }),
  });

  const result = await getRepoAssistantStatus({ signal: controller.signal });

  expect(result.indexed_files).toBe(7);
  expect(fetch).toHaveBeenCalledWith(
    expect.stringContaining("/ai/repo/status"),
    expect.objectContaining({
      credentials: "include",
      signal: controller.signal,
    })
  );
});

test("sendRepoAssistantMessage posts repo question with credentials and abort signal", async () => {
  const controller = new AbortController();
  const payload = {
    message: "Where do detection rules live?",
    client_history: [{ role: "user", content: "previous" }],
    refresh: true,
  };
  fetch.mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({ status: "success", answer: "ok" }),
  });

  const result = await sendRepoAssistantMessage(payload, { signal: controller.signal });

  expect(result.answer).toBe("ok");
  expect(fetch).toHaveBeenCalledWith(
    expect.stringContaining("/ai/repo/requests"),
    expect.objectContaining({
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: controller.signal,
    })
  );
});

test("sendRepoAssistantMessage polls queued repo request to completion", async () => {
  const progress = jest.fn();
  fetch
    .mockResolvedValueOnce({
      ok: true,
      status: 202,
      json: async () => ({ status: "queued", request_id: "repo-1", lifecycle: { stage: "queued" } }),
    })
    .mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({
        status: "completed",
        request_id: "repo-1",
        terminal: true,
        lifecycle: { stage: "complete" },
        result: { status: "success", answer: "repo answer", citations: [], retrieval: {}, metadata: {} },
      }),
    });

  const result = await sendRepoAssistantMessage(
    { message: "Where is the worker implemented?" },
    { onProgress: progress, pollIntervalMs: 0 }
  );

  expect(result.answer).toBe("repo answer");
  expect(result.async_request.request_id).toBe("repo-1");
  expect(progress).toHaveBeenCalledWith(expect.objectContaining({ request_id: "repo-1" }));
  expect(fetch.mock.calls[0][0]).toEqual(expect.stringContaining("/ai/repo/requests"));
  expect(fetch.mock.calls[1][0]).toEqual(expect.stringContaining("/ai/repo/requests/repo-1"));
});

test("getRepoAssistantRequest fetches request status", async () => {
  fetch.mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({ status: "running", request_id: "repo-2" }),
  });

  const result = await getRepoAssistantRequest("repo-2");

  expect(result.status).toBe("running");
  expect(fetch).toHaveBeenCalledWith(
    expect.stringContaining("/ai/repo/requests/repo-2"),
    expect.objectContaining({ credentials: "include" })
  );
});

test("sendRepoAssistantMessage maps safe server errors", async () => {
  fetch.mockResolvedValue({
    ok: false,
    status: 403,
    json: async () => ({ error: "Forbidden" }),
  });

  await expect(sendRepoAssistantMessage({ message: "repo?" })).rejects.toMatchObject({
    message: "Forbidden",
    status: 403,
  });
});
