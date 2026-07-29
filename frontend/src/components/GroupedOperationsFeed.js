import React from "react";

import { theme, toneStyles } from "../theme";
import { Badge } from "./uiPrimitives";
import { groupOperationalFeedEntries } from "./groupedOperationsFeedModel";

function GroupedOperationsFeed({
  entries = [],
  loading = false,
  error = "",
  stale = false,
  emptyLabel = "No recent operational activity found.",
  formatTime = (value) => value || "Time unavailable",
}) {
  const groups = groupOperationalFeedEntries(entries).filter((group) => group.items.length > 0);

  if (loading && entries.length === 0) {
    return <div style={stateStyle}>Loading activity...</div>;
  }

  if (error && entries.length === 0) {
    return <div style={{ ...stateStyle, color: theme.color.dangerSoft }}>{error}</div>;
  }

  if (entries.length === 0) {
    return <div style={stateStyle}>{emptyLabel}</div>;
  }

  return (
    <div style={feedWrapStyle} aria-label="Grouped live operations feed">
      {stale || error ? (
        <p style={noticeStyle}>{error || "Activity may be stale while data refreshes."}</p>
      ) : null}
      {groups.map((group) => (
        <section key={group.id} style={groupStyle} aria-labelledby={`operations-feed-${group.id}`}>
          <div style={groupHeaderStyle}>
            <h4 id={`operations-feed-${group.id}`} style={groupTitleStyle}>{group.label}</h4>
            <Badge tone={group.tone}>{group.items.length}</Badge>
          </div>
          <div style={itemListStyle}>
            {group.items.map((entry) => (
              <article key={entry.id} style={itemStyle}>
                <div style={railStyle}>
                  <span style={{ ...dotStyle, backgroundColor: (toneStyles[entry.tone] || toneStyles.neutral).borderColor }} />
                </div>
                <div style={{ minWidth: 0 }}>
                  <div style={metaStyle}>
                    <Badge tone={entry.tone}>{entry.source}</Badge>
                    <span style={timeStyle}>{formatTime(entry.timestamp)}</span>
                  </div>
                  <p style={titleStyle}>{entry.title}</p>
                  <p style={detailStyle}>{entry.detail || "No additional metadata"}</p>
                  {entry.relatedObjectLabel ? <p style={relatedStyle}>{entry.relatedObjectLabel}</p> : null}
                </div>
              </article>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

const feedWrapStyle = {
  padding: `${theme.spacing.md}px ${theme.spacing.lg}px ${theme.spacing.lg}px`,
  display: "grid",
  gap: theme.spacing.md,
};

const stateStyle = {
  padding: `${theme.spacing.lg}px`,
  color: theme.color.textMuted,
  fontSize: "13px",
};

const noticeStyle = {
  margin: 0,
  color: theme.color.reviewSoft,
  fontSize: "12px",
};

const groupStyle = {
  border: `1px solid ${theme.color.border}`,
  borderRadius: theme.radius.sm,
  backgroundColor: theme.color.bg,
  overflow: "hidden",
};

const groupHeaderStyle = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: theme.spacing.sm,
  padding: `${theme.spacing.sm}px ${theme.spacing.md}px`,
  borderBottom: `1px solid ${theme.color.border}`,
};

const groupTitleStyle = {
  margin: 0,
  color: theme.color.text,
  fontSize: "12px",
  fontWeight: 900,
  letterSpacing: "0.04em",
  textTransform: "uppercase",
};

const itemListStyle = {
  display: "grid",
};

const itemStyle = {
  display: "grid",
  gridTemplateColumns: "18px minmax(0, 1fr)",
  gap: theme.spacing.sm,
  padding: `${theme.spacing.md}px`,
  borderBottom: `1px solid ${theme.color.border}`,
};

const railStyle = {
  display: "flex",
  justifyContent: "center",
  paddingTop: 5,
};

const dotStyle = {
  width: 9,
  height: 9,
  borderRadius: theme.radius.pill,
};

const metaStyle = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: theme.spacing.sm,
  flexWrap: "wrap",
};

const timeStyle = {
  color: theme.color.textMuted,
  fontSize: "11px",
};

const titleStyle = {
  margin: "7px 0 3px",
  color: theme.color.text,
  fontSize: "13px",
  fontWeight: 800,
  lineHeight: 1.35,
  overflowWrap: "anywhere",
};

const detailStyle = {
  margin: 0,
  color: theme.color.textMuted,
  fontSize: "12px",
  lineHeight: 1.35,
};

const relatedStyle = {
  margin: "4px 0 0",
  color: theme.color.textSoft,
  fontSize: "11px",
};

export default GroupedOperationsFeed;
