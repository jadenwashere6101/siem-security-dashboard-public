import React, { useCallback, useEffect, useState, useMemo, useRef } from "react";

import DashboardSection from "./components/DashboardSection";
import AdminUsersPanel from "./components/AdminUsersPanel";
import AuditLogPanel from "./components/AuditLogPanel";
import DetectionRulesPanel from "./components/DetectionRulesPanel";
import IncidentsPanel from "./components/IncidentsPanel";
import ApprovalsPanel from "./components/ApprovalsPanel";
import SoarQueuePanel from "./components/SoarQueuePanel";
import PlaybooksPanel from "./components/PlaybooksPanel";
import IntegrationStatusPanel from "./components/IntegrationStatusPanel";
import SoarMetricsDashboard from "./components/SoarMetricsDashboard";
import DeadLettersPanel from "./components/DeadLettersPanel";
import SocCommandCenter from "./components/SocCommandCenter";
import ThreatHuntPanel from "./components/ThreatHuntPanel";
import BlocklistManagerPanel from "./components/BlocklistManagerPanel";
import SidebarLayout from "./components/SidebarLayout";
import {
  readStoredSessionIdentity,
  writeStoredSessionIdentity,
} from "./utils/sessionIdentity";
import {
  buildAlertMetrics,
  buildAlertTimelineData,
  buildTopIPChartData,
  filterAlerts,
  sortAlerts,
} from "./utils/alertDashboardData";
import { updateAlertStatusRequest } from "./services/alertStatusService";
import { loadAlerts } from "./services/alertsService";
import {
  loadCurrentSession,
  loginToDashboard,
  logoutFromDashboard,
} from "./services/authService";
import { isSectionVisible, sectionsConfig } from "./utils/sectionsConfig";
import packageJson from "../package.json";

