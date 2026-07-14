import { getApiErrorMessage, parseJsonResponse } from "../utils/apiResponse";
import { buildSiemPath } from "../utils/siemPath";

const listFallback = { items: [], total: 0, limit: 50, offset: 0, sort: "newest" };
const summaryFallback = {
  metrics: {
    total_alerts: 0,
    high_count: 0,
    medium_count: 0,
    low_count: 0,
    unique_source_ips: 0,
  },
  top_source_ips: [],
  timeline: [],
  map_markers: [],
};

function buildAlertQuery({
  searchTerm,
  severityFilter,
  statusFilter,
  sourceFilter,
  sortOption,
  limit,
  offset,
} = {}) {
  const params = new URLSearchParams();
  if (searchTerm) params.set("search", String(searchTerm).trim());
  if (severityFilter && severityFilter !== "all") params.set("severity", severityFilter);
  if (statusFilter && statusFilter !== "all") params.set("status", statusFilter);
  if (sourceFilter && sourceFilter !== "all") params.set("source", sourceFilter);
  if (sortOption) params.set("sort", sortOption);
  if (limit !== undefined && limit !== null && limit !== "") params.set("limit", String(limit));
  if (offset !== undefined && offset !== null && offset !== "") params.set("offset", String(offset));
  return params.toString();
}

export const loadAlerts = async (queryOptions = {}) => {
  const query = buildAlertQuery(queryOptions);
  const res = await fetch(buildSiemPath(`/alerts${query ? `?${query}` : ""}`), {
    credentials: "include",
  });
  const data = await parseJsonResponse(res, listFallback);

  if (!res.ok) {
    throw new Error(getApiErrorMessage(data, "Failed to fetch alerts", ["error", "message"]));
  }

  return data;
};

export const loadAlertDashboardSummary = async (queryOptions = {}) => {
  const query = buildAlertQuery(queryOptions);
  const res = await fetch(buildSiemPath(`/alerts/summary${query ? `?${query}` : ""}`), {
    credentials: "include",
  });
  const data = await parseJsonResponse(res, summaryFallback);

  if (!res.ok) {
    throw new Error(
      getApiErrorMessage(data, "Failed to fetch alert dashboard summary", ["error", "message"])
    );
  }

  return data;
};
