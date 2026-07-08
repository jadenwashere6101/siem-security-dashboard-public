export const UI_SETTINGS_STORAGE_KEY = "siem.ui.settings.v1";
export const UI_SETTINGS_VERSION = 1;

export const DEFAULT_UI_SETTINGS = {
  defaultLandingPage: "dashboard",
  autoRefreshIntervalMs: 5000,
};

export const ALLOWED_AUTO_REFRESH_INTERVALS = [0, 5000, 10000, 30000, 60000];

const LANDING_PAGE_ID_PATTERN = /^[a-z0-9-]+$/;

const isValidLandingPageId = (value) =>
  typeof value === "string" && LANDING_PAGE_ID_PATTERN.test(value.trim());

const isValidRefreshInterval = (value) =>
  Number.isInteger(value) && ALLOWED_AUTO_REFRESH_INTERVALS.includes(value);

const parseStoredRecord = (rawValue) => {
  const parsed = JSON.parse(rawValue);
  if (!parsed || typeof parsed !== "object") {
    return null;
  }
  return parsed;
};

const sanitizeSettings = (candidate) => {
  const next = { ...DEFAULT_UI_SETTINGS };

  if (candidate && typeof candidate === "object") {
    if (isValidLandingPageId(candidate.defaultLandingPage)) {
      next.defaultLandingPage = candidate.defaultLandingPage;
    }
    if (isValidRefreshInterval(candidate.autoRefreshIntervalMs)) {
      next.autoRefreshIntervalMs = candidate.autoRefreshIntervalMs;
    }
  }

  return next;
};

export const readUiSettings = () => {
  try {
    const raw = window.localStorage.getItem(UI_SETTINGS_STORAGE_KEY);
    if (!raw) {
      return { ...DEFAULT_UI_SETTINGS };
    }

    const parsedRecord = parseStoredRecord(raw);
    if (!parsedRecord) {
      return { ...DEFAULT_UI_SETTINGS };
    }

    const candidateSettings =
      parsedRecord.version === UI_SETTINGS_VERSION &&
      parsedRecord.settings &&
      typeof parsedRecord.settings === "object"
        ? parsedRecord.settings
        : parsedRecord;

    return sanitizeSettings(candidateSettings);
  } catch (_error) {
    return { ...DEFAULT_UI_SETTINGS };
  }
};

export const writeUiSettings = (settings) => {
  const sanitized = sanitizeSettings(settings);
  const payload = JSON.stringify({
    version: UI_SETTINGS_VERSION,
    settings: sanitized,
  });

  try {
    window.localStorage.setItem(UI_SETTINGS_STORAGE_KEY, payload);
  } catch (_error) {
    // localStorage failures should not break app rendering.
  }

  return sanitized;
};
