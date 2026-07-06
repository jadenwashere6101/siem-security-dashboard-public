import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import SidebarLayout from "./SidebarLayout";

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

test("composes TopBar title, Sidebar nav items, and main content children", () => {
  render(
    <SidebarLayout
      sections={mockSections}
      roleFlags={{ isAdmin: true }}
      activeSectionId="alpha"
      onNavigate={() => {}}
      title="SIEM Dashboard"
      statusLabel="Operational"
      versionLabel="v1.0.0"
    >
      <p>Page Content</p>
    </SidebarLayout>
  );

  expect(screen.getByRole("heading", { name: "SIEM Dashboard" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Alpha" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Gamma" })).toBeInTheDocument();
  expect(screen.getByText("Page Content")).toBeInTheDocument();
  expect(screen.getByText("Operational")).toBeInTheDocument();
});

test("forwards roleFlags-driven visibility to Sidebar", () => {
  render(
    <SidebarLayout
      sections={mockSections}
      roleFlags={{ isAdmin: false }}
      activeSectionId="alpha"
      onNavigate={() => {}}
      title="SIEM Dashboard"
    >
      <p>Page Content</p>
    </SidebarLayout>
  );

  expect(screen.queryByRole("button", { name: "Beta" })).not.toBeInTheDocument();
});

test("forwards onNavigate so clicking a nav item calls it with the correct id", async () => {
  const onNavigate = jest.fn();

  render(
    <SidebarLayout
      sections={mockSections}
      roleFlags={{ isAdmin: true }}
      activeSectionId="alpha"
      onNavigate={onNavigate}
      title="SIEM Dashboard"
    >
      <p>Page Content</p>
    </SidebarLayout>
  );

  await userEvent.click(screen.getByRole("button", { name: "Gamma" }));

  expect(onNavigate).toHaveBeenCalledWith("gamma");
});

test("toggling the hamburger flips collapse state and propagates to both TopBar and Sidebar", async () => {
  render(
    <SidebarLayout
      sections={mockSections}
      roleFlags={{ isAdmin: true }}
      activeSectionId="alpha"
      onNavigate={() => {}}
      title="SIEM Dashboard"
    >
      <p>Page Content</p>
    </SidebarLayout>
  );

  const toggleButton = screen.getByRole("button", { name: /toggle navigation/i });
  expect(toggleButton).toHaveAttribute("aria-expanded", "true");

  await userEvent.click(toggleButton);

  expect(toggleButton).toHaveAttribute("aria-expanded", "false");
  expect(screen.getByRole("button", { name: "Alpha" })).toBeInTheDocument();
});

test("does not own activeSection state; activeSectionId prop alone controls highlighting", () => {
  render(
    <SidebarLayout
      sections={mockSections}
      roleFlags={{ isAdmin: true }}
      activeSectionId="gamma"
      onNavigate={() => {}}
      title="SIEM Dashboard"
    >
      <p>Page Content</p>
    </SidebarLayout>
  );

  expect(screen.getByRole("button", { name: "Gamma" })).toHaveAttribute(
    "aria-current",
    "page"
  );
  expect(screen.getByRole("button", { name: "Alpha" })).not.toHaveAttribute(
    "aria-current"
  );
});
