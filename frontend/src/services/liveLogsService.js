import { getApiErrorMessage, parseJsonResponse } from "../utils/apiResponse";
import { buildSiemPath } from "../utils/siemPath";

export const loadLiveLogs = async ({ source, afterId } = {}) => {
  const params = new URLSearchParams();
  if (source) params.set("source", source);
  if (afterId !== undefined && afterId !== null && afterId !== "") {
    params.set("after_id", String(afterId));
  }

  const path = params.toString()
    ? `${buildSiemPath("/events/search")}?${params.toString()}`
    : buildSiemPath("/events/search");

  const res = await fetch(path, {
    credentials: "include",
  });
  const data = await parseJsonResponse(res, []);

  if (!res.ok) {
    throw new Error(getApiErrorMessage(data, "Unable to load live logs", ["error"]));
  }

  return Array.isArray(data) ? data : [];
};
