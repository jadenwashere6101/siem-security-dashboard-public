const SIEM_BASE_PATH =
  typeof window !== "undefined" &&
  (window.location.pathname === "/siem" || window.location.pathname.startsWith("/siem/"))
    ? "/siem"
    : "";

export const buildSiemPath = (path) => `${SIEM_BASE_PATH}${path}`;
