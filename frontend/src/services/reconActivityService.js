import { getApiErrorMessage, parseJsonResponse } from "../utils/apiResponse";
import { buildSiemPath } from "../utils/siemPath";

const listFallback = { items: [], count: 0 };
const detailFallback = { alerts: [], summary: {} };

export async function loadReconActivities({ limit = 12, status } = {}) {
  const params = new URLSearchParams();
  if (limit) params.set("limit", String(limit));
  if (status) params.set("status", status);
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
