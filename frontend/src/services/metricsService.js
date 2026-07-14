import { getApiErrorMessage, parseJsonResponse } from "../utils/apiResponse";
import { buildSiemPath } from "../utils/siemPath";

const metricsFallback = {};

const fetchMetrics = async (path, fallbackMessage, query = "") => {
  const res = await fetch(buildSiemPath(`${path}${query ? `?${query}` : ""}`), {
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

export async function getIncidentMetrics({ operationalScope } = {}) {
  const params = new URLSearchParams();
  if (operationalScope && operationalScope !== "all_history") {
    params.set("operational_scope", operationalScope);
  }
  return fetchMetrics(
    "/metrics/incidents",
    "Unable to load incident metrics",
    params.toString()
  );
}

export async function getApprovalMetrics() {
  return fetchMetrics("/metrics/approvals", "Unable to load approval metrics");
}

export async function getPlaybookWorkerMetrics() {
  return fetchMetrics(
    "/metrics/playbook-worker",
    "Unable to load playbook worker metrics"
  );
}
