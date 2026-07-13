import { buildPlainLanguageSummary, operatorsForField, PLAYGROUND_MITRE_PATTERN } from "./detectionSimulatorPlaygroundContract";

describe("operatorsForField", () => {
  test("returns numeric operators for destination_port and http_status", () => {
    expect(operatorsForField("destination_port")).toContain("greater_than");
    expect(operatorsForField("http_status")).toContain("greater_than_or_equal");
  });

  test("returns string operators for other fields", () => {
    expect(operatorsForField("source_ip")).toEqual(
      expect.arrayContaining(["equals", "contains", "starts_with", "ends_with"])
    );
    expect(operatorsForField("source_ip")).not.toContain("greater_than");
  });
});

describe("PLAYGROUND_MITRE_PATTERN", () => {
  test("accepts Txxxx and Txxxx.xxx", () => {
    expect(PLAYGROUND_MITRE_PATTERN.test("T1110")).toBe(true);
    expect(PLAYGROUND_MITRE_PATTERN.test("T1110.001")).toBe(true);
  });

  test("rejects malformed technique ids", () => {
    expect(PLAYGROUND_MITRE_PATTERN.test("1110")).toBe(false);
    expect(PLAYGROUND_MITRE_PATTERN.test("DROP TABLE alerts")).toBe(false);
    expect(PLAYGROUND_MITRE_PATTERN.test("T11")).toBe(false);
  });
});

describe("buildPlainLanguageSummary", () => {
  test("prompts for required fields when the builder is incomplete", () => {
    expect(buildPlainLanguageSummary({})).toMatch(/Select a source/i);
  });

  test("describes a complete temporary rule in plain language without evaluating any event", () => {
    const summary = buildPlainLanguageSummary({
      source: "bank_app",
      eventType: "failed_login",
      conditionField: "username",
      conditionOperator: "equals",
      conditionValue: "alice",
      groupByField: "source_ip",
      threshold: "3",
      windowMinutes: "15",
      severity: "high",
      mitreTechniqueId: "T1110",
    });
    expect(summary).toMatch(/username equals "alice"/);
    expect(summary).toMatch(/event type equals "failed_login"/);
    expect(summary).toMatch(/GROUP BY source_ip/);
    expect(summary).toMatch(/high-severity/);
    expect(summary).toMatch(/3 or more matching event\(s\)/);
    expect(summary).toMatch(/within 15 minute\(s\)/);
    expect(summary).toMatch(/T1110/);
  });

  test("renders in_list values as a joined list", () => {
    const summary = buildPlainLanguageSummary({
      source: "pfsense",
      conditionField: "destination_port",
      conditionOperator: "in_list",
      conditionValue: [22, 3389],
      groupByField: "source_ip",
      threshold: "5",
      windowMinutes: "10",
      severity: "medium",
    });
    expect(summary).toMatch(/is one of "22, 3389"/);
  });
});
