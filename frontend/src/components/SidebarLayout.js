import React, { useCallback, useState } from "react";

import Sidebar from "./Sidebar";
import TopBar from "./TopBar";

function SidebarLayout({
  sections,
  roleFlags,
  activeSectionId,
  onNavigate,
  title,
  statusLabel,
  versionLabel,
  children,
}) {
  const [isCollapsed, setIsCollapsed] = useState(false);

  const toggleCollapsed = useCallback(() => {
    setIsCollapsed((previous) => !previous);
  }, []);

  return (
    <div style={shellStyle}>
      <TopBar isCollapsed={isCollapsed} onToggleCollapse={toggleCollapsed} title={title} />

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

        <main style={mainContentStyle}>{children}</main>
      </div>
    </div>
  );
}

const shellStyle = {
  display: "flex",
  flexDirection: "column",
  minHeight: "100vh",
};

const bodyStyle = {
  display: "flex",
  flex: "1 1 auto",
  minHeight: 0,
};

const mainContentStyle = {
  flex: "1 1 auto",
  overflow: "auto",
  padding: "18px 32px 32px",
  boxSizing: "border-box",
};

export default SidebarLayout;
