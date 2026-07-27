import { getApiErrorMessage, parseJsonResponse } from "../utils/apiResponse";
import { buildSiemPath } from "../utils/siemPath";

const listFallback = { items: [], limit: 25, offset: 0, total: 0 };
const detailFallback = { sections: {}, evidence_refs: [], run_steps: [], deliveries: [] };

export async function listSocBriefings(filters = {}) {
  const params = new URLSearchParams();
  const keys = [
    "status",
    "content_status",
    "schedule_id",
    "delivery_status",
    "provider_status",
    "generated_from",
    "generated_to",
    "search",
    "limit",
    "offset",
  ];
  for (const key of keys) {
    const value = filters[key];
    if (value !== undefined && value !== null && value !== "") {
      params.set(key, String(value));
    }
  }
  const query = params.toString();
  const res = await fetch(buildSiemPath(`/soc-briefings${query ? `?${query}` : ""}`), {
    credentials: "include",
  });
  const data = await parseJsonResponse(res, listFallback);
  if (!res.ok) {
    throw new Error(getApiErrorMessage(data, "Unable to load SOC briefings", ["error", "message"]));
  }
  return data;
}

export async function getSocBriefing(briefingId) {
  const res = await fetch(buildSiemPath(`/soc-briefings/${briefingId}`), {
    credentials: "include",
  });
  const data = await parseJsonResponse(res, detailFallback);
  if (!res.ok) {
    throw new Error(getApiErrorMessage(data, "Unable to load SOC briefing", ["error", "message"]));
  }
  return data;
}
