import { getApiErrorMessage, parseJsonResponse } from "../utils/apiResponse";
import { buildSiemPath } from "../utils/siemPath";

export const loadSeverityResponseMatrix = async () => {
  const response = await fetch(buildSiemPath("/api/severity-response-matrix"), {
    credentials: "include",
  });
  const data = await parseJsonResponse(response, {});
  if (!response.ok) {
    throw new Error(
      getApiErrorMessage(data, "Unable to load severity and response matrix", ["error", "message"])
    );
  }
  return data;
};
