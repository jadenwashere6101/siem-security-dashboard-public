import { getApiErrorMessage, parseJsonResponse } from "../utils/apiResponse";
import { buildSiemPath } from "../utils/siemPath";

const listFallback = { items: [], count: 0, total: 0, limit: 0, offset: 0 };
const detailFallback = { alerts: [], summary: {}, recon_intelligence: {} };
const linkedAlertsFallback = { items: [], count: 0, total: 0, limit: 0, offset: 0 };

export async function loadReconActivities({
  limit = 12,
  offset = 0,
  status,
  severity,
  confidence,
  classification,
  search,
  timeRange,
  startTime,
  endTime,
  sort,
} = {}) {
  const params = new URLSearchParams();
  if (limit) params.set("limit", String(limit));
  if (offset) params.set("offset", String(offset));
  if (status) params.set("status", status);
  if (severity) params.set("severity", severity);
  if (confidence) params.set("confidence", confidence);
  if (classification) params.set("classification", classification);
  if (search) params.set("search", search);
  if (timeRange) params.set("time_range", timeRange);
  if (startTime) params.set("start_time", startTime);
  if (endTime) params.set("end_time", endTime);
  if (sort) params.set("sort", sort);
  const query = params.toString();
  const res = await fetch(buildSiemPath(`/recon-activities${query ? `?${query}` : ""}`), {
    credentials: "include",
  });
  const data = await parseJsonResponse(res, listFallback);
  if (!res.ok) {
    throw new Error(getApiErrorMessage(data, "Unable to load recon activities", ["error", "message"]));
  }
  return data;
}

export async function loadReconActivityAlerts(activityId, { limit = 10, offset = 0, sort = "newest" } = {}) {
  const params = new URLSearchParams();
  if (limit) params.set("limit", String(limit));
  if (offset) params.set("offset", String(offset));
  if (sort) params.set("sort", sort);
  const query = params.toString();
  const res = await fetch(buildSiemPath(`/recon-activities/${activityId}/alerts${query ? `?${query}` : ""}`), {
    credentials: "include",
  });
  const data = await parseJsonResponse(res, linkedAlertsFallback);
  if (!res.ok) {
    throw new Error(getApiErrorMessage(data, "Unable to load recon activity alerts", ["error", "message"]));
  }
  return data;
}

export async function loadReconActivity(activityId) {
  const res = await fetch(buildSiemPath(`/recon-activities/${activityId}`), {
    credentials: "include",
  });
  const data = await parseJsonResponse(res, detailFallback);
  if (!res.ok) {
    throw new Error(getApiErrorMessage(data, "Unable to load recon activity", ["error", "message"]));
  }
  return data;
}
