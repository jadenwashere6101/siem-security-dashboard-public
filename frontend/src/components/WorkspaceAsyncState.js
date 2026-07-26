import React from "react";
import LoadingIndicator from "./LoadingIndicator";

export function WorkspaceInitialState({ loading, error, loadingLabel, errorLabel, onRetry }) {
  if (loading) {
    return (
      <LoadingIndicator label={loadingLabel} size={16} style={initialStateStyle} />
    );
  }

  if (!error) {
    return null;
  }

  return (
    <div role="alert" style={errorStateStyle}>
      <span>{errorLabel || error}</span>
      {typeof onRetry === "function" ? (
        <button type="button" onClick={onRetry} style={retryButtonStyle}>
          Retry
        </button>
      ) : null}
    </div>
  );
}

export function WorkspaceRefreshState({ refreshing, refreshError }) {
  return (
    <>
      {refreshing ? (
        <p role="status" aria-live="polite" style={refreshStateStyle}>
          Refreshing…
        </p>
      ) : null}
      {!refreshing && refreshError ? (
        <div role="alert" style={warningStateStyle}>
          Refresh failed: {refreshError}. Showing the last successful data.
        </div>
      ) : null}
    </>
  );
}

const initialStateStyle = {
  display: "flex",
  alignItems: "center",
  gap: "10px",
  minHeight: "120px",
  color: "#c9d1d9",
  padding: "12px 0",
};

const errorStateStyle = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: "12px",
  padding: "12px 14px",
  borderRadius: "10px",
  border: "1px solid rgba(248, 81, 73, 0.35)",
  backgroundColor: "rgba(248, 81, 73, 0.12)",
  color: "#ffa198",
};

const warningStateStyle = {
  padding: "10px 12px",
  marginBottom: "16px",
  borderRadius: "10px",
  border: "1px solid rgba(210, 153, 34, 0.35)",
  backgroundColor: "rgba(210, 153, 34, 0.12)",
  color: "#e3b341",
};

const refreshStateStyle = {
  margin: "0 0 12px",
  color: "#9da7b3",
  fontSize: "13px",
};

const retryButtonStyle = {
  border: "1px solid rgba(255, 255, 255, 0.16)",
  background: "#0d1117",
  color: "#f0f6fc",
  borderRadius: "8px",
  padding: "6px 12px",
  cursor: "pointer",
};

export default WorkspaceInitialState;
