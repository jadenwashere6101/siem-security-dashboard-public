import { getApiErrorMessage, parseJsonResponse } from "../utils/apiResponse";
import { buildSiemPath } from "../utils/siemPath";

const listFallback = { items: [], limit: 100, offset: 0 };
const metricsFallback = {};

const listFilterKeys = [
  "status",
  "source_type",
  "failure_class",
  "retryable",
  "incident_id",
  "alert_id",
  "execution_id",
  "limit",
  "offset",
];

const buildQuery = (filters = {}) => {
  const params = new URLSearchParams();
  for (const key of listFilterKeys) {
    const value = filters[key];
    if (value !== undefined && value !== null && value !== "") {
      params.set(key, String(value));
    }
  }
  return params.toString();
};

const parseAndThrowOnError = async (res, fallbackValue, fallbackMessage) => {
  const data = await parseJsonResponse(res, fallbackValue);
  if (!res.ok) {
    throw new Error(
      getApiErrorMessage(data, fallbackMessage, ["error", "message"])
    );
  }
  return data;
};

export async function getDeadLetters(filters = {}) {
  const query = buildQuery(filters);
  const res = await fetch(buildSiemPath(`/dead-letters${query ? `?${query}` : ""}`), {
    credentials: "include",
  });
  return parseAndThrowOnError(res, listFallback, "Unable to load dead letters");
}

export const listDeadLetters = getDeadLetters;

export async function getDeadLetter(id) {
  const res = await fetch(buildSiemPath(`/dead-letters/${id}`), {
    credentials: "include",
  });
  return parseAndThrowOnError(res, {}, "Unable to load dead letter");
}

export async function getDeadLetterMetrics() {
  const res = await fetch(buildSiemPath("/metrics/dead-letters"), {
    credentials: "include",
  });
  return parseAndThrowOnError(
    res,
    metricsFallback,
    "Unable to load dead letter metrics"
  );
}

export async function dismissDeadLetter(id, body = {}) {
  const payload = body && typeof body === "object" ? body : { comment: body };
  const res = await fetch(buildSiemPath(`/dead-letters/${id}/dismiss`), {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseAndThrowOnError(res, {}, "Unable to dismiss dead letter");
}

export async function requestDeadLetterRetry(id) {
  const res = await fetch(buildSiemPath(`/dead-letters/${id}/retry-request`), {
    method: "POST",
    credentials: "include",
  });
  return parseAndThrowOnError(res, {}, "Unable to request dead letter retry");
}

export const retryRequestDeadLetter = requestDeadLetterRetry;

export async function executeDeadLetterRetry(id) {
  const res = await fetch(buildSiemPath(`/dead-letters/${id}/retry-execute`), {
    method: "POST",
    credentials: "include",
  });
  return parseAndThrowOnError(res, {}, "Unable to execute dead letter retry");
}

export const retryExecuteDeadLetter = executeDeadLetterRetry;
