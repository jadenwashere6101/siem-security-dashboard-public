import { getApiErrorMessage, parseJsonResponse } from "../utils/apiResponse";
import { buildSiemPath } from "../utils/siemPath";

const requestJson = async (path, options, fallbackMessage) => {
  const response = await fetch(buildSiemPath(path), {
    credentials: "include",
    ...options,
  });
  const data = await parseJsonResponse(response, {});
  if (!response.ok) {
    throw new Error(getApiErrorMessage(data, fallbackMessage, ["error"]));
  }
  return data;
};

export const loadPfsenseIngestFilters = () =>
  requestJson("/admin/pfsense-ingest-filters", {}, "Unable to load pfSense ingest filters");

export const loadPfsenseIngestFilterMetrics = () =>
  requestJson(
    "/admin/pfsense-ingest-filters/metrics",
    {},
    "Unable to load pfSense ingest filter metrics"
  );

export const updatePfsenseIngestFilter = (category, enabled, parameters = {}) =>
  requestJson(
    `/admin/pfsense-ingest-filters/${encodeURIComponent(category)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled, parameters }),
    },
    "Unable to update pfSense ingest filter"
  );
