import { getApiErrorMessage, parseJsonResponse } from "../utils/apiResponse";
import { buildSiemPath } from "../utils/siemPath";

const requestJson = async (path, options, fallbackMessage) => {
  const response = await fetch(buildSiemPath(path), {
    credentials: "include",
    ...options,
  });
  const data = await parseJsonResponse(response, {});
  if (!response.ok) {
    throw new Error(getApiErrorMessage(data, fallbackMessage, ["error", "message"]));
  }
  return data;
};

export const loadNotificationPolicy = () =>
  requestJson("/admin/notification-policy", {}, "Unable to load notification policy");

export const updateNotificationPolicy = (updates) =>
  requestJson(
    "/admin/notification-policy",
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updates),
    },
    "Unable to update notification policy"
  );
