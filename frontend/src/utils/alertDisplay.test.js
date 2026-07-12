import { getSourceBadgeMeta } from "./alertDisplay";
import { getSourceBadgeMeta as getThreatHuntSourceBadgeMeta } from "./threatHuntDisplay";

describe("source badge labels", () => {
  test.each([
    ["honeypot", "Honeypot"],
    ["bank_app", "App / Bank"],
    ["nginx", "Web Log"],
    ["azure_insights", "Azure"],
    ["opentelemetry", "OTEL"],
    ["pfsense", "pfSense"],
  ])("maps %s to %s", (source, expectedLabel) => {
    expect(getSourceBadgeMeta(source, "firewall").label).toBe(expectedLabel);
  });

  test.each([
    ["honeypot", "#60a5fa", "rgba(96, 165, 250, 0.10)", "1px solid rgba(96, 165, 250, 0.28)"],
    ["bank_app", "#93c5fd", "rgba(59, 130, 246, 0.10)", "1px solid rgba(59, 130, 246, 0.28)"],
    ["pfsense", "#d8b4fe", "rgba(192, 132, 252, 0.10)", "1px solid rgba(192, 132, 252, 0.28)"],
    ["nginx", "#fbbf24", "rgba(251, 191, 36, 0.10)", "1px solid rgba(251, 191, 36, 0.28)"],
    ["azure_insights", "#67e8f9", "rgba(103, 232, 249, 0.10)", "1px solid rgba(103, 232, 249, 0.26)"],
    ["opentelemetry", "#c4b5fd", "rgba(196, 181, 253, 0.10)", "1px solid rgba(196, 181, 253, 0.26)"],
    ["legacy", "#c9d1d9", "rgba(148, 163, 184, 0.10)", "1px solid rgba(148, 163, 184, 0.22)"],
  ])("uses the expected palette for %s", (source, color, backgroundColor, border) => {
    expect(getSourceBadgeMeta(source).style).toEqual({ color, backgroundColor, border });
  });

  test("keeps unknown sources on the legacy fallback", () => {
    expect(getSourceBadgeMeta("legacy")).toMatchObject({
      label: "Unknown",
      subLabel: "Legacy",
    });
  });

  test("uses the shared source badge mapping in threat hunt", () => {
    ["honeypot", "pfsense"].forEach((source) => {
      expect(getThreatHuntSourceBadgeMeta(source)).toEqual(getSourceBadgeMeta(source));
    });

    expect(getThreatHuntSourceBadgeMeta("legacy")).toMatchObject({
      label: "Unknown",
      style: {
        color: "#c9d1d9",
        backgroundColor: "rgba(148, 163, 184, 0.10)",
      },
    });
  });
});
