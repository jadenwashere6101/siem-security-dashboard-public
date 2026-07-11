import React, { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import fs from "fs";
import path from "path";

import {
  MasterDetailLayout,
  MasterDetailMaster,
  MasterDetailPane,
  useMasterDetailFocus,
} from "./MasterDetailLayout";

function Harness({ detailMode = "ready" } = {}) {
  const [selected, setSelected] = useState(null);
  const { detailRef, rememberTrigger, restoreTriggerFocus } = useMasterDetailFocus(selected);

  return (
    <MasterDetailLayout detailOpen={selected !== null} ariaLabel="Test records and detail">
      <MasterDetailMaster ariaLabel="Test records">
        <button
          type="button"
          onClick={(event) => {
            rememberTrigger(event.currentTarget);
            setSelected("record-1");
          }}
        >
          View record
        </button>
      </MasterDetailMaster>
      <MasterDetailPane ref={detailRef} ariaLabel="Test detail">
        {detailMode === "loading" ? (
          <p>Loading detail...</p>
        ) : detailMode === "error" ? (
          <div>
            <h3>Detail unavailable</h3>
            <p>Error loading detail: boom</p>
          </div>
        ) : (
          <>
            <h3>Record detail</h3>
            <button
              type="button"
              onClick={() => {
                restoreTriggerFocus();
                setSelected(null);
              }}
            >
              Close detail
            </button>
          </>
        )}
      </MasterDetailPane>
    </MasterDetailLayout>
  );
}

test("opens a labeled detail region, focuses its heading, and restores the trigger", async () => {
  render(<Harness />);

  const trigger = screen.getByRole("button", { name: "View record" });
  await userEvent.click(trigger);

  const layout = screen.getByLabelText("Test records and detail");
  expect(layout).toHaveClass("master-detail-layout--open");
  expect(layout.querySelector(".master-detail-layout__master")).toBeInTheDocument();
  expect(screen.getByRole("complementary", { name: "Test detail" })).toBeVisible();
  expect(screen.getByRole("heading", { name: "Record detail" })).toHaveFocus();

  await userEvent.click(screen.getByRole("button", { name: "Close detail" }));

  expect(trigger).toHaveFocus();
  expect(screen.getByLabelText("Test records and detail")).not.toHaveClass(
    "master-detail-layout--open"
  );
});

test("detail pane follows the master region in DOM order for stacked narrow layouts", async () => {
  render(<Harness />);
  await userEvent.click(screen.getByRole("button", { name: "View record" }));

  const layout = screen.getByLabelText("Test records and detail");
  const master = layout.querySelector(".master-detail-layout__master");
  const detail = layout.querySelector(".master-detail-layout__detail");
  expect(master.compareDocumentPosition(detail) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

  const css = fs.readFileSync(path.join(__dirname, "MasterDetailLayout.css"), "utf8");
  expect(css).toMatch(/@media \(max-width: 1100px\)/);
  expect(css).toMatch(/grid-template-columns: minmax\(0, 1fr\);/);
});

test("loading and error detail states still open the adjacent pane without crashing", async () => {
  const { unmount } = render(<Harness detailMode="loading" />);
  await userEvent.click(screen.getByRole("button", { name: "View record" }));
  expect(screen.getByText("Loading detail...")).toBeVisible();
  expect(screen.getByRole("complementary", { name: "Test detail" })).toHaveFocus();
  unmount();

  render(<Harness detailMode="error" />);
  await userEvent.click(screen.getByRole("button", { name: "View record" }));
  expect(screen.getByText(/Error loading detail/i)).toBeVisible();
  expect(screen.getByRole("heading", { name: "Detail unavailable" })).toHaveFocus();
});
