import {
  NAVIGATION_DESTINATIONS,
  WORKSPACE_TARGETS,
  createWorkspaceNavigationRequest,
  getWorkspaceNavigationBehavior,
} from "./workspaceNavigation";

test("creates structured requests with unique nonces and preserved context", () => {
  const top = createWorkspaceNavigationRequest("dashboard");
  const element = createWorkspaceNavigationRequest("dashboard", {
    destination: NAVIGATION_DESTINATIONS.element,
    targetKey: WORKSPACE_TARGETS.recentAlerts,
    context: { sourceIp: "8.8.8.8" },
  });
  expect(top).toEqual(expect.objectContaining({ sectionId: "dashboard", destination: "top" }));
  expect(element.context).toEqual({ sourceIp: "8.8.8.8" });
  expect(element.nonce).toBeGreaterThan(top.nonce);
});

test("rejects incomplete and unsupported requests", () => {
  expect(() => createWorkspaceNavigationRequest("")).toThrow(/sectionId/);
  expect(() => createWorkspaceNavigationRequest("dashboard", { destination: "sideways" })).toThrow(/unsupported/i);
  expect(() => createWorkspaceNavigationRequest("dashboard", { destination: "element" })).toThrow(/targetKey/i);
});

test("preserve destination skips scroll and focus effects", () => {
  createWorkspaceNavigationRequest("dashboard", {
    destination: NAVIGATION_DESTINATIONS.preserve,
  });
  expect(
    createWorkspaceNavigationRequest("dashboard", {
      destination: NAVIGATION_DESTINATIONS.preserve,
      context: { filter: "open" },
    })
  ).toEqual(
    expect.objectContaining({
      sectionId: "dashboard",
      destination: "preserve",
      context: { filter: "open" },
    })
  );
});

test("respects reduced-motion preference", () => {
  const original = window.matchMedia;
  window.matchMedia = jest.fn().mockReturnValue({ matches: true });
  expect(getWorkspaceNavigationBehavior()).toBe("auto");
  window.matchMedia = jest.fn().mockReturnValue({ matches: false });
  expect(getWorkspaceNavigationBehavior()).toBe("smooth");
  window.matchMedia = original;
});
