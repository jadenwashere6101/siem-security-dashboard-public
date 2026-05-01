import React, { useEffect, useState } from "react";
import AdminStatusBadge from "./AdminStatusBadge";
import {
  createAdminUser,
  loadAdminUsers,
  resetAdminUserPassword,
  updateAdminUserRole,
  updateAdminUserStatus,
} from "../services/adminUsersService";

function AdminUsersPanel({
  cardStyle,
  cardHeaderStyle,
  cardTitleStyle,
  cardSubtitleStyle,
  filterLabelStyle,
  selectStyle,
}) {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [statusUpdating, setStatusUpdating] = useState("");
  const [roleUpdating, setRoleUpdating] = useState("");
  const [pendingRoles, setPendingRoles] = useState({});
  const [passwordResetTarget, setPasswordResetTarget] = useState("");
  const [passwordResetValue, setPasswordResetValue] = useState("");
  const [passwordResetSubmitting, setPasswordResetSubmitting] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("viewer");
  const [feedback, setFeedback] = useState({ type: "", message: "" });

  const formatCreatedAt = (value) => {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return value;
    }

    return new Intl.DateTimeFormat("en-US", {
      month: "short",
      day: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
      timeZone: "UTC",
      timeZoneName: "short",
    }).format(date);
  };

  const loadUsers = async () => {
    try {
      setLoading(true);
      const data = await loadAdminUsers();

      setUsers(Array.isArray(data) ? data : []);
    } catch (err) {
      setFeedback({
        type: "error",
        message: err.message || "Unable to load users",
      });
      setUsers([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadUsers();
  }, []);

  useEffect(() => {
    setPendingRoles((prev) => {
      const next = {};
      users.forEach((user) => {
        next[user.username] = prev[user.username] || user.role;
      });
      return next;
    });
  }, [users]);

  const handleCreateUser = async (e) => {
    e.preventDefault();
    setFeedback({ type: "", message: "" });

    try {
      setSubmitting(true);
      const data = await createAdminUser({ username, password, role });

      setUsername("");
      setPassword("");
      setRole("viewer");
      setFeedback({
        type: "success",
        message: data.message || "User created successfully",
      });
      await loadUsers();
    } catch (err) {
      setFeedback({
        type: "error",
        message: err.message || "Unable to create user",
      });
    } finally {
      setSubmitting(false);
    }
  };

  const handleStatusUpdate = async (targetUsername, isActive) => {
    setFeedback({ type: "", message: "" });

    try {
      setStatusUpdating(targetUsername);
      const data = await updateAdminUserStatus(targetUsername, isActive);

      setFeedback({
        type: "success",
        message: data.message || "User status updated successfully",
      });
      await loadUsers();
    } catch (err) {
      setFeedback({
        type: "error",
        message: err.message || "Unable to update user status",
      });
    } finally {
      setStatusUpdating("");
    }
  };

  const handlePasswordReset = async (targetUsername) => {
    setFeedback({ type: "", message: "" });

    try {
      setPasswordResetSubmitting(targetUsername);
      const data = await resetAdminUserPassword(targetUsername, passwordResetValue);

      setFeedback({
        type: "success",
        message: data.message || "Password updated successfully",
      });
      setPasswordResetTarget("");
      setPasswordResetValue("");
    } catch (err) {
      setFeedback({
        type: "error",
        message: err.message || "Unable to update password",
      });
      setPasswordResetValue("");
    } finally {
      setPasswordResetSubmitting("");
    }
  };

  const handleRoleUpdate = async (targetUsername) => {
    setFeedback({ type: "", message: "" });

    try {
      setRoleUpdating(targetUsername);
      const data = await updateAdminUserRole(targetUsername, pendingRoles[targetUsername]);

      setFeedback({
        type: "success",
        message: data.message || "User role updated successfully",
      });
      await loadUsers();
    } catch (err) {
      setFeedback({
        type: "error",
        message: err.message || "Unable to update user role",
      });
    } finally {
      setRoleUpdating("");
    }
  };

  return (
    <>
      <style>
        {`
          .admin-users-input::placeholder {
            color: #8b949e;
          }
        `}
      </style>
      <section style={cardStyle}>
      <div style={cardHeaderStyle}>
        <div>
          <p style={sectionLabelStyle}>Administration</p>
          <h2 style={cardTitleStyle}>Users</h2>
          <p style={cardSubtitleStyle}>
            Admin-only user management for auditor and analyst accounts.
          </p>
        </div>
      </div>

      <div style={panelContentStyle}>
        {feedback.message && (
          <div
            style={{
              ...feedbackStyle,
              ...(feedback.type === "error" ? errorFeedbackStyle : successFeedbackStyle),
            }}
          >
            {feedback.message}
          </div>
        )}

        <form onSubmit={handleCreateUser} style={formSectionStyle}>
          <div style={formInputsRowStyle}>
            <div style={formFieldStyle}>
              <label style={filterLabelStyle}>Username</label>
              <input
                className="admin-users-input"
                type="text"
                value={username}
                placeholder="Enter username"
                autoComplete="off"
                onChange={(e) => setUsername(e.target.value)}
                onFocus={(e) => {
                  e.target.style.border = "1px solid #58a6ff";
                }}
                onBlur={(e) => {
                  e.target.style.border = "1px solid #30363d";
                }}
                style={adminInputStyle}
              />
            </div>

            <div style={formFieldStyle}>
              <label style={filterLabelStyle}>Password</label>
              <input
                className="admin-users-input"
                type="password"
                value={password}
                placeholder="Enter password"
                autoComplete="new-password"
                onChange={(e) => setPassword(e.target.value)}
                onFocus={(e) => {
                  e.target.style.border = "1px solid #58a6ff";
                }}
                onBlur={(e) => {
                  e.target.style.border = "1px solid #30363d";
                }}
                style={adminInputStyle}
              />
            </div>

            <div style={roleFieldStyle}>
              <label style={filterLabelStyle}>Role</label>
              <select
                value={role}
                onChange={(e) => setRole(e.target.value)}
                style={{
                  ...adminInputStyle,
                  cursor: "pointer",
                }}
              >
                <option value="viewer">Auditor</option>
                <option value="analyst">Analyst</option>
              </select>
            </div>
          </div>

          <div style={buttonRowStyle}>
            <button
              type="submit"
              disabled={submitting}
              style={{
                ...actionButtonStyle,
                opacity: submitting ? 0.65 : 1,
                cursor: submitting ? "not-allowed" : "pointer",
              }}
            >
              {submitting ? "Creating..." : "Create User"}
            </button>
          </div>
        </form>

        {loading ? (
          <p style={emptyTextStyle}>Loading users...</p>
        ) : users.length === 0 ? (
          <p style={emptyTextStyle}>No users found.</p>
        ) : (
          <div style={tableSectionStyle}>
            <div style={tableMetaStyle}>
              <span style={tableMetaLabelStyle}>Users</span>
              <span style={tableMetaCountStyle}>{users.length}</span>
            </div>
            <table style={tableStyle}>
              <thead>
                <tr>
                  <th style={{ ...headerCellStyle, width: "28%" }}>Username</th>
                  <th style={{ ...headerCellStyle, width: "16%" }}>Role</th>
                  <th style={{ ...headerCellStyle, width: "16%" }}>Status</th>
                  <th style={{ ...headerCellStyle, width: "24%" }}>Created</th>
                  <th style={{ ...headerCellStyle, width: "16%" }}>Action</th>
                </tr>
              </thead>
              <tbody>
                {users.map((user) => (
                  <React.Fragment key={user.username}>
                    <tr style={rowStyle}>
                      <td style={bodyCellStyle}>{user.username}</td>
                      <td style={bodyCellStyle}>
                        <div style={roleControlStyle}>
                          <select
                            value={pendingRoles[user.username] || user.role}
                            onChange={(e) =>
                              setPendingRoles((prev) => ({
                                ...prev,
                                [user.username]: e.target.value,
                              }))
                            }
                            style={compactSelectStyle}
                          >
                            <option value="viewer">Auditor</option>
                            <option value="analyst">Analyst</option>
                          </select>
                          <button
                            type="button"
                            onClick={() => handleRoleUpdate(user.username)}
                            disabled={
                              roleUpdating === user.username ||
                              (pendingRoles[user.username] || user.role) === user.role
                            }
                            style={{
                              ...secondaryActionButtonStyle,
                              opacity:
                                roleUpdating === user.username ||
                                (pendingRoles[user.username] || user.role) === user.role
                                  ? 0.55
                                  : 1,
                              cursor:
                                roleUpdating === user.username ||
                                (pendingRoles[user.username] || user.role) === user.role
                                  ? "not-allowed"
                                  : "pointer",
                            }}
                          >
                            {roleUpdating === user.username ? "Saving..." : "Save"}
                          </button>
                        </div>
                      </td>
                      <td style={bodyCellStyle}>
                        <AdminStatusBadge isActive={user.is_active} />
                      </td>
                      <td style={{ ...bodyCellStyle, ...createdCellStyle }} title={user.created_at}>
                        {formatCreatedAt(user.created_at)}
                      </td>
                      <td style={bodyCellStyle}>
                        <div style={rowActionsStyle}>
                          <button
                            type="button"
                            onClick={() => handleStatusUpdate(user.username, !user.is_active)}
                            disabled={statusUpdating === user.username}
                            style={{
                              ...toggleButtonStyle,
                              opacity: statusUpdating === user.username ? 0.65 : 1,
                              cursor: statusUpdating === user.username ? "not-allowed" : "pointer",
                            }}
                          >
                            {statusUpdating === user.username
                              ? "Updating..."
                              : user.is_active
                              ? "Deactivate"
                              : "Activate"}
                          </button>
                          <button
                            type="button"
                            onClick={() => {
                              if (passwordResetTarget === user.username) {
                                setPasswordResetTarget("");
                                setPasswordResetValue("");
                              } else {
                                setPasswordResetTarget(user.username);
                                setPasswordResetValue("");
                              }
                            }}
                            style={secondaryActionButtonStyle}
                          >
                            Reset Password
                          </button>
                        </div>
                      </td>
                    </tr>
                    {passwordResetTarget === user.username && (
                      <tr style={rowStyle}>
                        <td colSpan="5" style={inlineResetCellStyle}>
                          <div style={inlineResetPanelStyle}>
                            <div style={inlineResetLabelStyle}>
                              Set a new password for <strong>{user.username}</strong>
                            </div>
                            <div style={inlineResetRowStyle}>
                              <input
                                className="admin-users-input"
                                type="password"
                                value={passwordResetValue}
                                placeholder="Enter new password"
                                autoComplete="new-password"
                                onChange={(e) => setPasswordResetValue(e.target.value)}
                                onFocus={(e) => {
                                  e.target.style.border = "1px solid #58a6ff";
                                }}
                                onBlur={(e) => {
                                  e.target.style.border = "1px solid #30363d";
                                }}
                                style={adminInputStyle}
                              />
                              <button
                                type="button"
                                onClick={() => handlePasswordReset(user.username)}
                                disabled={passwordResetSubmitting === user.username}
                                style={{
                                  ...actionButtonStyle,
                                  opacity: passwordResetSubmitting === user.username ? 0.65 : 1,
                                  cursor: passwordResetSubmitting === user.username ? "not-allowed" : "pointer",
                                }}
                              >
                                {passwordResetSubmitting === user.username ? "Saving..." : "Save Password"}
                              </button>
                              <button
                                type="button"
                                onClick={() => {
                                  setPasswordResetTarget("");
                                  setPasswordResetValue("");
                                }}
                                style={secondaryActionButtonStyle}
                              >
                                Cancel
                              </button>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      </section>
    </>
  );
}

const panelContentStyle = {
  padding: "24px 20px 22px",
};

const formSectionStyle = {
  paddingTop: "2px",
  paddingBottom: "2px",
  borderTop: "1px solid #21262d",
  marginTop: "4px",
  paddingTop: "20px",
  display: "flex",
  flexDirection: "column",
  gap: "14px",
  maxWidth: "640px",
  marginBottom: "24px",
};

const formInputsRowStyle = {
  display: "flex",
  alignItems: "stretch",
  gap: "12px",
  flexWrap: "wrap",
};

const formFieldStyle = {
  display: "flex",
  flexDirection: "column",
  gap: "6px",
  flex: "1 1 220px",
  minWidth: "180px",
};

const roleFieldStyle = {
  display: "flex",
  flexDirection: "column",
  gap: "6px",
  flex: "0 0 150px",
  minWidth: "140px",
};

const buttonRowStyle = {
  display: "flex",
  justifyContent: "flex-end",
};

const adminInputStyle = {
  backgroundColor: "#0d1117",
  color: "#e6edf3",
  border: "1px solid #30363d",
  borderRadius: "10px",
  padding: "12px",
  outline: "none",
  width: "100%",
  fontSize: "14px",
  minWidth: "0",
  boxSizing: "border-box",
  WebkitAppearance: "none",
  MozAppearance: "none",
  appearance: "none",
};

const feedbackStyle = {
  marginBottom: "20px",
  padding: "10px 12px",
  borderRadius: "8px",
  fontSize: "13px",
  fontWeight: "600",
};

const successFeedbackStyle = {
  backgroundColor: "rgba(34, 197, 94, 0.12)",
  border: "1px solid rgba(34, 197, 94, 0.28)",
  color: "#86efac",
};

const errorFeedbackStyle = {
  backgroundColor: "rgba(239, 68, 68, 0.12)",
  border: "1px solid rgba(239, 68, 68, 0.28)",
  color: "#fca5a5",
};

const actionButtonStyle = {
  padding: "10px 16px",
  borderRadius: "9px",
  border: "1px solid #30363d",
  backgroundColor: "#0d1117",
  color: "#e6edf3",
  fontSize: "13px",
  fontWeight: "700",
  whiteSpace: "nowrap",
};

const tableSectionStyle = {
  marginTop: "24px",
  borderTop: "1px solid #21262d",
  paddingTop: "20px",
};

const tableMetaStyle = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: "12px",
  marginBottom: "12px",
};

const tableMetaLabelStyle = {
  color: "#8b949e",
  fontSize: "12px",
  fontWeight: "700",
  letterSpacing: "0.08em",
  textTransform: "uppercase",
};

const sectionLabelStyle = {
  margin: "0 0 8px 0",
  color: "#8b949e",
  fontSize: "10px",
  fontWeight: "700",
  letterSpacing: "0.14em",
  textTransform: "uppercase",
};

const tableMetaCountStyle = {
  color: "#c9d1d9",
  fontSize: "12px",
  fontWeight: "700",
};

const tableStyle = {
  width: "100%",
  minWidth: "720px",
  borderCollapse: "collapse",
  overflowX: "auto",
};

const headerCellStyle = {
  textAlign: "left",
  padding: "12px 14px",
  color: "#8b949e",
  fontSize: "12px",
  fontWeight: "700",
  letterSpacing: "0.04em",
  textTransform: "uppercase",
  borderBottom: "1px solid #30363d",
};

const bodyCellStyle = {
  padding: "14px",
  color: "#e6edf3",
  borderBottom: "1px solid #30363d",
  fontSize: "14px",
  verticalAlign: "middle",
};

const rowStyle = {
  backgroundColor: "#161b22",
};

const toggleButtonStyle = {
  padding: "7px 12px",
  borderRadius: "9px",
  border: "1px solid #30363d",
  backgroundColor: "#0d1117",
  color: "#c9d1d9",
  fontSize: "12px",
  fontWeight: "700",
  whiteSpace: "nowrap",
};

const secondaryActionButtonStyle = {
  padding: "7px 12px",
  borderRadius: "9px",
  border: "1px solid #30363d",
  backgroundColor: "#161b22",
  color: "#c9d1d9",
  fontSize: "12px",
  fontWeight: "700",
  whiteSpace: "nowrap",
};

const rowActionsStyle = {
  display: "flex",
  alignItems: "center",
  gap: "8px",
  flexWrap: "wrap",
};

const roleControlStyle = {
  display: "flex",
  alignItems: "center",
  gap: "8px",
  flexWrap: "wrap",
};

const compactSelectStyle = {
  backgroundColor: "#0d1117",
  color: "#e6edf3",
  border: "1px solid #30363d",
  borderRadius: "9px",
  padding: "7px 10px",
  fontSize: "12px",
  fontWeight: "600",
};

const inlineResetCellStyle = {
  padding: "0 14px 14px",
  borderBottom: "1px solid #30363d",
};

const inlineResetPanelStyle = {
  backgroundColor: "#0d1117",
  border: "1px solid #30363d",
  borderRadius: "10px",
  padding: "12px",
};

const inlineResetLabelStyle = {
  color: "#8b949e",
  fontSize: "12px",
  marginBottom: "10px",
};

const inlineResetRowStyle = {
  display: "flex",
  alignItems: "center",
  gap: "10px",
  flexWrap: "wrap",
};

const createdCellStyle = {
  maxWidth: "180px",
  fontSize: "12px",
  color: "#8b949e",
  whiteSpace: "nowrap",
  overflow: "hidden",
  textOverflow: "ellipsis",
};

const emptyTextStyle = {
  margin: 0,
  color: "#8b949e",
  fontSize: "14px",
};

export default AdminUsersPanel;
