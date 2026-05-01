import { buildSiemPath } from "../utils/siemPath";

export const loadAlertResponseLog = async (alertId) => {
  const res = await fetch(buildSiemPath(`/alerts/${alertId}/response-log`), {
    credentials: "include",
  });

  return res.json();
};
