import React from "react";

function LoadingIndicator({
  label = "Loading...",
  size = 14,
  accentColor = "#58a6ff",
  style,
  spinnerStyle,
}) {
  return (
    <span role="status" aria-live="polite" style={{ ...containerStyle, ...style }}>
      <span
        className="workspace-loading-spinner"
        style={{
          width: `${size}px`,
          height: `${size}px`,
          borderTopColor: accentColor,
          ...spinnerStyle,
        }}
        aria-hidden="true"
      />
      <span>{label}</span>
    </span>
  );
}

const containerStyle = {
  display: "inline-flex",
  alignItems: "center",
  gap: "8px",
  color: "#c9d1d9",
};

export default LoadingIndicator;
