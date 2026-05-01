const SESSION_IDENTITY_KEY = "siem_last_identity";

export const readStoredSessionIdentity = () => {
  if (typeof window === "undefined") return null;

  try {
    const rawValue = window.sessionStorage.getItem(SESSION_IDENTITY_KEY);
    return rawValue ? JSON.parse(rawValue) : null;
  } catch (_error) {
    return null;
  }
};

export const writeStoredSessionIdentity = (identity) => {
  if (typeof window === "undefined") return;

  try {
    if (!identity?.authenticated) {
      window.sessionStorage.removeItem(SESSION_IDENTITY_KEY);
      return;
    }

    window.sessionStorage.setItem(SESSION_IDENTITY_KEY, JSON.stringify(identity));
  } catch (_error) {
  }
};
