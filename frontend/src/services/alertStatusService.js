import { getApiErrorMessage, parseJsonResponse } from "../utils/apiResponse";
import { buildSiemPath } from "../utils/siemPath";

export const updateAlertStatusRequest = async (id, status) => {
  const response = await fetch(buildSiemPath(`/alerts/${id}/status`), {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ status }),
  });
  if (!response.ok) {
    const errorData = await parseJsonResponse(response, {});
    throw new Error(
      getApiErrorMessage(
        errorData,
        "Failed to update alert status",
        ["message", "error"]
      )
    );
  }
};
