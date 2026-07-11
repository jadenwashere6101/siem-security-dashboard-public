import React, { useCallback, useEffect, useState } from "react";

import Sidebar from "./Sidebar";
import TopBar from "./TopBar";
import { readStoredSidebarCollapsed, writeStoredSidebarCollapsed } from "../utils/sidebarPreference";

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
  children,
}) {
  const [isCollapsed, setIsCollapsed] = useState(() => readStoredSidebarCollapsed() ?? false);

  const toggleCollapsed = useCallback(() => {
    setIsCollapsed((previous) => !previous);
  }, []);

  useEffect(() => {
    writeStoredSidebarCollapsed(isCollapsed);
  }, [isCollapsed]);

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