function App() {
  const [alerts, setAlerts] = useState([]);
  const [searchTerm, setSearchTerm] = useState("");
  const [sourceFilter, setSourceFilter] = useState("all");
  const [severityFilter, setSeverityFilter] = useState("");
  const [selectedAlertId, setSelectedAlertId] = useState(null);
  const [statusFilter, setStatusFilter] = useState("");
  const [sortOption, setSortOption] = useState("newest");
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [currentUsername, setCurrentUsername] = useState(null);
  const [userRole, setUserRole] = useState(null);
  const [activeSection, setActiveSection] = useState("dashboard");
  const [authLoading, setAuthLoading] = useState(true);
  const [loginUsername, setLoginUsername] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [loginError, setLoginError] = useState("");
  const [sessionNotice, setSessionNotice] = useState("");
  const previousSessionRef = useRef({
    authenticated: false,
    username: null,
    role: null,
  });
  const hasCheckedAuthRef = useRef(false);
  const alertsTableRef = useRef(null);
  const pendingAlertsFocusRef = useRef(false);

  const checkAuth = async () => {
    try {
      const data = await loadCurrentSession();
      const authenticated = !!data.authenticated;
      const nextUsername = authenticated ? data.user || null : null;
      const nextRole = authenticated ? data.role || null : null;
      const previousSession = hasCheckedAuthRef.current
        ? previousSessionRef.current
        : readStoredSessionIdentity() || previousSessionRef.current;

      if (
        hasCheckedAuthRef.current &&
        previousSession.authenticated &&
        authenticated &&
        (previousSession.username !== nextUsername || previousSession.role !== nextRole)
      ) {
        setSessionNotice("Session changed. Permissions updated.");
      }

      setIsAuthenticated(authenticated);
      setCurrentUsername(nextUsername);
      setUserRole(nextRole);
      previousSessionRef.current = {
        authenticated,
        username: nextUsername,
        role: nextRole,
      };
      writeStoredSessionIdentity({
        authenticated,
        username: nextUsername,
        role: nextRole,
      });
      hasCheckedAuthRef.current = true;

      if (authenticated) {
        await fetchAlerts();
      }
    } catch (err) {
      console.error("Error checking auth:", err);
      setIsAuthenticated(false);
      setCurrentUsername(null);
      setUserRole(null);
      writeStoredSessionIdentity(null);
    } finally {
      setAuthLoading(false);
    }
  };

  const fetchAlerts = useCallback(async () => {
    if (!isAuthenticated) return;

    try {
      const data = await loadAlerts();

      setAlerts(Array.isArray(data) ? data : []);
    } catch (err) {
      console.error("Error fetching alerts:", err);
      setAlerts([]);
    }
  }, [isAuthenticated]);

  const handleLogin = async (e) => {
    e.preventDefault();
    setLoginError("");

    try {
      await loginToDashboard(loginUsername, loginPassword);
      await checkAuth();
    } catch (err) {
      console.error("Login error:", err);
      setLoginError(err.message || "Login failed");
      setIsAuthenticated(false);
      setCurrentUsername(null);
      setUserRole(null);
      writeStoredSessionIdentity(null);
    }
  };

  const handleLogout = async () => {
    try {
      await logoutFromDashboard();
    } catch (err) {
      console.error("Logout error:", err);
    } finally {
      setIsAuthenticated(false);
      setCurrentUsername(null);
      setUserRole(null);
      setActiveSection("dashboard");
      setSessionNotice("");
      setAlerts([]);
      writeStoredSessionIdentity(null);
    }
  };

  useEffect(() => {
    checkAuth();
  }, []);

  useEffect(() => {
    if (!isAuthenticated) return;

    fetchAlerts();
    const interval = setInterval(() => {
      fetchAlerts();
    }, 5000);

    return () => clearInterval(interval);
  }, [isAuthenticated, fetchAlerts]);

  useEffect(() => {
    if (!sessionNotice) return;

    const timeout = setTimeout(() => {
      setSessionNotice("");
    }, 5000);

    return () => clearTimeout(timeout);
  }, [sessionNotice]);

  useEffect(() => {
    if (!pendingAlertsFocusRef.current || activeSection !== "dashboard") {
      return;
    }

    alertsTableRef.current?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
    pendingAlertsFocusRef.current = false;
  }, [activeSection, searchTerm]);

  const filteredAlerts = useMemo(() => {
    return filterAlerts(alerts, {
      searchTerm,
      severityFilter,
      statusFilter,
      sourceFilter,
    });
  }, [alerts, searchTerm, severityFilter, statusFilter, sourceFilter]);

  const sortedAlerts = useMemo(() => {
    return sortAlerts(filteredAlerts, sortOption);
  }, [filteredAlerts, sortOption]);

  const isSuperAdmin = userRole === "super_admin";
  const isAnalyst = userRole === "analyst";
  const canTakeAlertActions = isSuperAdmin || isAnalyst;
  const roleFlags = useMemo(
    () => ({ isSuperAdmin, isAnalyst, canTakeAlertActions }),
    [isSuperAdmin, isAnalyst, canTakeAlertActions]
  );
  const displayRoleLabel =
    userRole === "super_admin"
      ? "Super Admin"
      : userRole === "analyst"
      ? "Analyst"
      : userRole === "viewer"
      ? "Auditor"
      : userRole || "unknown";

  const handleUpdateStatus = async (id, status) => {
    try {
      await updateAlertStatusRequest(id, status);

      setAlerts((prevAlerts) =>
        prevAlerts.map((alert) =>
          alert.id === id ? { ...alert, status } : alert
        )
      );

      return { ok: true };
    } catch (err) {
      console.error("Failed to update status", err);
      return {
        ok: false,
        message: err.message || "Failed to update alert status",
      };
    }
  };

  const handleViewRelatedAlerts = (sourceIp) => {
    pendingAlertsFocusRef.current = true;
    setSearchTerm(sourceIp || "");
    setActiveSection("dashboard");
    setSelectedAlertId(null);
  };


  const metrics = useMemo(() => {
    return buildAlertMetrics(filteredAlerts);
  }, [filteredAlerts]);


  const topIPChartData = useMemo(() => {
    return buildTopIPChartData(filteredAlerts);
  }, [filteredAlerts]);

  const alertTimelineData = useMemo(() => {
    return buildAlertTimelineData(filteredAlerts);
  }, [filteredAlerts]);

  const getSeverityBadgeStyle = (severity) => {
    if (severity === "high") {
      return {
        ...severityBadgeBase,
        color: "#f85149",
        border: "1px solid rgba(248, 81, 73, 0.35)",
        backgroundColor: "rgba(248, 81, 73, 0.10)",
      };
    }

    if (severity === "medium") {
      return {
        ...severityBadgeBase,
        color: "#d18616",
        border: "1px solid rgba(209, 134, 22, 0.35)",
        backgroundColor: "rgba(209, 134, 22, 0.10)",
      };
    }

    if (severity === "low") {
      return {
        ...severityBadgeBase,
        color: "#3fb950",
        border: "1px solid rgba(63, 185, 80, 0.35)",
        backgroundColor: "rgba(63, 185, 80, 0.10)",
      };
    }

    return {
      ...severityBadgeBase,
      color: "#8b949e",
      border: "1px solid #30363d",
      backgroundColor: "#161b22",
    };
  };

  if (authLoading) {
    return (
      <div
        style={{
          minHeight: "100vh",
          backgroundColor: "#0b1020",
          color: "white",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontFamily: "Arial, sans-serif",
        }}
      >
        Checking authentication...
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <div
        style={{
          minHeight: "100vh",
          backgroundColor: "#0b1020",
          color: "white",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: "20px",
          fontFamily: "Arial, sans-serif",
        }}
      >
        <form
          onSubmit={handleLogin}
          style={{
            width: "100%",
            maxWidth: "400px",
            backgroundColor: "#111827",
            border: "1px solid #1f2937",
            borderRadius: "12px",
            padding: "24px",
            boxShadow: "0 10px 30px rgba(0,0,0,0.35)",
          }}
        >
          <h2 style={{ marginTop: 0, marginBottom: "8px" }}>SIEM Dashboard Login</h2>
          <p style={{ marginTop: 0, marginBottom: "20px", color: "#9ca3af" }}>
            Sign in to access alerts and response actions.
          </p>

          <label
            htmlFor="login-username"
            style={{ display: "block", marginBottom: "6px", fontSize: "14px" }}
          >
            Username
          </label>
          <input
            id="login-username"
            type="text"
            value={loginUsername}
            onChange={(e) => setLoginUsername(e.target.value)}
            style={{
              width: "100%",
              padding: "10px 12px",
              marginBottom: "16px",
              borderRadius: "8px",
              border: "1px solid #374151",
              backgroundColor: "#0f172a",
              color: "white",
              boxSizing: "border-box",
            }}
          />

          <label
            htmlFor="login-password"
            style={{ display: "block", marginBottom: "6px", fontSize: "14px" }}
          >
            Password
          </label>
          <input
            id="login-password"
            type="password"
            value={loginPassword}
            onChange={(e) => setLoginPassword(e.target.value)}
            style={{
              width: "100%",
              padding: "10px 12px",
              marginBottom: "16px",
              borderRadius: "8px",
              border: "1px solid #374151",
              backgroundColor: "#0f172a",
              color: "white",
              boxSizing: "border-box",
            }}
          />

          {loginError && (
            <div
              style={{
                marginBottom: "16px",
                padding: "10px 12px",
                borderRadius: "8px",
                backgroundColor: "rgba(239, 68, 68, 0.15)",
                border: "1px solid rgba(239, 68, 68, 0.35)",
                color: "#fca5a5",
                fontSize: "14px",
              }}
            >
              {loginError}
            </div>
          )}

          <button
            type="submit"
            style={{
              width: "100%",
              padding: "10px 12px",
              borderRadius: "8px",
              border: "none",
              backgroundColor: "#2563eb",
              color: "white",
              fontWeight: "600",
              cursor: "pointer",
            }}
          >
            Log In
          </button>
        </form>
      </div>
    );
  }

  return (
    <SidebarLayout
      sections={sectionsConfig}
      roleFlags={roleFlags}
      activeSectionId={activeSection}
      onNavigate={setActiveSection}
      title="SIEM Dashboard"
      eyebrow="SIEM"
      statusLabel="Operational"
      versionLabel={`v${packageJson.version}`}
      topBarActions={
        <div style={sessionActionsStyle}>
          <div style={identityBlockStyle}>
            <p style={identityLabelStyle}>Signed in as {currentUsername || "Unknown user"}</p>
            <span
              style={{
                ...roleBadgeStyle,
                ...(isSuperAdmin
                  ? superAdminRoleBadgeStyle
                  : isAnalyst
                  ? analystRoleBadgeStyle
                  : viewerRoleBadgeStyle),
              }}
            >
              {displayRoleLabel}
            </span>
          </div>
          <button onClick={handleLogout} style={logoutButtonStyle}>
            Switch Account / Logout
          </button>
        </div>
      }
    >
      {sessionNotice && <div style={sessionNoticeStyle}>{sessionNotice}</div>}

        {activeSection === "dashboard" && isSectionVisible("dashboard", roleFlags) && (
          <DashboardSection
            metrics={metrics}
            topIPChartData={topIPChartData}
            alertTimelineData={alertTimelineData}
            sortedAlerts={sortedAlerts}
            alertsTableRef={alertsTableRef}
            canTakeAlertActions={canTakeAlertActions}
            setAlerts={setAlerts}
            searchTerm={searchTerm}
            setSearchTerm={setSearchTerm}
            sortOption={sortOption}
            setSortOption={setSortOption}
            severityFilter={severityFilter}
            setSeverityFilter={setSeverityFilter}
            sourceFilter={sourceFilter}
            setSourceFilter={setSourceFilter}
            selectedAlertId={selectedAlertId}
            setSelectedAlertId={setSelectedAlertId}
            getSeverityBadgeStyle={getSeverityBadgeStyle}
            onUpdateStatus={handleUpdateStatus}
            statusFilter={statusFilter}
            setStatusFilter={setStatusFilter}
            metricsGridStyle={metricsGridStyle}
            metricCardStyle={metricCardStyle}
            metricLabelStyle={metricLabelStyle}
            metricValueStyle={metricValueStyle}
            chartsGridStyle={chartsGridStyle}
            tooltipStyle={tooltipStyle}
            tooltipLabelStyle={tooltipLabelStyle}
            tooltipItemStyle={tooltipItemStyle}
            cardStyle={cardStyle}
            cardHeaderStyle={cardHeaderStyle}
            cardTitleStyle={cardTitleStyle}
            cardSubtitleStyle={cardSubtitleStyle}
            filterWrapperStyle={filterWrapperStyle}
            filterLabelStyle={filterLabelStyle}
            selectStyle={selectStyle}
            emptyStateStyle={emptyStateStyle}
            emptyStateTextStyle={emptyStateTextStyle}
            tableWrapperStyle={tableWrapperStyle}
            tableStyle={tableStyle}
            headerCellStyle={headerCellStyle}
            bodyCellStyle={bodyCellStyle}
            monoCellStyle={monoCellStyle}
            tableRowStyle={tableRowStyle}
            expandedCellStyle={expandedCellStyle}
            expandedContentStyle={expandedContentStyle}
            expandedLabelStyle={expandedLabelStyle}
            expandedTextStyle={expandedTextStyle}
          />
        )}

        {activeSection === "threat-hunt" && isSectionVisible("threat-hunt", roleFlags) && (
          <ThreatHuntPanel
            cardStyle={cardStyle}
            cardHeaderStyle={cardHeaderStyle}
            cardTitleStyle={cardTitleStyle}
            cardSubtitleStyle={cardSubtitleStyle}
            filterLabelStyle={filterLabelStyle}
            selectStyle={selectStyle}
            onViewRelatedAlerts={handleViewRelatedAlerts}
          />
        )}

        {activeSection === "soc-command-center" && isSectionVisible("soc-command-center", roleFlags) && (
          <SocCommandCenter
            alerts={alerts}
            userRole={userRole}
            currentUsername={currentUsername}
            onNavigate={setActiveSection}
          />
        )}

        {activeSection === "blocklist" && isSectionVisible("blocklist", roleFlags) && (
          <BlocklistManagerPanel
            cardStyle={cardStyle}
            cardHeaderStyle={cardHeaderStyle}
            cardTitleStyle={cardTitleStyle}
            cardSubtitleStyle={cardSubtitleStyle}
            filterLabelStyle={filterLabelStyle}
            selectStyle={selectStyle}
          />
        )}

        {activeSection === "detection-rules" && isSectionVisible("detection-rules", roleFlags) && (
          <DetectionRulesPanel
            cardStyle={cardStyle}
            cardHeaderStyle={cardHeaderStyle}
            cardTitleStyle={cardTitleStyle}
            cardSubtitleStyle={cardSubtitleStyle}
          />
        )}

        {activeSection === "admin-users" && isSectionVisible("admin-users", roleFlags) && (
          <AdminUsersPanel
            cardStyle={cardStyle}
            cardHeaderStyle={cardHeaderStyle}
            cardTitleStyle={cardTitleStyle}
            cardSubtitleStyle={cardSubtitleStyle}
            filterLabelStyle={filterLabelStyle}
            selectStyle={selectStyle}
          />
        )}

        {activeSection === "admin-audit-logs" && isSectionVisible("admin-audit-logs", roleFlags) && (
          <AuditLogPanel
            cardStyle={cardStyle}
            cardHeaderStyle={cardHeaderStyle}
            cardTitleStyle={cardTitleStyle}
            cardSubtitleStyle={cardSubtitleStyle}
          />
        )}

        {activeSection === "soar-queue" && isSectionVisible("soar-queue", roleFlags) && (
          <SoarQueuePanel
            cardStyle={cardStyle}
            cardHeaderStyle={cardHeaderStyle}
            cardTitleStyle={cardTitleStyle}
            cardSubtitleStyle={cardSubtitleStyle}
            filterLabelStyle={filterLabelStyle}
            selectStyle={selectStyle}
          />
        )}

        {activeSection === "soar-incidents" && isSectionVisible("soar-incidents", roleFlags) && (
          <IncidentsPanel
            cardStyle={cardStyle}
            cardHeaderStyle={cardHeaderStyle}
            cardTitleStyle={cardTitleStyle}
            cardSubtitleStyle={cardSubtitleStyle}
            filterLabelStyle={filterLabelStyle}
            selectStyle={selectStyle}
            canTakeAlertActions={canTakeAlertActions}
          />
        )}

        {activeSection === "soar-approvals" && isSectionVisible("soar-approvals", roleFlags) && (
          <ApprovalsPanel
            cardStyle={cardStyle}
            cardHeaderStyle={cardHeaderStyle}
            cardTitleStyle={cardTitleStyle}
            cardSubtitleStyle={cardSubtitleStyle}
            filterLabelStyle={filterLabelStyle}
            selectStyle={selectStyle}
            userRole={userRole}
          />
        )}

        {activeSection === "soar-playbooks" && isSectionVisible("soar-playbooks", roleFlags) && (
          <PlaybooksPanel
            cardStyle={cardStyle}
            cardHeaderStyle={cardHeaderStyle}
            cardTitleStyle={cardTitleStyle}
            cardSubtitleStyle={cardSubtitleStyle}
            filterWrapperStyle={filterWrapperStyle}
            filterLabelStyle={filterLabelStyle}
            selectStyle={selectStyle}
            userRole={userRole}
          />
        )}

        {activeSection === "soar-integrations" && isSectionVisible("soar-integrations", roleFlags) && (
          <IntegrationStatusPanel
            cardStyle={cardStyle}
            cardHeaderStyle={cardHeaderStyle}
            cardTitleStyle={cardTitleStyle}
            cardSubtitleStyle={cardSubtitleStyle}
          />
        )}

        {activeSection === "soar-playbook-metrics" && isSectionVisible("soar-playbook-metrics", roleFlags) && (
          <SoarMetricsDashboard
            cardStyle={cardStyle}
            cardHeaderStyle={cardHeaderStyle}
            cardTitleStyle={cardTitleStyle}
            cardSubtitleStyle={cardSubtitleStyle}
            userRole={userRole}
          />
        )}

        {activeSection === "soar-operations" && isSectionVisible("soar-operations", roleFlags) && (
          <DeadLettersPanel
            cardStyle={cardStyle}
            cardHeaderStyle={cardHeaderStyle}
            cardTitleStyle={cardTitleStyle}
            cardSubtitleStyle={cardSubtitleStyle}
            filterLabelStyle={filterLabelStyle}
            selectStyle={selectStyle}
            userRole={userRole}
          />
        )}
    </SidebarLayout>
  );
}

