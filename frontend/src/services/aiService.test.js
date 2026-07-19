import {
  getAiStatus,
  requestAiChat,
  requestAiDraft,
  requestAiExplanation,
  sendSiemChatMessage,
} from "./aiService";

beforeEach(() => {
  global.fetch = jest.fn();
});

afterEach(() => {
  jest.restoreAllMocks();
});

test("requestAiExplanation posts to the read-only explain endpoint", async () => {
  fetch.mockResolvedValue({
    ok: true,
    json: async () => ({ status: "success", answer: "ok" }),
  });

  const result = await requestAiExplanation({
    context_type: "alert",
    action: "explain_alert",
    context: { alert_id: 1 },
  });

  expect(result.answer).toBe("ok");
  expect(fetch).toHaveBeenCalledWith(
    expect.stringContaining("/ai/explain"),
    expect.objectContaining({
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        context_type: "alert",
        action: "explain_alert",
        context: { alert_id: 1 },
      }),
    })
  );
});

test("requestAiChat posts visible context and client-owned history", async () => {
  fetch.mockResolvedValue({
    ok: true,
    json: async () => ({ status: "success", answer: "chat" }),
  });

  await sendSiemChatMessage({
    message: "What is this?",
    visible_context: { active_section: "dashboard" },
    client_history: [{ role: "user", content: "previous" }],
  });

  expect(fetch).toHaveBeenCalledWith(
    expect.stringContaining("/ai/chat"),
    expect.objectContaining({
      method: "POST",
      credentials: "include",
      body: JSON.stringify({
        message: "What is this?",
        visible_context: { active_section: "dashboard" },
        client_history: [{ role: "user", content: "previous" }],
      }),
    })
  );
});

test("requestAiChat preserves optional read-tool policy", async () => {
  fetch.mockResolvedValue({
    ok: true,
    json: async () => ({ status: "success", answer: "chat" }),
  });

  await sendSiemChatMessage({
    message: "Show me everything tied to this IP",
    visible_context: { active_section: "dashboard" },
    client_history: [],
    use_tools: true,
    tool_policy: { max_tool_calls: 5, time_window_hours: 24 },
  });

  expect(fetch).toHaveBeenCalledWith(
    expect.stringContaining("/ai/chat"),
    expect.objectContaining({
      body: JSON.stringify({
        message: "Show me everything tied to this IP",
        visible_context: { active_section: "dashboard" },
        client_history: [],
        use_tools: true,
        tool_policy: { max_tool_calls: 5, time_window_hours: 24 },
      }),
    })
  );
});

test("requestAiDraft posts review-only draft requests", async () => {
  const controller = new AbortController();
  fetch.mockResolvedValue({
    ok: true,
    json: async () => ({
      status: "success",
      draft: {
        draft_type: "incident_note",
        labels: { ai_generated: true, read_only: true, persisted: false, applied: false },
      },
    }),
  });

  const result = await requestAiDraft(
    {
      draft_type: "incident_note",
      instruction: "Draft a note.",
      context_type: "incident",
      context: { incident_id: 7 },
      use_tools: true,
      tool_policy: { max_tool_calls: 3, time_window_hours: 24 },
    },
    { signal: controller.signal }
  );

  expect(result.draft.labels.persisted).toBe(false);
  expect(fetch).toHaveBeenCalledWith(
    expect.stringContaining("/ai/drafts"),
    expect.objectContaining({
      method: "POST",
      credentials: "include",
      signal: controller.signal,
      body: JSON.stringify({
        draft_type: "incident_note",
        instruction: "Draft a note.",
        context_type: "incident",
        context: { incident_id: 7 },
        use_tools: true,
        tool_policy: { max_tool_calls: 3, time_window_hours: 24 },
      }),
    })
  );
});

test("getAiStatus fetches status with credentials and abort signal", async () => {
  const controller = new AbortController();
  fetch.mockResolvedValue({
    ok: true,
    json: async () => ({ read_only: true }),
  });

  const result = await getAiStatus({ signal: controller.signal });

  expect(result.read_only).toBe(true);
  expect(fetch).toHaveBeenCalledWith(
    expect.stringContaining("/ai/status"),
    expect.objectContaining({
      credentials: "include",
      signal: controller.signal,
    })
  );
});

test("requestAiExplanation maps server errors without logging payloads", async () => {
  fetch.mockResolvedValue({
    ok: false,
    status: 403,
    json: async () => ({ error: "Forbidden" }),
  });

  await expect(requestAiExplanation({ context_type: "alert" })).rejects.toMatchObject({
    message: "Forbidden",
    status: 403,
  });
});
