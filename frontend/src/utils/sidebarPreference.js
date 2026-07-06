const SIDEBAR_COLLAPSED_KEY = "siem_sidebar_collapsed";

export const readStoredSidebarCollapsed = () => {
  if (typeof window === "undefined") return null;

  try {
    const rawValue = window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY);
    if (rawValue === null) return null;

    const parsed = JSON.parse(rawValue);
    return typeof parsed === "boolean" ? parsed : null;
  } catch (_error) {
    return null;
  }
};

export const writeStoredSidebarCollapsed = (isCollapsed) => {
  if (typeof window === "undefined") return;

  try {
    window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, JSON.stringify(!!isCollapsed));
  } catch (_error) {
  }
};
