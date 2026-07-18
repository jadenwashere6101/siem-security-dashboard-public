import { render, screen } from "@testing-library/react";

describe("WorkspaceAsyncState", () => {
  const originalMatchMedia = window.matchMedia;

  afterEach(() => {
    window.matchMedia = originalMatchMedia;
    jest.resetModules();
  });

  test("renders a rotating spinner by default", async () => {
    window.matchMedia = jest.fn().mockReturnValue({
      matches: false,
      addListener: jest.fn(),
      removeListener: jest.fn(),
    });
    const { WorkspaceInitialState } = await import("./WorkspaceAsyncState");
    render(<WorkspaceInitialState loading loadingLabel="Loading workspace" />);
    expect(screen.getByRole("status").firstChild).toHaveStyle({
      animation: "workspace-spin 0.85s linear infinite",
    });
  });

  test("disables spinner animation for reduced motion", async () => {
    window.matchMedia = jest.fn().mockReturnValue({
      matches: true,
      addListener: jest.fn(),
      removeListener: jest.fn(),
    });
    const { WorkspaceInitialState } = await import("./WorkspaceAsyncState");
    render(<WorkspaceInitialState loading loadingLabel="Loading workspace" />);
    expect(screen.getByRole("status").firstChild).toHaveStyle({ animation: "none" });
  });
});
