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
      defaultLandingPage: "threat-hunt",
      autoRefreshIntervalMs: DEFAULT_UI_SETTINGS.autoRefreshIntervalMs,
    });
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
