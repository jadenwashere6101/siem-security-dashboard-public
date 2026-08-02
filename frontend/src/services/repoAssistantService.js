import { getApiErrorMessage, parseJsonResponse } from "../utils/apiResponse";
import { buildSiemPath } from "../utils/siemPath";

const fallbackRepoAssistantResponse = {
  status: "failed",
  answer: null,
  insufficient_evidence: false,
  citations: [],
  retrieval: { indexed_files: 0, matched_chunks: 0, refreshed: false, excluded_matches: [] },
  metadata: null,
  error: "Repository assistant response unavailable.",
};

export const getRepoAssistantStatus = async (options = {}) => {
  const res = await fetch(buildSiemPath("/ai/repo/status"), {
    credentials: "include",
    signal: options.signal,
  });
  const data = await parseJsonResponse(res, {});

  if (!res.ok) {
    const error = new Error(getApiErrorMessage(data, "Failed to fetch repo assistant status", ["error", "message"]));
    error.status = res.status;
    error.payload = data;
    throw error;
  }

  return data;
};

export const sendRepoAssistantMessage = async (payload, options = {}) => {
  const res = await fetch(buildSiemPath("/ai/repo/requests"), {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload || {}),
    signal: options.signal,
  });
  const data = await parseJsonResponse(res, fallbackRepoAssistantResponse);

  if (!res.ok) {
    const error = new Error(getApiErrorMessage(data, "Repository assistant request failed", ["error", "message"]));
    error.status = res.status;
    error.payload = data;
    throw error;
  }

  if (res.status !== 202 || !data?.request_id) {
    return data;
  }

  options.onProgress?.(data);
  return pollRepoAssistantRequest(data.request_id, options);
};

export const getRepoAssistantRequest = async (requestId, options = {}) => {
  const res = await fetch(buildSiemPath(`/ai/repo/requests/${encodeURIComponent(requestId)}`), {
    credentials: "include",
    signal: options.signal,
  });
  const data = await parseJsonResponse(res, fallbackRepoAssistantResponse);

  if (!res.ok) {
    const error = new Error(getApiErrorMessage(data, "Repository assistant request status failed", ["error", "message"]));
    error.status = res.status;
    error.payload = data;
    throw error;
  }

  return data;
};

export const pollRepoAssistantRequest = async (requestId, options = {}) => {
  const pollIntervalMs = options.pollIntervalMs ?? 2500;
  const timeoutMs = options.timeoutMs ?? 150000;
  const startedAt = Date.now();

  while (Date.now() - startedAt < timeoutMs) {
    const data = await getRepoAssistantRequest(requestId, options);
    options.onProgress?.(data);
    if (data?.terminal || ["completed", "partial", "degraded", "failed", "timed_out", "cancelled", "expired"].includes(data?.status)) {
      if (data.result) {
        return {
          ...data.result,
          async_request: {
            request_id: data.request_id,
            status: data.status,
            lifecycle: data.lifecycle,
            timestamps: data.timestamps,
          },
        };
      }
      return data;
    }
    await new Promise((resolve) => setTimeout(resolve, pollIntervalMs));
  }

  const error = new Error("Repository assistant request timed out while polling.");
  error.status = 408;
  error.payload = { status: "timed_out", error: error.message, request_id: requestId };
  throw error;
};
