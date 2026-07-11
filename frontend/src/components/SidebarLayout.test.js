import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import SidebarLayout from "./SidebarLayout";
import {
  readStoredSidebarCollapsed,
  writeStoredSidebarCollapsed,
} from "../utils/sidebarPreference";

jest.mock("../utils/sidebarPreference", () => ({
  readStoredSidebarCollapsed: jest.fn(),
  writeStoredSidebarCollapsed: jest.fn(),
}));

beforeEach(() => {
  jest.clearAllMocks();
  readStoredSidebarCollapsed.mockReturnValue(null);
});

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
  expect(screen.queryByRole("button", { name: "Alpha" })).not.toBeInTheDocument();
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

test("renders topBarActions content inside TopBar's right-side slot", () => {
  render(
    <SidebarLayout
      sections={mockSections}
      roleFlags={{ isAdmin: true }}
      activeSectionId="alpha"
      onNavigate={() => {}}
      title="SIEM Dashboard"
      topBarActions={<button type="button">Log out</button>}
    >
      <p>Page Content</p>
    </SidebarLayout>
  );

  expect(screen.getByRole("button", { name: "Log out" })).toBeInTheDocument();
});

test("forwards eyebrow to TopBar when provided", () => {
  render(
    <SidebarLayout
      sections={mockSections}
      roleFlags={{ isAdmin: true }}
      activeSectionId="alpha"
      onNavigate={() => {}}
      title="SIEM Dashboard"
      eyebrow="SIEM"
    >
      <p>Page Content</p>
    </SidebarLayout>
  );

  expect(screen.getByText("SIEM")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "SIEM Dashboard" })).toBeInTheDocument();
});

test("initializes collapsed when a stored preference of true is present", () => {
  readStoredSidebarCollapsed.mockReturnValue(true);

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

  expect(screen.getByRole("button", { name: /toggle navigation/i })).toHaveAttribute(
    "aria-expanded",
    "false"
  );
});

test("initializes expanded when no stored preference is present", () => {
  readStoredSidebarCollapsed.mockReturnValue(null);

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

  expect(screen.getByRole("button", { name: /toggle navigation/i })).toHaveAttribute(
    "aria-expanded",
    "true"
  );
});

test("persists the new collapse state when toggled", async () => {
  readStoredSidebarCollapsed.mockReturnValue(false);

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

  expect(writeStoredSidebarCollapsed).toHaveBeenCalledWith(false);

  await userEvent.click(screen.getByRole("button", { name: /toggle navigation/i }));

  expect(writeStoredSidebarCollapsed).toHaveBeenCalledWith(true);
});

test("does not add a new prop to the public contract for persistence", () => {
  readStoredSidebarCollapsed.mockReturnValue(null);

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

  expect(screen.getByRole("button", { name: "Alpha" })).toBeInTheDocument();
  expect(screen.getByText("Page Content")).toBeInTheDocument();
});

test("main content region has a dark background so no white gutter shows through", () => {
  readStoredSidebarCollapsed.mockReturnValue(null);

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

  const pageContent = screen.getByText("Page Content");
  const mainRegion = pageContent.closest("main");
  expect(mainRegion).toHaveStyle({ backgroundColor: "#0d1117" });
});

test("main content region has minWidth 0 so wide content cannot squeeze the sidebar", () => {
  readStoredSidebarCollapsed.mockReturnValue(null);

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

  const pageContent = screen.getByText("Page Content");
  const mainRegion = pageContent.closest("main");
  expect(mainRegion).toHaveStyle({ minWidth: 0 });
});

test("main content keeps balanced gutters when the sidebar is collapsed", () => {
  readStoredSidebarCollapsed.mockReturnValue(true);

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

  const pageContent = screen.getByText("Page Content");
  const mainRegion = pageContent.closest("main");
  expect(mainRegion).toHaveAttribute("data-sidebar-state", "collapsed");
  expect(mainRegion).toHaveStyle({ paddingLeft: "32px", paddingRight: "32px" });
});

test("main content keeps its left padding when the sidebar is expanded", () => {
  readStoredSidebarCollapsed.mockReturnValue(false);

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

  const pageContent = screen.getByText("Page Content");
  const mainRegion = pageContent.closest("main");
  expect(mainRegion).toHaveAttribute("data-sidebar-state", "expanded");
  expect(mainRegion).toHaveStyle({ paddingLeft: "32px", paddingRight: "32px" });
});

