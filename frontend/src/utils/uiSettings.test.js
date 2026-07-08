import {
  ALLOWED_AUTO_REFRESH_INTERVALS,
  DEFAULT_UI_SETTINGS,
  UI_SETTINGS_STORAGE_KEY,
  readUiSettings,
  writeUiSettings,
} from "./uiSettings";

describe("uiSettings", () => {
  beforeEach(() => {
    window.localStorage.clear();
    jest.restoreAllMocks();
  });

  test("returns defaults when localStorage is missing", () => {
    expect(readUiSettings()).toEqual(DEFAULT_UI_SETTINGS);
  });

  test("returns defaults when localStorage has malformed JSON", () => {
    window.localStorage.setItem(UI_SETTINGS_STORAGE_KEY, "{not-json");
    expect(readUiSettings()).toEqual(DEFAULT_UI_SETTINGS);
  });

  test("falls back to defaults when stored values are invalid", () => {
    window.localStorage.setItem(
      UI_SETTINGS_STORAGE_KEY,
      JSON.stringify({
        version: 1,
        settings: {
          defaultLandingPage: "###",
          autoRefreshIntervalMs: 12345,
        },
      })
    );

    expect(readUiSettings()).toEqual(DEFAULT_UI_SETTINGS);
  });

  test("merges partially valid settings with defaults", () => {
    window.localStorage.setItem(
      UI_SETTINGS_STORAGE_KEY,
      JSON.stringify({
        version: 1,
        settings: {
          defaultLandingPage: "threat-hunt",
          autoRefreshIntervalMs: 12345,
          unknownFutureKey: true,
        },
      })
    );

    expect(readUiSettings()).toEqual({
      ...DEFAULT_UI_SETTINGS,
      defaultLandingPage: "threat-hunt",
      autoRefreshIntervalMs: DEFAULT_UI_SETTINGS.autoRefreshIntervalMs,
    });
  });

  test("recovers malformed display settings key-by-key", () => {
    window.localStorage.setItem(
      UI_SETTINGS_STORAGE_KEY,
      JSON.stringify({
        version: 1,
        settings: {
          defaultLandingPage: "dashboard",
          autoRefreshIntervalMs: 5000,
          display: {
            timezoneMode: "utc",
            timestampFormat: "bad",
            rowsPerPage: 25,
            defaultLiveLogsTab: "json",
            severityColorPreset: "highContrast",
            columnVisibility: {
              alertsTable: {
                id: false,
                message: false,
              },
            },
            liveLogHighlightRules: [
              { target: "severity", value: "high", treatment: "border" },
              { target: "bad", value: "x", treatment: "border" },
            ],
          },
        },
      })
    );

    const parsed = readUiSettings();
    expect(parsed.display.timezoneMode).toBe("utc");
    expect(parsed.display.timestampFormat).toBe(DEFAULT_UI_SETTINGS.display.timestampFormat);
    expect(parsed.display.rowsPerPage).toBe(25);
    expect(parsed.display.defaultLiveLogsTab).toBe("json");
    expect(parsed.display.severityColorPreset).toBe("highContrast");
    expect(parsed.display.columnVisibility.alertsTable.id).toBe(true);
    expect(parsed.display.columnVisibility.alertsTable.message).toBe(false);
    expect(parsed.display.liveLogHighlightRules).toEqual([
      { target: "severity", value: "high", treatment: "border" },
    ]);
  });

  test("handles localStorage read/write exceptions safely", () => {
    const getItemSpy = jest.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("read failed");
    });
    expect(readUiSettings()).toEqual(DEFAULT_UI_SETTINGS);
    getItemSpy.mockRestore();

    const setItemSpy = jest.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("write failed");
    });
    expect(() =>
      writeUiSettings({
        defaultLandingPage: "dashboard",
        autoRefreshIntervalMs: ALLOWED_AUTO_REFRESH_INTERVALS[0],
      })
    ).not.toThrow();
    setItemSpy.mockRestore();
  });
});
