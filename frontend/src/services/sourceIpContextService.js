import { getApiErrorMessage, parseJsonResponse } from "../utils/apiResponse";
import { buildSiemPath } from "../utils/siemPath";

export const loadSourceIpContext = async (sourceIp) => {
  const normalizedSourceIp = String(sourceIp || "").trim();
  if (!normalizedSourceIp) {
    throw new Error("source_ip is required");
  }

  const params = new URLSearchParams({ source_ip: normalizedSourceIp });
  const res = await fetch(buildSiemPath(`/source-ip-context?${params.toString()}`), {
    credentials: "include",
  });
  const data = await parseJsonResponse(res, {});

  if (!res.ok) {
    const error = new Error(
      getApiErrorMessage(data, "Unable to load source-IP context", ["message", "error"])
    );
    error.status = res.status;
    throw error;
  }

  return data;
};
