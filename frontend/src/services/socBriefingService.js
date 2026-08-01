import { getApiErrorMessage, parseJsonResponse } from "../utils/apiResponse";
import { buildSiemPath } from "../utils/siemPath";

const listFallback = { items: [], limit: 25, offset: 0, total: 0 };
const detailFallback = { sections: {}, evidence_refs: [], run_steps: [], deliveries: [] };
const controlFallback = { mode: "manual_only", schedules_paused: true, ai: {}, active_jobs: {} };

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

export async function getSocBriefingControl() {
  const res = await fetch(buildSiemPath("/soc-briefings/control"), {
    credentials: "include",
  });
  const data = await parseJsonResponse(res, controlFallback);
  if (!res.ok) {
    throw new Error(getApiErrorMessage(data, "Unable to load SOC briefing controls", ["error", "message"]));
  }
  return data;
}

export async function updateSocBriefingMode(mode) {
  const res = await fetch(buildSiemPath("/soc-briefings/control/mode"), {
    method: "PUT",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode }),
  });
  const data = await parseJsonResponse(res, controlFallback);
  if (!res.ok) {
    throw new Error(getApiErrorMessage(data, "Unable to update SOC briefing mode", ["error", "message"]));
  }
  return data;
}

export async function updateSocBriefingPause(schedulesPaused, pauseReason = "") {
  const res = await fetch(buildSiemPath("/soc-briefings/control/pause"), {
    method: "PUT",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ schedules_paused: Boolean(schedulesPaused), pause_reason: pauseReason }),
  });
  const data = await parseJsonResponse(res, controlFallback);
  if (!res.ok) {
    throw new Error(getApiErrorMessage(data, "Unable to update SOC briefing pause state", ["error", "message"]));
  }
  return data;
}

export async function runSocBriefingNow() {
  const res = await fetch(buildSiemPath("/soc-briefings/run-now"), {
    method: "POST",
    credentials: "include",
  });
  const data = await parseJsonResponse(res, {});
  if (!res.ok) {
    throw new Error(getApiErrorMessage(data, "Unable to run Anakin briefing now", ["error", "message"]));
  }
  return data;
}

export async function getManualSocBriefingRunStatus(jobId = null) {
  const params = new URLSearchParams();
  if (jobId !== null && jobId !== undefined && jobId !== "") {
    params.set("job_id", String(jobId));
  }
  const query = params.toString();
  const res = await fetch(buildSiemPath(`/soc-briefings/manual-run/status${query ? `?${query}` : ""}`), {
    credentials: "include",
  });
  const data = await parseJsonResponse(res, {});
  if (!res.ok) {
    throw new Error(getApiErrorMessage(data, "Unable to load manual Anakin briefing run status", ["error", "message"]));
  }
  return data;
}
