import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import Sidebar, { SIDEBAR_NAV_ID } from "./Sidebar";
import { sectionsConfig } from "../utils/sectionsConfig";

const mockSections = [
  { id: "alpha", label: "Alpha", group: "Overview", visibleWhen: () => true },
  {
    id: "beta",
    label: "Beta",
    group: "Overview",
    visibleWhen: (roleFlags) => !!roleFlags.isAdmin,
  },
  { id: "gamma", label: "Gamma", group: "Admin", visibleWhen: () => true },
];

test("renders only sections whose visibleWhen returns true for the given roleFlags", () => {
  render(
    <Sidebar
      sections={mockSections}
      roleFlags={{ isAdmin: false }}
      activeSectionId="alpha"
      onNavigate={() => {}}
    />
  );

  expect(screen.getByRole("button", { name: "Alpha" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Gamma" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Beta" })).not.toBeInTheDocument();
});

test("renders a previously hidden section once roleFlags grant visibility", () => {
  render(
    <Sidebar
      sections={mockSections}
      roleFlags={{ isAdmin: true }}
      activeSectionId="alpha"
      onNavigate={() => {}}
    />
  );

  expect(screen.getByRole("button", { name: "Beta" })).toBeInTheDocument();
});

test("groups visible sections by their group field with an accessible group label", () => {
  render(
    <Sidebar
      sections={mockSections}
      roleFlags={{ isAdmin: true }}
      activeSectionId="alpha"
      onNavigate={() => {}}
    />
  );

  expect(screen.getByRole("group", { name: "Overview" })).toBeInTheDocument();
  expect(screen.getByRole("group", { name: "Admin" })).toBeInTheDocument();
});

test("marks the active section with a visual highlight and aria-current", () => {
  render(
    <Sidebar
      sections={mockSections}
      roleFlags={{ isAdmin: true }}
      activeSectionId="beta"
      onNavigate={() => {}}
    />
  );

  expect(screen.getByRole("button", { name: "Beta" })).toHaveAttribute(
    "aria-current",
    "page"
  );
  expect(screen.getByRole("button", { name: "Alpha" })).not.toHaveAttribute(
    "aria-current"
  );
});

test("calls onNavigate with the clicked section's id", async () => {
  const onNavigate = jest.fn();

  render(
    <Sidebar
      sections={mockSections}
      roleFlags={{ isAdmin: true }}
      activeSectionId="alpha"
      onNavigate={onNavigate}
    />
  );

  await userEvent.click(screen.getByRole("button", { name: "Gamma" }));

  expect(onNavigate).toHaveBeenCalledTimes(1);
  expect(onNavigate).toHaveBeenCalledWith("gamma");
});

test("does not render hidden nav buttons when collapsed", () => {
  render(
    <Sidebar
      sections={mockSections}
      roleFlags={{ isAdmin: true }}
      activeSectionId="alpha"
      onNavigate={() => {}}
      isCollapsed
    />
  );

  expect(screen.queryByRole("button", { name: "Alpha" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Beta" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Gamma" })).not.toBeInTheDocument();
});

test("renders a bottom status/version panel from props", () => {
  render(
    <Sidebar
      sections={mockSections}
      roleFlags={{ isAdmin: true }}
      activeSectionId="alpha"
      onNavigate={() => {}}
      statusLabel="Operational"
      versionLabel="v1.2.3"
    />
  );

  expect(screen.getByText("Operational")).toBeInTheDocument();
  expect(screen.getByText("v1.2.3")).toBeInTheDocument();
});

test("footer status and version text carry a title attribute with their full content", () => {
  render(
    <Sidebar
      sections={mockSections}
      roleFlags={{ isAdmin: true }}
      activeSectionId="alpha"
      onNavigate={() => {}}
      statusLabel="Operational"
      versionLabel="v1.2.3"
    />
  );

  expect(screen.getByText("Operational")).toHaveAttribute("title", "Operational");
  expect(screen.getByText("v1.2.3")).toHaveAttribute("title", "v1.2.3");
});

test("renders no broken footer row when statusLabel and versionLabel are omitted", () => {
  render(
    <Sidebar
      sections={mockSections}
      roleFlags={{ isAdmin: true }}
      activeSectionId="alpha"
      onNavigate={() => {}}
    />
  );

  expect(screen.queryByText("Operational")).not.toBeInTheDocument();
  expect(screen.getByTestId("sidebar-status-panel").querySelector("[title]")).toBeNull();
});

