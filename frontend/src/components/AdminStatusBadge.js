import React from "react";

function AdminStatusBadge({ isActive }) {
  return (
    <span
      style={{
        ...statusBadgeStyle,
        ...(isActive ? activeStatusStyle : inactiveStatusStyle),
      }}
    >
      {isActive ? "Active" : "Inactive"}
    </span>
  );
}

const statusBadgeStyle = {
  display: "inline-block",
  padding: "3px 7px",
  borderRadius: "999px",
  fontSize: "10px",
  fontWeight: "700",
  textTransform: "uppercase",
  letterSpacing: "0.04em",
};

const activeStatusStyle = {
  color: "#86efac",
  backgroundColor: "rgba(34, 197, 94, 0.12)",
  border: "1px solid rgba(34, 197, 94, 0.28)",
};

const inactiveStatusStyle = {
  color: "#fca5a5",
  backgroundColor: "rgba(239, 68, 68, 0.12)",
  border: "1px solid rgba(239, 68, 68, 0.28)",
};

export default AdminStatusBadge;
