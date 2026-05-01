import { getApiErrorMessage, parseJsonResponse } from "../utils/apiResponse";
import { buildSiemPath } from "../utils/siemPath";

export const loadBlocklistEntries = async () => {
  const res = await fetch(buildSiemPath("/blocked-ips"), {
    credentials: "include",
  });
  const data = await parseJsonResponse(res, []);

  if (!res.ok) {
    throw new Error(
      getApiErrorMessage(data, "Unable to load blocked IPs", ["error"])
    );
  }

  return data;
};

export const addBlocklistEntry = async ({ ipAddress, reason, expiresAt }) => {
  const res = await fetch(buildSiemPath("/blocked-ips"), {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      ip_address: ipAddress,
      reason,
      expires_at: expiresAt ? new Date(expiresAt).toISOString() : null,
    }),
  });
  const data = await parseJsonResponse(res, {});

  if (!res.ok) {
    throw new Error(
      getApiErrorMessage(data, "Unable to add blocked IP", ["error"])
    );
  }

  return data;
};

export const unblockBlocklistEntry = async (blockId) => {
  const res = await fetch(buildSiemPath(`/blocked-ips/${blockId}/unblock`), {
    method: "PATCH",
    credentials: "include",
  });
  const data = await parseJsonResponse(res, {});

  if (!res.ok) {
    throw new Error(
      getApiErrorMessage(data, "Unable to unblock IP", ["error"])
    );
  }

  return data;
};
