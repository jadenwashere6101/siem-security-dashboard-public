import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import TopBar from "./TopBar";
import { SIDEBAR_NAV_ID } from "./Sidebar";

test("calls onToggleCollapse when the hamburger button is clicked", async () => {
  const onToggleCollapse = jest.fn();

  render(
    <TopBar isCollapsed={false} onToggleCollapse={onToggleCollapse} title="SIEM Dashboard" />
  );

  await userEvent.click(screen.getByRole("button", { name: /toggle navigation/i }));

  expect(onToggleCollapse).toHaveBeenCalledTimes(1);
});

test("reflects expanded state via aria-expanded when not collapsed", () => {
  render(<TopBar isCollapsed={false} onToggleCollapse={() => {}} title="SIEM Dashboard" />);

  expect(screen.getByRole("button", { name: /toggle navigation/i })).toHaveAttribute(
    "aria-expanded",
    "true"
  );
});

test("reflects collapsed state via aria-expanded when collapsed", () => {
  render(<TopBar isCollapsed title="SIEM Dashboard" onToggleCollapse={() => {}} />);

  expect(screen.getByRole("button", { name: /toggle navigation/i })).toHaveAttribute(
    "aria-expanded",
    "false"
  );
});

test("hamburger button references the sidebar nav id via aria-controls", () => {
  render(<TopBar isCollapsed={false} onToggleCollapse={() => {}} title="SIEM Dashboard" />);

  expect(screen.getByRole("button", { name: /toggle navigation/i })).toHaveAttribute(
    "aria-controls",
    SIDEBAR_NAV_ID
  );
});

test("renders the provided title", () => {
  render(<TopBar isCollapsed={false} onToggleCollapse={() => {}} title="SIEM Dashboard" />);

  expect(screen.getByRole("heading", { name: "SIEM Dashboard" })).toBeInTheDocument();
});

test("renders caller-supplied content in the right-side slot", () => {
  render(
    <TopBar isCollapsed={false} onToggleCollapse={() => {}} title="SIEM Dashboard">
      <button type="button">Log out</button>
    </TopBar>
  );

  expect(screen.getByRole("button", { name: "Log out" })).toBeInTheDocument();
});
