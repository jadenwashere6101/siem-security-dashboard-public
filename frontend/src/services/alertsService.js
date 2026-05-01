import { buildSiemPath } from "../utils/siemPath";

export const loadAlerts = async () => {
  const res = await fetch(buildSiemPath("/alerts"), {
    credentials: "include",
  });

  if (!res.ok) {
    throw new Error("Failed to fetch alerts");
  }

  return res.json();
};
