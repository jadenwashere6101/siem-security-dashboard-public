export const UI_SETTINGS_STORAGE_KEY = "siem.ui.settings.v1";
export const UI_SETTINGS_VERSION = 1;

export const DEFAULT_UI_SETTINGS = {
  defaultLandingPage: "dashboard",
  autoRefreshIntervalMs: 5000,
  display: {
    timezoneMode: "local",
    timestampFormat: "24h",
    rowsPerPage: "all",
    liveLogsFontSize: "medium",
    defaultLiveLogsTab: "eventFeed",
    severityColorPreset: "default",
    columnVisibility: {
      alertsTable: {
        id: true,
        type: true,
        source: true,
        sourceIp: true,
        behavior: true,
        severity: true,
        message: true,
        createdAt: true,
        action: true,
      },
      liveLogsTable: {
        id: true,
        type: true,
        severity: true,
        sourceIp: true,
        app: true,
        message: true,
        created: true,
      },
      incidentsTable: {
        id: true,
        title: true,
        severity: true,
        priority: true,
        status: true,
        sourceIp: true,
        created: true,
      },
    },
    liveLogHighlightRules: [],
  },
};

export const ALLOWED_AUTO_REFRESH_INTERVALS = [0, 5000, 10000, 30000, 60000];
export const ALLOWED_TIMEZONE_MODES = ["local", "utc"];
export const ALLOWED_TIMESTAMP_FORMATS = ["12h", "24h"];
export const ALLOWED_ROWS_PER_PAGE_VALUES = ["all", 10, 25, 50, 100];
export const ALLOWED_LIVE_LOGS_FONT_SIZES = ["small", "medium", "large"];
export const ALLOWED_LIVE_LOGS_TABS = ["eventFeed", "rawLog", "json"];
export const ALLOWED_SEVERITY_COLOR_PRESETS = ["default", "colorblindSafe", "highContrast"];
export const ALLOWED_HIGHLIGHT_TARGETS = ["severity", "type"];
export const ALLOWED_HIGHLIGHT_TREATMENTS = ["border", "background", "glow"];

const LANDING_PAGE_ID_PATTERN = /^[a-z0-9-]+$/;

const isValidLandingPageId = (value) =>
  typeof value === "string" && LANDING_PAGE_ID_PATTERN.test(value.trim());

const isValidRefreshInterval = (value) =>
  Number.isInteger(value) && ALLOWED_AUTO_REFRESH_INTERVALS.includes(value);

const isStringEnum = (value, allowed) => typeof value === "string" && allowed.includes(value);

const isValidRowsPerPage = (value) =>
  value === "all" || (Number.isInteger(value) && ALLOWED_ROWS_PER_PAGE_VALUES.includes(value));

const sanitizeColumnVisibilityMap = (candidateMap, fallbackMap, idKey) => {
  const next = { ...fallbackMap };
  if (!candidateMap || typeof candidateMap !== "object") {
    return next;
  }

  Object.keys(fallbackMap).forEach((key) => {
    const incoming = candidateMap[key];
    if (typeof incoming === "boolean") {
      next[key] = incoming;
    }
  });

  next[idKey] = true;
  return next;
};

const sanitizeDisplaySettings = (candidateDisplay) => {
  const fallback = DEFAULT_UI_SETTINGS.display;
  const next = {
    ...fallback,
    columnVisibility: {
      alertsTable: { ...fallback.columnVisibility.alertsTable },
      liveLogsTable: { ...fallback.columnVisibility.liveLogsTable },
      incidentsTable: { ...fallback.columnVisibility.incidentsTable },
    },
    liveLogHighlightRules: [],
  };

  if (!candidateDisplay || typeof candidateDisplay !== "object") {
    return next;
  }

  if (isStringEnum(candidateDisplay.timezoneMode, ALLOWED_TIMEZONE_MODES)) {
    next.timezoneMode = candidateDisplay.timezoneMode;
  }
  if (isStringEnum(candidateDisplay.timestampFormat, ALLOWED_TIMESTAMP_FORMATS)) {
    next.timestampFormat = candidateDisplay.timestampFormat;
  }
  if (isValidRowsPerPage(candidateDisplay.rowsPerPage)) {
    next.rowsPerPage = candidateDisplay.rowsPerPage;
  }
  if (isStringEnum(candidateDisplay.liveLogsFontSize, ALLOWED_LIVE_LOGS_FONT_SIZES)) {
    next.liveLogsFontSize = candidateDisplay.liveLogsFontSize;
  }
  if (isStringEnum(candidateDisplay.defaultLiveLogsTab, ALLOWED_LIVE_LOGS_TABS)) {
    next.defaultLiveLogsTab = candidateDisplay.defaultLiveLogsTab;
  }
  if (isStringEnum(candidateDisplay.severityColorPreset, ALLOWED_SEVERITY_COLOR_PRESETS)) {
    next.severityColorPreset = candidateDisplay.severityColorPreset;
  }

  const incomingColumnVisibility = candidateDisplay.columnVisibility;
  if (incomingColumnVisibility && typeof incomingColumnVisibility === "object") {
    next.columnVisibility.alertsTable = sanitizeColumnVisibilityMap(
      incomingColumnVisibility.alertsTable,
      fallback.columnVisibility.alertsTable,
      "id"
    );
    next.columnVisibility.liveLogsTable = sanitizeColumnVisibilityMap(
      incomingColumnVisibility.liveLogsTable,
      fallback.columnVisibility.liveLogsTable,
      "id"
    );
    next.columnVisibility.incidentsTable = sanitizeColumnVisibilityMap(
      incomingColumnVisibility.incidentsTable,
      fallback.columnVisibility.incidentsTable,
      "id"
    );
  }

  if (Array.isArray(candidateDisplay.liveLogHighlightRules)) {
    next.liveLogHighlightRules = candidateDisplay.liveLogHighlightRules
      .filter(
        (rule) =>
          rule &&
          typeof rule === "object" &&
          isStringEnum(rule.target, ALLOWED_HIGHLIGHT_TARGETS) &&
          typeof rule.value === "string" &&
          rule.value.trim() &&
          isStringEnum(rule.treatment, ALLOWED_HIGHLIGHT_TREATMENTS)
      )
      .map((rule) => ({
        target: rule.target,
        value: rule.value.trim(),
        treatment: rule.treatment,
      }));
  }

  return next;
};

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
    next.display = sanitizeDisplaySettings(candidate.display);
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
