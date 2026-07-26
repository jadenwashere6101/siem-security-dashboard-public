import { render, screen } from "@testing-library/react";
import fs from "fs";
import path from "path";

describe("WorkspaceAsyncState", () => {
  test("renders the shared globally-styled spinner", async () => {
    const { WorkspaceInitialState } = await import("./WorkspaceAsyncState");
    render(<WorkspaceInitialState loading loadingLabel="Loading workspace" />);
    expect(screen.getByRole("status").firstChild).toHaveClass("workspace-loading-spinner");
  });

  test("global CSS provides animation and reduced-motion fallback", () => {
    const css = fs.readFileSync(path.resolve(__dirname, "../index.css"), "utf8");
    expect(css).toContain("@keyframes workspace-spin");
    expect(css).toContain(".workspace-loading-spinner");
    expect(css).toContain("@media (prefers-reduced-motion: reduce)");
    expect(css).toContain("animation: none");
  });
});
