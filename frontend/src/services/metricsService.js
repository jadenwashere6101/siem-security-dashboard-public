import { getApiErrorMessage, parseJsonResponse } from "../utils/apiResponse";
import { buildSiemPath } from "../utils/siemPath";

const metricsFallback = {};

const fetchMetrics = async (path, fallbackMessage) => {
  const res = await fetch(buildSiemPath(path), {
    credentials: "include",
  });
  const data = await parseJsonResponse(res, metricsFallback);
  if (!res.ok) {
    throw new Error(
      getApiErrorMessage(data, fallbackMessage, ["error", "message"])
    );
  }
  return data;
};

export async function getPlaybookMetrics() {
  return fetchMetrics("/metrics/playbooks", "Unable to load playbook metrics");
}

export async function getNotificationDeliveryMetrics() {
  return fetchMetrics(
    "/metrics/notifications",
    "Unable to load notification delivery metrics"
  );
}

export async function getIncidentMetrics() {
  return fetchMetrics("/metrics/incidents", "Unable to load incident metrics");
}

export async function getApprovalMetrics() {
  return fetchMetrics("/metrics/approvals", "Unable to load approval metrics");
}