const sessionActionsStyle = {
  display: "flex",
  alignItems: "center",
  gap: "12px",
  flexWrap: "wrap",
  justifyContent: "flex-end",
};

const identityBlockStyle = {
  display: "flex",
  alignItems: "center",
  gap: "10px",
  padding: "8px 12px",
  borderRadius: "999px",
  border: "1px solid #30363d",
  backgroundColor: "#161b22",
};

const identityLabelStyle = {
  margin: 0,
  color: "#c9d1d9",
  fontSize: "13px",
  fontWeight: "600",
};

const roleBadgeStyle = {
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  padding: "4px 9px",
  borderRadius: "999px",
  fontSize: "11px",
  fontWeight: "700",
  textTransform: "uppercase",
  letterSpacing: "0.04em",
};

const superAdminRoleBadgeStyle = {
  backgroundColor: "rgba(31, 111, 235, 0.16)",
  border: "1px solid rgba(88, 166, 255, 0.35)",
  color: "#93c5fd",
};

const analystRoleBadgeStyle = {
  backgroundColor: "rgba(217, 164, 65, 0.14)",
  border: "1px solid rgba(217, 164, 65, 0.32)",
  color: "#f5d487",
};

const viewerRoleBadgeStyle = {
  backgroundColor: "rgba(139, 148, 158, 0.12)",
  border: "1px solid rgba(139, 148, 158, 0.24)",
  color: "#c9d1d9",
};

