export const NAVIGATION_DESTINATIONS = Object.freeze({
  top: "top",
  element: "element",
  preserve: "preserve",
});

export const WORKSPACE_TARGETS = Object.freeze({
  recentAlerts: "recent-alerts",
  responseRegistry: "response-registry",
  approvals: "soar-approvals",
});

let navigationNonce = 0;

export function createWorkspaceNavigationRequest(
  sectionId,
  { destination = NAVIGATION_DESTINATIONS.top, targetKey = null, context = null } = {}
) {
  const normalizedSectionId = String(sectionId || "").trim();
  if (!normalizedSectionId) throw new Error("Workspace navigation requires a sectionId");
  if (!Object.values(NAVIGATION_DESTINATIONS).includes(destination)) {
    throw new Error(`Unsupported workspace navigation destination: ${destination}`);
  }
  const normalizedTargetKey = targetKey == null ? null : String(targetKey).trim();
  if (destination === NAVIGATION_DESTINATIONS.element && !normalizedTargetKey) {
    throw new Error("Element workspace navigation requires a targetKey");
  }

  navigationNonce += 1;
  return {
    sectionId: normalizedSectionId,
    destination,
    targetKey: normalizedTargetKey,
    context,
    nonce: navigationNonce,
  };
}

export function getWorkspaceNavigationBehavior() {
  const reduceMotion =
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  return reduceMotion ? "auto" : "smooth";
}
