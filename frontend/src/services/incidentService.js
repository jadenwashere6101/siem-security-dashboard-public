import { getApiErrorMessage, parseJsonResponse } from "../utils/apiResponse";
import { buildSiemPath } from "../utils/siemPath";

export const loadIncidents = async ({
  status,
  severity,
  limit = 50,
  offset = 0,
} = {}) => {
  const params = new URLSearchParams();
  if (status && status !== "all") params.set("status", status);
  if (severity && severity !== "all") params.set("severity", severity);
  if (limit && limit !== 50) params.set("limit", String(limit));
  if (offset) params.set("offset", String(offset));

  const query = params.toString();
  const res = await fetch(buildSiemPath(`/incidents${query ? `?${query}` : ""}`), {
    credentials: "include",
  });
  const data = await parseJsonResponse(res, { incidents: [], count: 0 });

  if (!res.ok) {
    throw new Error(
      getApiErrorMessage(data, "Unable to load incidents", ["error"])
    );
  }

  return data;
};

export const loadIncidentDetail = async (incidentId) => {
  const res = await fetch(buildSiemPath(`/incidents/${incidentId}`), {
    credentials: "include",
  });
  const data = await parseJsonResponse(res, {});

  if (!res.ok) {
    throw new Error(
      getApiErrorMessage(data, "Unable to load incident detail", ["error"])
    );
  }

  return data;
};

export const updateIncidentStatus = async (incidentId, status) => {
  const res = await fetch(buildSiemPath(`/incidents/${incidentId}/status`), {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
  const data = await parseJsonResponse(res, {});

  if (!res.ok) {
    throw new Error(
      getApiErrorMessage(data, "Unable to update incident status", ["error"])
    );
  }

  return data;
};
