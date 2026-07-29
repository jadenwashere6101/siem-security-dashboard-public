import {
  buildDrawerSections,
  buildInvestigationContext,
  buildThreatStory,
} from "./investigationWorkflow";

test("buildInvestigationContext derives entities and detections from authoritative inputs", () => {
  const context = buildInvestigationContext({
    alert: { id: 7, alert_type: "failed_login_threshold", severity: "HIGH", source_ip: "203.0.113.5", source: "bank_app" },
    incident: { id: 3, title: "Credential attack", status: "open", priority: "P2" },
    timeline: [{ event_type: "alert_created", title: "Alert created", timestamp: "2026-01-01T00:00:00Z" }],
  });

  expect(context.entities).toEqual(expect.arrayContaining([
    { label: "Source IP", value: "203.0.113.5" },
    { label: "Alert ID", value: "7" },
    { label: "Incident ID", value: "3" },
  ]));
  expect(context.detections.map((item) => item.label)).toEqual(
    expect.arrayContaining(["failed_login_threshold", "alert_created"])
  );
});

test("buildDrawerSections renders explicit partial and unavailable states", () => {
  const context = buildInvestigationContext({});
  const sections = buildDrawerSections(context);

  expect(sections.find((section) => section.id === "timeline")).toEqual(
    expect.objectContaining({ status: "partial", value: "Timeline incomplete" })
  );
  expect(sections.find((section) => section.id === "alert-summary")).toEqual(
    expect.objectContaining({ status: "unavailable", value: "No alert selected" })
  );
});

test("buildThreatStory uses only supported progression data", () => {
  const emptyStory = buildThreatStory(buildInvestigationContext({
    alert: { id: 9, alert_type: "port_scan", source_ip: "203.0.113.9", severity: "MEDIUM" },
  }));
  expect(emptyStory.progression).toEqual([]);
  expect(emptyStory.progressionStatus).toBe("incomplete");
  expect(JSON.stringify(emptyStory)).not.toMatch(/spray|approval|resolution/i);

  const story = buildThreatStory(buildInvestigationContext({
    timeline: [
      { event_type: "alert_created", title: "Alert created", summary: "Detection fired", timestamp: "2026-01-02T00:00:00Z", source: "alert" },
      { event_type: "playbook_step_completed", title: "Playbook step", summary: "Notification simulated", timestamp: "2026-01-02T00:02:00Z", source: "playbook_execution" },
    ],
  }));
  expect(story.progression.map((item) => item.label)).toEqual(["Alert created", "Playbook step"]);
  expect(story.progression[0].source).toBe("alert");
});
