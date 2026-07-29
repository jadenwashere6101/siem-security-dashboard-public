import { render, screen, within } from "@testing-library/react";

import GroupedOperationsFeed from "./GroupedOperationsFeed";
import { buildOperationalFeedEntries, groupOperationalFeedEntries } from "./groupedOperationsFeedModel";

const data = {
  incidents: [{ id: 1, title: "Incident alpha", severity: "high", status: "open", created_at: "2026-01-01T00:05:00Z" }],
  executions: [{ id: 2, playbook_id: "containment", status: "failed", created_at: "2026-01-01T00:04:00Z" }],
  approvals: [{ id: 3, action: "block_ip", status: "pending", created_at: "2026-01-01T00:03:00Z" }],
  notifications: [{ id: 4, adapter_name: "slack", status: "failed", mode: "simulation", created_at: "2026-01-01T00:02:00Z" }],
  queueItems: [{ id: 5, playbook_id: "triage", status: "running", created_at: "2026-01-01T00:01:00Z" }],
};

test("normalizes and groups supported operational feed categories", () => {
  const entries = buildOperationalFeedEntries(data);
  const groups = groupOperationalFeedEntries(entries);

  expect(entries.map((entry) => entry.source)).toEqual(
    expect.arrayContaining(["Incident", "Playbook", "Approval", "Notification", "Worker"])
  );
  expect(groups.find((group) => group.id === "Incident").items).toHaveLength(1);
  expect(groups.find((group) => group.id === "Worker").items).toHaveLength(1);
});

test("renders grouped feed populated, empty, loading, and error states", () => {
  const entries = buildOperationalFeedEntries(data);
  const { rerender } = render(
    <GroupedOperationsFeed entries={entries} formatTime={() => "now"} />
  );

  expect(screen.getByRole("heading", { name: "Incident" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Playbook" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Approval" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Notification" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Worker" })).toBeInTheDocument();
  expect(within(screen.getByLabelText("Grouped live operations feed")).getByText("Incident alpha")).toBeInTheDocument();

  rerender(<GroupedOperationsFeed entries={[]} />);
  expect(screen.getByText("No recent operational activity found.")).toBeInTheDocument();

  rerender(<GroupedOperationsFeed entries={[]} loading />);
  expect(screen.getByText("Loading activity...")).toBeInTheDocument();

  rerender(<GroupedOperationsFeed entries={[]} error="feed unavailable" />);
  expect(screen.getByText("feed unavailable")).toBeInTheDocument();
});
