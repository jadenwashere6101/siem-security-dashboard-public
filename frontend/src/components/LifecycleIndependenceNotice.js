import React from "react";
import { LIFECYCLE_INDEPENDENCE_COPY } from "../utils/responseStateLabels";

const noticeStyle = {
  marginTop: "10px",
  marginBottom: "10px",
  padding: "10px 12px",
  borderRadius: "6px",
  border: "1px solid #30363d",
  background: "#0d1117",
  color: "#8b949e",
  fontSize: "12px",
  lineHeight: 1.45,
};

const actionStyle = {
  marginTop: "8px",
  background: "transparent",
  border: "1px solid #388bfd",
  color: "#58a6ff",
  borderRadius: "6px",
  padding: "4px 8px",
  cursor: "pointer",
  fontSize: "12px",
};

/**
 * Explains that alert/incident/response/approval/execution lifecycles are independent.
 */
function LifecycleIndependenceNotice({
  onReviewIncident = null,
  reviewLabel = "Review linked incident",
}) {
  return (
    <aside
      style={noticeStyle}
      data-testid="lifecycle-independence-notice"
      role="note"
    >
      {LIFECYCLE_INDEPENDENCE_COPY}
      {typeof onReviewIncident === "function" ? (
        <div>
          <button type="button" onClick={onReviewIncident} style={actionStyle}>
            {reviewLabel}
          </button>
        </div>
      ) : null}
    </aside>
  );
}

export default LifecycleIndependenceNotice;
