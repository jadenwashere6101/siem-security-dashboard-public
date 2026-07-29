import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import InvestigationDrawer from "./InvestigationDrawer";

test("InvestigationDrawer renders alert context, supports private actions, and closes with Escape", async () => {
  const onClose = jest.fn();
  const onPinAlert = jest.fn();
  const onCreateInvestigation = jest.fn();
  render(
    <>
      <button type="button">Before</button>
      <InvestigationDrawer
        open
        onClose={onClose}
        alert={{ id: 7, alert_type: "failed_login_threshold", severity: "HIGH", source_ip: "203.0.113.7", status: "open" }}
        timeline={[{ event_type: "alert_created", title: "Alert created", summary: "Detection fired", timestamp: "2026-01-01T00:00:00Z" }]}
        workspace={{ evidence: [{ id: 1, label: "Primary alert", referenced_object_type: "alert", referenced_object_id: "7" }] }}
        onPinAlert={onPinAlert}
        onCreateInvestigation={onCreateInvestigation}
      />
    </>
  );

  expect(screen.getByRole("dialog", { name: "Investigation Drawer" })).toBeInTheDocument();
  expect(screen.getByText("Alert #7")).toBeInTheDocument();
  expect(screen.getByRole("region", { name: "Threat Story" })).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "Pin alert to analyst workspace" }));
  expect(onPinAlert).toHaveBeenCalledWith(expect.objectContaining({ id: 7 }));

  await userEvent.click(screen.getByRole("button", { name: "Save investigation state" }));
  expect(onCreateInvestigation).toHaveBeenCalled();

  await userEvent.keyboard("{Escape}");
  expect(onClose).toHaveBeenCalled();
});

test("InvestigationDrawer renders partial states without fabricating evidence", () => {
  render(<InvestigationDrawer open onClose={() => {}} />);
  expect(screen.getByText("No alert selected")).toBeInTheDocument();
  expect(screen.getByText("Timeline incomplete")).toBeInTheDocument();
  expect(screen.queryByText(/spray/i)).not.toBeInTheDocument();
});
