import React from "react";

function AlertResponseIndicator({ responseAction }) {
  return (
    <span
      title={responseAction || "No response action"}
      style={{
        width: "10px",
        height: "10px",
        borderRadius: "999px",
        backgroundColor: getResponseIndicatorColor(responseAction),
        boxShadow: `0 0 0 2px rgba(255, 255, 255, 0.04), 0 0 0 1px ${getResponseIndicatorColor(responseAction)}`,
        flexShrink: 0,
      }}
    />
  );
}

const getResponseIndicatorColor = (action) => {
  if (action === "block_ip") return "#ef4444";
  if (action === "flag_high_priority") return "#f59e0b";
  if (action === "monitor") return "#22c55e";
  return "#6b7280";
};

export default AlertResponseIndicator;
