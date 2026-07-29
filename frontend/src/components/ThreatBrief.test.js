import { render, screen } from "@testing-library/react";

import ThreatBrief, { buildThreatBriefModel } from "./ThreatBrief";

const alerts = [
  { alert_id: 1, alert_type: "low_noise", severity: "low", source_ip: "198.51.100.10", status: "open" },
  { alert_id: 2, alert_type: "critical_login", severity: "critical", source_ip: "203.0.113.10", status: "open" },
  { alert_id: 3, alert_type: "application_exception", severity: "medium", source_ip: "203.0.113.10", status: "failed" },
];

test("buildThreatBriefModel derives deterministic priorities without fabricating unavailable fields", () => {
  const model = buildThreatBriefModel({ alerts, metrics: { totalAlerts: 3 } });

  expect(model.sections.find((section) => section.id === "highest-priority")).toEqual(
    expect.objectContaining({ value: "critical_login" })
  );
  expect(model.sections.find((section) => section.id === "riskiest-source")).toEqual(
    expect.objectContaining({ value: "203.0.113.10" })
  );
  expect(model.sections.find((section) => section.id === "pending-approvals")).toEqual(
    expect.objectContaining({ value: "Unavailable" })
  );
  expect(model.sections.find((section) => section.id === "recommended-next-action").value).toMatch(/critical_login/);
});

test("ThreatBrief renders populated and partial-error states", () => {
  const model = buildThreatBriefModel({ alerts, metrics: { totalAlerts: 3 }, sourceErrors: ["approvals"], stale: true });
  render(<ThreatBrief model={model} />);

  expect(screen.getByRole("region", { name: "Threat Brief" })).toBeInTheDocument();
  expect(screen.getByText("critical_login")).toBeInTheDocument();
  expect(screen.getByText(/Partial data loaded: approvals/)).toBeInTheDocument();
  expect(screen.getByText(/Showing stale briefing inputs/)).toBeInTheDocument();
});

test("ThreatBrief applies resilient wrapping styles for long values", () => {
  const longAlertType = "critical_login_from_extremely_long_source_identifier_without_breaks".repeat(3);
  const model = buildThreatBriefModel({
    alerts: [{ alert_id: 9, alert_type: longAlertType, severity: "critical", source_ip: "2001:db8:ffff:ffff:ffff:ffff:ffff:ffff", status: "open" }],
    metrics: { totalAlerts: 1 },
  });
  render(<ThreatBrief model={model} />);

  expect(screen.getByText(longAlertType)).toHaveStyle({
    overflowWrap: "anywhere",
    wordBreak: "break-word",
  });
});
