import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import Sidebar, { SIDEBAR_NAV_ID } from "./Sidebar";

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

test("keeps each nav item's accessible name available when collapsed", () => {
  render(
    <Sidebar
      sections={mockSections}
      roleFlags={{ isAdmin: true }}
      activeSectionId="alpha"
      onNavigate={() => {}}
      isCollapsed
    />
  );

  expect(screen.getByRole("button", { name: "Alpha" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Beta" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Gamma" })).toBeInTheDocument();
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

test("hides group heading text when collapsed but keeps the accessible group label", () => {
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
  expect(screen.getByRole("group", { name: "Overview" })).toBeInTheDocument();
  expect(screen.getByRole("group", { name: "Admin" })).toBeInTheDocument();
});

test("shows a decorative glyph and a native tooltip on each nav item when collapsed", () => {
  render(
    <Sidebar
      sections={mockSections}
      roleFlags={{ isAdmin: true }}
      activeSectionId="alpha"
      onNavigate={() => {}}
      isCollapsed
    />
  );

  const alphaButton = screen.getByRole("button", { name: "Alpha" });
  expect(alphaButton).toHaveAttribute("title", "Alpha");

  const glyph = alphaButton.querySelector('[aria-hidden="true"]');
  expect(glyph).not.toBeNull();
  expect(glyph).toHaveTextContent("A");
});

test("renders no clipped footer text when collapsed, using a decorative status indicator instead", () => {
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
  expect(container.querySelector('[title="Operational · v1.2.3"]')).toBeInTheDocument();
});

test("renders no footer indicator when collapsed with no status/version props", () => {
  render(
    <Sidebar
      sections={mockSections}
      roleFlags={{ isAdmin: true }}
      activeSectionId="alpha"
      onNavigate={() => {}}
      isCollapsed
    />
  );

  expect(screen.getByTestId("sidebar-status-panel").querySelector("[title]")).toBeNull();
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
