import { getSourceBadgeMeta } from "./alertDisplay";
import { getSourceBadgeMeta as getThreatHuntSourceBadgeMeta } from "./threatHuntDisplay";

describe("source badge labels", () => {
  test.each([
    ["bank_app", "App / Bank"],
    ["nginx", "Web Log"],
    ["azure_insights", "Azure"],
    ["opentelemetry", "OTEL"],
    ["pfsense", "pfSense"],
  ])("maps %s to %s", (source, expectedLabel) => {
    expect(getSourceBadgeMeta(source, "firewall").label).toBe(expectedLabel);
  });

  test("uses the shared source badge mapping in threat hunt", () => {
    expect(getThreatHuntSourceBadgeMeta("pfsense", "firewall")).toEqual(
      getSourceBadgeMeta("pfsense", "firewall")
    );
  });
});
