import { getApiErrorMessage, parseJsonResponse } from "../utils/apiResponse";
import { buildSiemPath } from "../utils/siemPath";

export const loadAuditLogEvents = async () => {
  const res = await fetch(buildSiemPath("/admin/audit-log"), {
    credentials: "include",
  });
  const data = await parseJsonResponse(res, []);

  if (!res.ok) {
    throw new Error(
      getApiErrorMessage(data, "Unable to load audit log", ["error"])
    );
  }

  return data;
};
