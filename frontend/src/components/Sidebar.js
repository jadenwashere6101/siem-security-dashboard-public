import React from "react";

export const SIDEBAR_NAV_ID = "sidebar-shell-nav";

function Sidebar({
  sections = [],
  roleFlags = {},
  activeSectionId,
  onNavigate,
  isCollapsed = false,
  statusLabel,
  versionLabel,
}) {
  const visibleSections = sections.filter((section) =>
    typeof section.visibleWhen === "function" ? section.visibleWhen(roleFlags) : true
  );

  const groups = [];
  const groupIndexByName = new Map();

  visibleSections.forEach((section) => {
    const groupName = section.group || "";

    if (!groupIndexByName.has(groupName)) {
      groupIndexByName.set(groupName, groups.length);
      groups.push({ name: groupName, sections: [] });
    }

    groups[groupIndexByName.get(groupName)].sections.push(section);
  });

  return (
    <aside style={{ ...asideStyle, width: isCollapsed ? 64 : 240 }}>
      <nav id={SIDEBAR_NAV_ID} aria-label="Primary" style={navStyle}>
        {groups.map((group) => (
          <div
            key={group.name || "ungrouped"}
            role="group"
            aria-label={group.name || undefined}
            style={groupStyle}
          >
            {group.name && !isCollapsed && (
              <p aria-hidden="true" style={groupHeadingStyle}>
                {group.name}
              </p>
            )}

            {group.sections.map((section) => {
              const isActive = section.id === activeSectionId;

              return (
                <button
                  key={section.id}
                  type="button"
                  onClick={() => onNavigate(section.id)}
                  aria-current={isActive ? "page" : undefined}
                  title={section.label}
                  style={{
                    ...navButtonStyle,
                    ...(isCollapsed ? collapsedNavButtonStyle : {}),
                    ...(isActive ? activeNavButtonStyle : {}),
                  }}
                >
                  {isCollapsed && (
                    <span aria-hidden="true" style={collapsedGlyphStyle}>
                      {section.label.trim().charAt(0).toUpperCase()}
                    </span>
                  )}
                  <span style={isCollapsed ? visuallyHiddenStyle : undefined}>
                    {section.label}
                  </span>
                </button>
              );
            })}
          </div>
        ))}
      </nav>

      <div data-testid="sidebar-status-panel" style={statusPanelStyle}>
        {isCollapsed
          ? (statusLabel || versionLabel) && (
              <span
                aria-hidden="true"
                title={[statusLabel, versionLabel].filter(Boolean).join(" · ")}
                style={collapsedStatusDotStyle}
              />
            )
          : (
            <>
              {statusLabel && (
                <p style={statusLabelStyle} title={statusLabel}>
                  {statusLabel}
                </p>
              )}
              {versionLabel && (
                <p style={versionLabelStyle} title={versionLabel}>
                  {versionLabel}
                </p>
              )}
            </>
          )}
      </div>
    </aside>
  );
}

const asideStyle = {
  display: "flex",
  flexDirection: "column",
  justifyContent: "space-between",
  height: "100%",
  backgroundColor: "#0d1117",
  borderRight: "1px solid #30363d",
  transition: "width 120ms ease",
  overflow: "hidden",
  boxSizing: "border-box",
};

const navStyle = {
  display: "flex",
  flexDirection: "column",
  gap: "18px",
  padding: "16px 12px",
  overflowY: "auto",
};

const groupStyle = {
  display: "flex",
  flexDirection: "column",
  gap: "4px",
};

const groupHeadingStyle = {
  margin: "0 0 6px 8px",
  color: "#8b949e",
  fontSize: "11px",
  fontWeight: "700",
  textTransform: "uppercase",
  letterSpacing: "0.06em",
};

const navButtonStyle = {
  display: "flex",
  alignItems: "center",
  width: "100%",
  minHeight: "38px",
  padding: "10px 14px",
  borderWidth: "1px",
  borderStyle: "solid",
  borderColor: "transparent",
  borderRadius: "8px",
  backgroundColor: "transparent",
  color: "#c9d1d9",
  fontSize: "13px",
  fontWeight: "600",
  textAlign: "left",
  cursor: "pointer",
  whiteSpace: "nowrap",
  overflow: "hidden",
  textOverflow: "ellipsis",
  boxSizing: "border-box",
};

const collapsedNavButtonStyle = {
  justifyContent: "center",
  padding: "10px 0",
};

const collapsedGlyphStyle = {
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  width: "22px",
  height: "22px",
  fontSize: "12px",
  fontWeight: "700",
};

const activeNavButtonStyle = {
  backgroundColor: "#1f6feb",
  borderColor: "#1f6feb",
  color: "#ffffff",
};

const visuallyHiddenStyle = {
  position: "absolute",
  width: "1px",
  height: "1px",
  padding: 0,
  margin: "-1px",
  overflow: "hidden",
  clip: "rect(0, 0, 0, 0)",
  whiteSpace: "nowrap",
  border: 0,
};

const statusPanelStyle = {
  padding: "14px 12px",
  borderTop: "1px solid #30363d",
};

const collapsedStatusDotStyle = {
  display: "block",
  width: "10px",
  height: "10px",
  margin: "0 auto",
  borderRadius: "50%",
  backgroundColor: "#3fb950",
};

const statusLabelStyle = {
  margin: "0 0 4px 0",
  color: "#3fb950",
  fontSize: "12px",
  fontWeight: "700",
  whiteSpace: "nowrap",
  overflow: "hidden",
  textOverflow: "ellipsis",
};

const versionLabelStyle = {
  margin: 0,
  color: "#8b949e",
  fontSize: "11px",
  whiteSpace: "nowrap",
  overflow: "hidden",
  textOverflow: "ellipsis",
};

export default Sidebar;
