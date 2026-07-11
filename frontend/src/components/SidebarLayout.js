import React, { useCallback, useEffect, useRef, useState } from "react";

import Sidebar from "./Sidebar";
import TopBar from "./TopBar";
import { readStoredSidebarCollapsed, writeStoredSidebarCollapsed } from "../utils/sidebarPreference";
import { NAVIGATION_DESTINATIONS, getWorkspaceNavigationBehavior } from "../utils/workspaceNavigation";

function SidebarLayout({
  sections,
  roleFlags,
  activeSectionId,
  onNavigate,
  title,
  eyebrow,
  topBarActions,
  statusLabel,
  versionLabel,
  navigationRequest = null,
  children,
}) {
  const [isCollapsed, setIsCollapsed] = useState(() => readStoredSidebarCollapsed() ?? false);
  const mainRef = useRef(null);
  const handledNavigationNonceRef = useRef(null);

  const toggleCollapsed = useCallback(() => {
    setIsCollapsed((previous) => !previous);
  }, []);

  useEffect(() => {
    writeStoredSidebarCollapsed(isCollapsed);
  }, [isCollapsed]);

  useEffect(() => {
    const main = mainRef.current;
    if (!main || !navigationRequest || navigationRequest.sectionId !== activeSectionId) return;
    if (handledNavigationNonceRef.current === navigationRequest.nonce) return;
    if (navigationRequest.destination === NAVIGATION_DESTINATIONS.preserve) return;

    handledNavigationNonceRef.current = navigationRequest.nonce;
    const requestedTarget = navigationRequest.destination === NAVIGATION_DESTINATIONS.element
      ? main.querySelector(`[data-navigation-target="${navigationRequest.targetKey}"]`)
      : null;
    const primaryHeading = main.querySelector("[data-workspace-heading], h1, h2, [role='heading']");
    const focusTarget = requestedTarget || primaryHeading || main;
    const top = requestedTarget ? requestedTarget.offsetTop : 0;

    if (typeof main.scrollTo === "function") {
      main.scrollTo({ top, left: 0, behavior: getWorkspaceNavigationBehavior() });
    } else {
      main.scrollTop = top;
    }
    if (!focusTarget.hasAttribute("tabindex")) focusTarget.setAttribute("tabindex", "-1");
    focusTarget.focus({ preventScroll: true });
  }, [activeSectionId, navigationRequest]);

  return (
    <div style={shellStyle}>
      <TopBar
        isCollapsed={isCollapsed}
        onToggleCollapse={toggleCollapsed}
        title={title}
        eyebrow={eyebrow}
      >
        {topBarActions}
      </TopBar>

      <div style={bodyStyle}>
        <Sidebar
          sections={sections}
          roleFlags={roleFlags}
          activeSectionId={activeSectionId}
          onNavigate={onNavigate}
          isCollapsed={isCollapsed}
          statusLabel={statusLabel}
          versionLabel={versionLabel}
        />

        <main
          ref={mainRef}
          data-sidebar-state={isCollapsed ? "collapsed" : "expanded"}
          style={{ ...mainContentStyle, paddingLeft: "32px" }}
        >
          {children}
        </main>
      </div>
    </div>
  );
}

const shellStyle = {
  display: "flex",
  flexDirection: "column",
  minHeight: "100vh",
  backgroundColor: "#0d1117",
};

const bodyStyle = {
  display: "flex",
  flex: "1 1 auto",
  minHeight: 0,
  backgroundColor: "#0d1117",
};

const mainContentStyle = {
  flex: "1 1 auto",
  minWidth: 0,
  overflow: "auto",
  paddingTop: "18px",
  paddingRight: "32px",
  paddingBottom: "32px",
  boxSizing: "border-box",
  backgroundColor: "#0d1117",
};

export default SidebarLayout;
