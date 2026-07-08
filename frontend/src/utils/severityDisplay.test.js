import { getSeverityBadgeStyle } from "./severityDisplay";

describe("severityDisplay", () => {
  test("returns default preset styles", () => {
    const style = getSeverityBadgeStyle("high", "default");
    expect(style).toEqual(
      expect.objectContaining({
        color: expect.any(String),
        backgroundColor: expect.any(String),
        border: expect.any(String),
      })
    );
  });

  test("returns colorblind preset styles", () => {
    const style = getSeverityBadgeStyle("critical", "colorblindSafe");
    expect(style).toEqual(expect.objectContaining({ color: "#f6d32d" }));
  });

  test("falls back for unknown values", () => {
    const style = getSeverityBadgeStyle("unknown-level", "highContrast");
    expect(style).toEqual(expect.objectContaining({ backgroundColor: "#495057" }));
  });
});
