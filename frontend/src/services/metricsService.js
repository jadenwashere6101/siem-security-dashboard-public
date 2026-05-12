import { getApiErrorMessage, parseJsonResponse } from "../utils/apiResponse";
import { buildSiemPath } from "../utils/siemPath";

export async function getPlaybookMetrics() {
  const res = await fetch(buildSiemPath("/metrics/playbooks"), {
    credentials: "include",
  });
  const data = await parseJsonResponse(res, {});
  if (!res.ok) {
    throw new Error(
      getApiErrorMessage(data, "Unable to load playbook metrics", ["error", "message"])
    );
  }
  return data;
}

export async function getNotificationDeliveryMetrics() {
  const res = await fetch(buildSiemPath("/metrics/notifications"), {
    credentials: "include",
  });
  const data = await parseJsonResponse(res, {});
  if (!res.ok) {
    throw new Error(
      getApiErrorMessage(data, "Unable to load notification delivery metrics", ["error", "message"])
    );
  }
  return data;
}