test("ordinary navigation resets the main container and focuses its primary heading", () => {
  const { rerender } = render(
    <SidebarLayout
      sections={mockSections}
      roleFlags={{ isAdmin: true }}
      activeSectionId="alpha"
      onNavigate={() => {}}
      title="SIEM Dashboard"
    >
      <h2>Alpha workspace</h2>
    </SidebarLayout>
  );
  const main = screen.getByRole("main");
  main.scrollTo = jest.fn();

  rerender(
    <SidebarLayout
      sections={mockSections}
      roleFlags={{ isAdmin: true }}
      activeSectionId="gamma"
      onNavigate={() => {}}
      title="SIEM Dashboard"
      navigationRequest={{ sectionId: "gamma", destination: "top", nonce: 1 }}
    >
      <h2>Gamma workspace</h2>
    </SidebarLayout>
  );

  expect(main.scrollTo).toHaveBeenCalledWith({ top: 0, left: 0, behavior: "smooth" });
  expect(screen.getByRole("heading", { name: "Gamma workspace" })).toHaveFocus();
});

test("element navigation preserves the deep destination and background rerenders do not steal focus", () => {
  const request = {
    sectionId: "alpha",
    destination: "element",
    targetKey: "recent-alerts",
    nonce: 2,
  };
  const { rerender } = render(
    <SidebarLayout
      sections={mockSections}
      roleFlags={{ isAdmin: true }}
      activeSectionId="alpha"
      onNavigate={() => {}}
      title="SIEM Dashboard"
    >
      <h2>Alpha workspace</h2>
      <div data-navigation-target="recent-alerts">Recent Alerts target</div>
    </SidebarLayout>
  );
  const main = screen.getByRole("main");
  const target = screen.getByText("Recent Alerts target");
  Object.defineProperty(target, "offsetTop", { configurable: true, value: 240 });
  main.scrollTo = jest.fn();

  rerender(
    <SidebarLayout
      sections={mockSections}
      roleFlags={{ isAdmin: true }}
      activeSectionId="alpha"
      onNavigate={() => {}}
      title="SIEM Dashboard"
      navigationRequest={request}
    >
      <h2>Alpha workspace</h2>
      <div data-navigation-target="recent-alerts">Recent Alerts target</div>
    </SidebarLayout>
  );

  expect(main.scrollTo).toHaveBeenCalledWith({ top: 240, left: 0, behavior: "smooth" });
  expect(target).toHaveFocus();
  main.scrollTo.mockClear();

  rerender(
    <SidebarLayout
      sections={mockSections}
      roleFlags={{ isAdmin: true }}
      activeSectionId="alpha"
      onNavigate={() => {}}
      title="SIEM Dashboard"
      navigationRequest={request}
    >
      <h2>Alpha workspace refreshed</h2>
      <div data-navigation-target="recent-alerts">Recent Alerts target</div>
    </SidebarLayout>
  );
  expect(main.scrollTo).not.toHaveBeenCalled();
});

test("missing element target falls back to top and reduced motion disables animation", () => {
  const originalMatchMedia = window.matchMedia;
  window.matchMedia = jest.fn().mockReturnValue({ matches: true });
  const { rerender } = render(
    <SidebarLayout
      sections={mockSections}
      roleFlags={{ isAdmin: true }}
      activeSectionId="alpha"
      onNavigate={() => {}}
      title="SIEM Dashboard"
    >
      <h2>Fallback heading</h2>
    </SidebarLayout>
  );
  const main = screen.getByRole("main");
  main.scrollTo = jest.fn();

  rerender(
    <SidebarLayout
      sections={mockSections}
      roleFlags={{ isAdmin: true }}
      activeSectionId="alpha"
      onNavigate={() => {}}
      title="SIEM Dashboard"
      navigationRequest={{ sectionId: "alpha", destination: "element", targetKey: "missing", nonce: 3 }}
    >
      <h2>Fallback heading</h2>
    </SidebarLayout>
  );

  expect(main.scrollTo).toHaveBeenCalledWith({ top: 0, left: 0, behavior: "auto" });
  expect(screen.getByRole("heading", { name: "Fallback heading" })).toHaveFocus();
  window.matchMedia = originalMatchMedia;
});
