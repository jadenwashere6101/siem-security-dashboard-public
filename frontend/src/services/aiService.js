import { getApiErrorMessage, parseJsonResponse } from "../utils/apiResponse";
import { buildSiemPath } from "../utils/siemPath";

const aiFallback = {
  status: "failed",
  answer: null,
  insufficient_context: false,
  context: { context_type: null, sources: [], truncated: false, omitted_count: 0 },
  metadata: null,
  error: "AI response unavailable.",
};

const postAiRequest = async (path, payload, { signal } = {}) => {
  const res = await fetch(buildSiemPath(path), {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload || {}),
    signal,
  });
  const data = await parseJsonResponse(res, aiFallback);

  if (!res.ok) {
    const error = new Error(getApiErrorMessage(data, "AI request failed", ["error", "message"]));
    error.status = res.status;
    error.payload = data;
    throw error;
  }

  return data;
};

export const requestAiExplanation = (payload, options = {}) =>
  postAiRequest("/ai/explain", payload, options);

export const sendSiemChatMessage = (payload, options = {}) =>
  postAiRequest("/ai/chat", payload, options);

export const requestAiChat = sendSiemChatMessage;

export const getAiStatus = async (options = {}) => {
  const res = await fetch(buildSiemPath("/ai/status"), {
    credentials: "include",
    signal: options.signal,
  });
  const data = await parseJsonResponse(res, {});

  if (!res.ok) {
    const error = new Error(getApiErrorMessage(data, "Failed to fetch AI status", ["error", "message"]));
    error.status = res.status;
    error.payload = data;
    throw error;
  }

  return data;
};
