import { getApiErrorMessage, parseJsonResponse } from "../utils/apiResponse";
import { buildSiemPath } from "../utils/siemPath";

export const loadPfsenseWhyFired = async (alertId) => {
  const res = await fetch(buildSiemPath(`/alerts/${encodeURIComponent(alertId)}/why-fired`), {
    credentials: "include",
  });
  const data = await parseJsonResponse(res, {});

  if (!res.ok) {
    throw new Error(
      getApiErrorMessage(data, "Unable to load why this fired", ["error"])
    );
  }

  return data;
};
