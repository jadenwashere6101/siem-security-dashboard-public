import { getApiErrorMessage, parseJsonResponse } from "../utils/apiResponse";
import { buildSiemPath } from "../utils/siemPath";

const listFallback = { items: [], limit: 100, offset: 0 };

/**
 * Read-only list of notification delivery attempts (GET /notification-deliveries).
 * @param {Record<string, string|number|undefined|null>} filters
 */
export async function listNotificationDeliveries(filters = {}) {
  const params = new URLSearchParams();
  const keys = [
    "provider",
    "mode",
    "status",
    "correlation_id",
    "playbook_execution_id",
    "incident_id",
    "approval_request_id",
    "adapter_name",
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
  const res = await fetch(buildSiemPath(`/notification-deliveries${query ? `?${query}` : ""}`), {
    credentials: "include",
  });
  const data = await parseJsonResponse(res, listFallback);
  if (!res.ok) {
    throw new Error(
      getApiErrorMessage(data, "Unable to load notification deliveries", ["error", "message"])
    );
  }
  return data;
}

/**
 * Read-only delivery attempts linked to one incident_id.
 * Uses the existing GET /notification-deliveries list endpoint.
 */
export async function listIncidentNotificationDeliveries(incidentId, filters = {}) {
  return listNotificationDeliveries({
    ...filters,
    incident_id: incidentId,
  });
}

/**
 * Read-only delivery attempts linked to one approval_request_id.
 * Uses the existing GET /notification-deliveries list endpoint.
 */
export async function listApprovalNotificationDeliveries(approvalRequestId, filters = {}) {
  return listNotificationDeliveries({
    ...filters,
    approval_request_id: approvalRequestId,
  });
}