const logoutButtonStyle = {
  padding: "8px 12px",
  borderRadius: "999px",
  border: "1px solid #30363d",
  backgroundColor: "#0d1117",
  color: "#c9d1d9",
  fontSize: "12px",
  fontWeight: "700",
  cursor: "pointer",
};

const sessionNoticeStyle = {
  marginTop: "12px",
  padding: "10px 12px",
  borderRadius: "10px",
  border: "1px solid rgba(88, 166, 255, 0.28)",
  backgroundColor: "rgba(31, 111, 235, 0.10)",
  color: "#c9d1d9",
  fontSize: "13px",
  fontWeight: "600",
};

const metricsGridStyle = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
  gap: "16px",
  marginBottom: "24px",
};

const chartsGridStyle = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(400px, 1fr))",
  gap: "20px",
  marginBottom: "24px",
};

const metricCardStyle = {
  backgroundColor: "#161b22",
  border: "1px solid #30363d",
  borderRadius: "12px",
  padding: "18px",
};

const metricLabelStyle = {
  margin: "0 0 10px 0",
  color: "#8b949e",
  fontSize: "14px",
};

const metricValueStyle = {
  margin: 0,
  color: "#e6edf3",
  fontSize: "28px",
  fontWeight: "700",
};

const cardStyle = {
  backgroundColor: "#161b22",
  border: "1px solid #30363d",
  borderRadius: "12px",
  overflow: "hidden",
};

