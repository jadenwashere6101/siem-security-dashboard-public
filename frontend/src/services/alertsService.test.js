import { buildAlertQuery, loadAlertRuleOptions } from "./alertsService";

test("buildAlertQuery includes rule filter with existing filters", () => {
  const query = buildAlertQuery({
    searchTerm: "failed",
    exactSourceIp: "8.8.8.8",
    exactTargetIp: "10.0.0.5",
    exactAlertId: 101,
    severityFilter: "high",
    statusFilter: "open",
    sourceFilter: "bank_app",
    ruleFilter: "failed_login_threshold",
    sortOption: "severity",
    operationalScope: "since_tuning",
    timelineRange: "24h",
    limit: 25,
    offset: 50,
  });

  expect(query).toContain("search=failed");
  expect(query).toContain("exact_source_ip=8.8.8.8");
  expect(query).toContain("exact_target_ip=10.0.0.5");
  expect(query).toContain("alert_id=101");
  expect(query).toContain("severity=high");
  expect(query).toContain("status=open");
  expect(query).toContain("source=bank_app");
  expect(query).toContain("rule_id=failed_login_threshold");
  expect(query).toContain("sort=severity");
  expect(query).toContain("operational_scope=since_tuning");
  expect(query).toContain("timeline_range=24h");
  expect(query).toContain("limit=25");
  expect(query).toContain("offset=50");
});

test("loadAlertRuleOptions reads safe alert rule metadata", async () => {
  global.fetch = jest.fn().mockResolvedValue({
    ok: true,
    json: () =>
      Promise.resolve({
        items: [{ rule_id: "failed_login_threshold", label: "Failed Login Threshold" }],
      }),
  });

  await expect(loadAlertRuleOptions()).resolves.toEqual([
    { rule_id: "failed_login_threshold", label: "Failed Login Threshold" },
  ]);
  expect(global.fetch).toHaveBeenCalledWith("/alerts/rule-options", {
    credentials: "include",
  });
});