test("hides nav groups entirely when collapsed", () => {
  render(
    <Sidebar
      sections={mockSections}
      roleFlags={{ isAdmin: true }}
      activeSectionId="alpha"
      onNavigate={() => {}}
      isCollapsed
    />
  );

  expect(screen.queryByText("Overview")).not.toBeInTheDocument();
  expect(screen.queryByText("Admin")).not.toBeInTheDocument();
  expect(screen.queryByRole("group", { name: "Overview" })).not.toBeInTheDocument();
  expect(screen.queryByRole("group", { name: "Admin" })).not.toBeInTheDocument();
});

test("collapsed sidebar has no invisible navigation click targets", async () => {
  const onNavigate = jest.fn();

  render(
    <Sidebar
      sections={mockSections}
      roleFlags={{ isAdmin: true }}
      activeSectionId="alpha"
      onNavigate={onNavigate}
      isCollapsed
    />
  );

  await userEvent.click(screen.getByRole("navigation", { name: "Primary" }));

  expect(onNavigate).not.toHaveBeenCalled();
});

test("locks the sidebar to a fixed width that cannot shrink or grow from sibling content", () => {
  const { container, rerender } = render(
    <Sidebar
      sections={mockSections}
      roleFlags={{ isAdmin: true }}
      activeSectionId="alpha"
      onNavigate={() => {}}
    />
  );

  const aside = container.querySelector("aside");
  expect(aside).toHaveStyle({ flex: "0 0 auto", width: "256px" });

  rerender(
    <Sidebar
      sections={mockSections}
      roleFlags={{ isAdmin: true }}
      activeSectionId="alpha"
      onNavigate={() => {}}
      isCollapsed
    />
  );

  expect(aside).toHaveStyle({
    flex: "0 0 auto",
    width: "0px",
    borderRight: "none",
  });
});

test("sidebar width does not vary with which section is active", () => {
  const { container, rerender } = render(
    <Sidebar
      sections={mockSections}
      roleFlags={{ isAdmin: true }}
      activeSectionId="alpha"
      onNavigate={() => {}}
    />
  );

  const aside = container.querySelector("aside");
  const widthWithAlphaActive = aside.style.width;

  rerender(
    <Sidebar
      sections={mockSections}
      roleFlags={{ isAdmin: true }}
      activeSectionId="gamma"
      onNavigate={() => {}}
    />
  );

  expect(aside.style.width).toBe(widthWithAlphaActive);
});

test("renders LIVE LOGS group from sections config for analysts", () => {
  render(
    <Sidebar
      sections={sectionsConfig}
      roleFlags={{ isSuperAdmin: false, isAnalyst: true, canTakeAlertActions: true }}
      activeSectionId="live-logs-pfsense"
      onNavigate={() => {}}
    />
  );

  expect(screen.getByRole("group", { name: "live logs" })).toBeInTheDocument();
  expect(screen.getByText("live logs")).toBeInTheDocument();
  for (const label of ["Honeypot", "Bank App", "pfSense", "NGINX", "Azure", "OTEL"]) {
    expect(screen.getByRole("button", { name: label })).toBeInTheDocument();
  }
});

test("does not render the status panel or decorative indicator when collapsed", () => {
  const { container } = render(
    <Sidebar
      sections={mockSections}
      roleFlags={{ isAdmin: true }}
      activeSectionId="alpha"
      onNavigate={() => {}}
      isCollapsed
      statusLabel="Operational"
      versionLabel="v1.2.3"
    />
  );

  expect(screen.queryByText("Operational")).not.toBeInTheDocument();
  expect(screen.queryByText("v1.2.3")).not.toBeInTheDocument();
  expect(screen.queryByTestId("sidebar-status-panel")).not.toBeInTheDocument();
  expect(container.querySelector('[title="Operational · v1.2.3"]')).not.toBeInTheDocument();
});

test("renders no footer panel when collapsed with no status/version props", () => {
  render(
    <Sidebar
      sections={mockSections}
      roleFlags={{ isAdmin: true }}
      activeSectionId="alpha"
      onNavigate={() => {}}
      isCollapsed
    />
  );

  expect(screen.queryByTestId("sidebar-status-panel")).not.toBeInTheDocument();
});

test("renders a semantic primary nav landmark matching the exposed nav id", () => {
  render(
    <Sidebar
      sections={mockSections}
      roleFlags={{ isAdmin: true }}
      activeSectionId="alpha"
      onNavigate={() => {}}
    />
  );

  const nav = screen.getByRole("navigation", { name: "Primary" });
  expect(nav).toHaveAttribute("id", SIDEBAR_NAV_ID);
});
