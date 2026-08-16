import { getApiErrorMessage, parseJsonResponse } from "../utils/apiResponse";
import { buildSiemPath } from "../utils/siemPath";

async function request(path, { method = "GET", body, signal } = {}) {
  const response = await fetch(buildSiemPath(path), {
    method,
    credentials: "include",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  });
  const data = await parseJsonResponse(response, {});
  if (!response.ok) {
    const error = new Error(getApiErrorMessage(data, "Unable to load NIST evidence", ["error", "message"]));
    error.status = response.status;
    error.payload = data;
    throw error;
  }
  return data;
}

export const loadNistBoundaries = (options = {}) =>
  request("/nist/evidence/boundaries?limit=100", options);

export const createNistBoundary = (payload, options = {}) =>
  request("/nist/evidence/boundaries", { ...options, method: "POST", body: payload });

export const updateNistBoundary = (boundaryId, payload, options = {}) =>
  request(`/nist/evidence/boundaries/${encodeURIComponent(boundaryId)}`, {
    ...options,
    method: "PATCH",
    body: payload,
  });

export const loadNistRuns = (boundaryId, { cursor, limit = 25, ...options } = {}) => {
  const params = new URLSearchParams({ limit: String(limit) });
  if (cursor?.before_created_at && cursor?.before_id) {
    params.set("before_created_at", cursor.before_created_at);
    params.set("before_id", String(cursor.before_id));
  }
  return request(
    `/nist/evidence/boundaries/${encodeURIComponent(boundaryId)}/runs?${params}`,
    options
  );
};

export const startNistAssessment = (boundaryId, options = {}) =>
  request(`/nist/evidence/boundaries/${encodeURIComponent(boundaryId)}/runs`, {
    ...options,
    method: "POST",
    body: {},
  });

export const loadNistResults = (runId, options = {}) =>
  request(`/nist/evidence/runs/${encodeURIComponent(runId)}/results`, options);

export const loadNistEvidence = (
  runId,
  requirementId,
  { limit = 25, offset = 0, ...options } = {}
) => {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  return request(
    `/nist/evidence/runs/${encodeURIComponent(runId)}/results/${encodeURIComponent(requirementId)}/evidence?${params}`,
    options
  );
};

export const queueNistExplanation = (payload, options = {}) =>
  request("/nist/evidence/explanations", { ...options, method: "POST", body: payload });

export const getNistExplanationRequest = (requestId, options = {}) =>
  request(`/ai/workflows/requests/${encodeURIComponent(requestId)}`, options);

export const nistExportUrl = (runId, format) =>
  buildSiemPath(
    `/nist/evidence/runs/${encodeURIComponent(runId)}/export?format=${encodeURIComponent(format)}`
  );
