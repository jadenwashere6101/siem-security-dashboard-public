import { getApiErrorMessage, parseJsonResponse } from "../utils/apiResponse";
import { buildSiemPath } from "../utils/siemPath";

export async function getIntegrationStatus() {
  const res = await fetch(buildSiemPath("/integrations/status"), {
    credentials: "include",
  });
  const data = await parseJsonResponse(res, {});
  if (!res.ok) {
    throw new Error(
      getApiErrorMessage(data, "Unable to load integration status", ["error", "message"])
    );
  }
  return data;
}
