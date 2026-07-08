import { formatTimestamp } from "./displayFormatting";

describe("displayFormatting", () => {
  test("formats with defaults when settings missing", () => {
    const value = formatTimestamp("2026-07-08T12:30:00Z");
    expect(value).toContain("2026");
  });

  test("supports UTC and 12-hour format", () => {
    const value = formatTimestamp(
      "2026-07-08T12:30:00Z",
      { timezoneMode: "utc", timestampFormat: "12h" },
      "N/A"
    );
    expect(value).toMatch(/UTC/);
  });

  test("returns fallback for invalid timestamp", () => {
    expect(formatTimestamp("bad-date", { timezoneMode: "local", timestampFormat: "24h" }, "N/A")).toBe(
      "N/A"
    );
  });
});