const cardHeaderStyle = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "flex-end",
  gap: "16px",
  padding: "20px 20px 16px 20px",
  borderBottom: "1px solid #30363d",
  flexWrap: "wrap",
};

const cardTitleStyle = {
  margin: "0 0 6px 0",
  fontSize: "28px",
  color: "#e6edf3",
};

const cardSubtitleStyle = {
  margin: 0,
  color: "#8b949e",
  fontSize: "14px",
};

const filterWrapperStyle = {
  display: "flex",
  flexDirection: "column",
  gap: "6px",
};

const filterLabelStyle = {
  color: "#8b949e",
  fontSize: "13px",
  fontWeight: "600",
};

const selectStyle = {
  minWidth: "160px",
  padding: "10px 40px 10px 14px",
  backgroundColor: "#0d1117",
  color: "#e6edf3",
  border: "1px solid #30363d",
  borderRadius: "10px",
  fontSize: "14px",
  cursor: "pointer",
  appearance: "none",
  WebkitAppearance: "none",
  MozAppearance: "none",
  backgroundImage:
    "linear-gradient(45deg, transparent 50%, #8b949e 50%), linear-gradient(135deg, #8b949e 50%, transparent 50%)",
  backgroundPosition:
    "calc(100% - 18px) calc(50% - 3px), calc(100% - 12px) calc(50% - 3px)",
  backgroundSize: "6px 6px, 6px 6px",
  backgroundRepeat: "no-repeat",
};

