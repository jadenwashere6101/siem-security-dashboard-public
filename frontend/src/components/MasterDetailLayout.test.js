import React, { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import {
  MasterDetailLayout,
  MasterDetailMaster,
  MasterDetailPane,
  useMasterDetailFocus,
} from "./MasterDetailLayout";

function Harness() {
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
      </MasterDetailPane>
    </MasterDetailLayout>
  );
}

test("opens a labeled detail region, focuses its heading, and restores the trigger", async () => {
  render(<Harness />);

  const trigger = screen.getByRole("button", { name: "View record" });
  await userEvent.click(trigger);

  expect(screen.getByLabelText("Test records and detail")).toHaveClass(
    "master-detail-layout--open"
  );
  expect(screen.getByRole("complementary", { name: "Test detail" })).toBeVisible();
  expect(screen.getByRole("heading", { name: "Record detail" })).toHaveFocus();

  await userEvent.click(screen.getByRole("button", { name: "Close detail" }));

  expect(trigger).toHaveFocus();
  expect(screen.getByLabelText("Test records and detail")).not.toHaveClass(
    "master-detail-layout--open"
  );
});
