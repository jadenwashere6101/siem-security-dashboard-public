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
  const res = await fetch(buildSiemPath("/ai/repo/chat"), {
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

  return data;
};
