import React from "react";

function AlertTimeline({
  selectedAlert,
  selectedAlertTimeline,
  getSourceBadgeMeta,
}) {
  const formatTimelineTimestamp = (value) => {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return value;
    }

    return new Intl.DateTimeFormat("en-US", {
      month: "short",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
      timeZone: "UTC",
    }).format(date);
  };

  return (
    <div style={timelineSectionStyle}>
      <strong>Activity Timeline</strong>
      <div style={timelineListStyle}>
        {selectedAlertTimeline.map((relatedAlert) => {
          const relatedSourceBadge = getSourceBadgeMeta(
            relatedAlert.source,
            relatedAlert.source_type
          );
          const isCurrentTimelineAlert = relatedAlert.id === selectedAlert.id;

          return (
            <div
              key={relatedAlert.id}
              style={{
                ...timelineEntryStyle,
                ...(isCurrentTimelineAlert ? activeTimelineEntryStyle : {}),
              }}
            >
              <div style={timelineMetaRowStyle}>
                <span
                  style={{
                    ...timelineTypeStyle,
                    fontWeight: isCurrentTimelineAlert ? "800" : "700",
                  }}
                >
                  {relatedAlert.alert_type}
                </span>
                <span style={timelineSubtextStyle}>
                  {formatTimelineTimestamp(relatedAlert.created_at)}
                </span>
              </div>
              <div style={{ ...timelineMetaRowStyle, marginTop: "4px" }}>
                <span style={timelineSubtextStyle}>
                  {relatedSourceBadge.label}
                </span>
                <span style={timelineSubtextStyle}>
                  {String(relatedAlert.severity || "unknown").toUpperCase()}
                  {isCurrentTimelineAlert ? " · Current Alert" : ""}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

const timelineSectionStyle = {
  marginTop: "14px",
  paddingTop: "10px",
  borderTop: "1px solid #30363d",
};
const timelineListStyle = {
  display: "flex",
  flexDirection: "column",
  gap: "6px",
  marginTop: "8px",
};
const timelineEntryStyle = {
  padding: "8px 10px",
  borderRadius: "8px",
  border: "1px solid #30363d",
  backgroundColor: "#111827",
};
const activeTimelineEntryStyle = {
  border: "1px solid rgba(96, 165, 250, 0.34)",
  backgroundColor: "rgba(30, 64, 175, 0.18)",
};
const timelineMetaRowStyle = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  gap: "10px",
  flexWrap: "wrap",
};
const timelineTypeStyle = {
  color: "#e6edf3",
  fontSize: "12px",
  fontWeight: "700",
};
const timelineSubtextStyle = {
  color: "#8b949e",
  fontSize: "11px",
};

export default AlertTimeline;
