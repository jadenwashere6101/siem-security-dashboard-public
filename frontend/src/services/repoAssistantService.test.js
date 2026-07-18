import { getRepoAssistantStatus, sendRepoAssistantMessage } from "./repoAssistantService";

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
    json: async () => ({ status: "success", answer: "ok" }),
  });

  const result = await sendRepoAssistantMessage(payload, { signal: controller.signal });

  expect(result.answer).toBe("ok");
  expect(fetch).toHaveBeenCalledWith(
    expect.stringContaining("/ai/repo/chat"),
    expect.objectContaining({
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: controller.signal,
    })
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