const tableWrapperStyle = {
  overflowX: "auto",
};

const tableStyle = {
  width: "100%",
  borderCollapse: "collapse",
};

const headerCellStyle = {
  textAlign: "left",
  padding: "14px 16px",
  color: "#8b949e",
  fontSize: "13px",
  fontWeight: "700",
  letterSpacing: "0.03em",
  textTransform: "uppercase",
  borderBottom: "1px solid #30363d",
  backgroundColor: "#161b22",
};

const bodyCellStyle = {
  padding: "16px",
  borderBottom: "1px solid #30363d",
  color: "#e6edf3",
  verticalAlign: "top",
};

const monoCellStyle = {
  fontFamily: "'Courier New', monospace",
  fontSize: "14px",
  color: "#d29922",
};

const tableRowStyle = {
  backgroundColor: "#161b22",
};

const severityBadgeBase = {
  display: "inline-block",
  padding: "4px 10px",
  borderRadius: "999px",
  fontSize: "13px",
  fontWeight: "700",
  textTransform: "uppercase",
};

const emptyStateStyle = {
  padding: "24px 20px",
};

const emptyStateTextStyle = {
  margin: 0,
  color: "#8b949e",
};

const expandedCellStyle = {
  padding: "0",
  borderBottom: "1px solid #30363d",
  backgroundColor: "#0f1720",
};

const expandedContentStyle = {
  padding: "18px 20px",
};

const expandedLabelStyle = {
  margin: "0 0 12px 0",
  color: "#d29922",
  fontSize: "13px",
  fontWeight: "700",
  textTransform: "uppercase",
  letterSpacing: "0.05em",
};

const expandedTextStyle = {
  margin: "0 0 10px 0",
  color: "#e6edf3",
};

const tooltipStyle = {
  backgroundColor: "#0f172a",
  border: "1px solid #1f2937",
  borderWidth: "1px",
  borderRadius: "8px",
  color: "#cbd5f5",
  padding: "10px",
  boxShadow: "0 10px 24px rgba(0, 0, 0, 0.28)",
};

const tooltipLabelStyle = {
  color: "#e5e7eb",
  marginBottom: "4px",
};

const tooltipItemStyle = {
  color: "#cbd5f5",
  fontWeight: "600",
};

export default App;
