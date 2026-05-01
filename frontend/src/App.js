import React, { useEffect, useState, useMemo, useRef } from "react";

import DashboardSection from "./components/DashboardSection";
import AdminUsersPanel from "./components/AdminUsersPanel";
import AuditLogPanel from "./components/AuditLogPanel";
import DetectionRulesPanel from "./components/DetectionRulesPanel";
import ThreatHuntPanel from "./components/ThreatHuntPanel";
import BlocklistManagerPanel from "./components/BlocklistManagerPanel";
import { buildSiemPath } from "./utils/siemPath";
import {
  readStoredSessionIdentity,
  writeStoredSessionIdentity,
} from "./utils/sessionIdentity";

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
      const res = await fetch(buildSiemPath("/auth/me"), {
        credentials: "include",
      });

      const data = await res.json();
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

  const loginToDashboard = async (username, password) => {
    const res = await fetch(buildSiemPath("/login"), {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        username,
        password,
      }),
    });

    const data = await res.json();

    if (!res.ok) {
      throw new Error(data.error || "Login failed");
    }

    return data;
  };

  const fetchAlerts = async () => {
    if (!isAuthenticated) return;

    try {
      const res = await fetch(buildSiemPath("/alerts"), {
        credentials: "include",
      });

      if (!res.ok) {
        throw new Error("Failed to fetch alerts");
      }

      const data = await res.json();

      setAlerts(Array.isArray(data) ? data : []);
    } catch (err) {
      console.error("Error fetching alerts:", err);
      setAlerts([]);
    }
  };

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
      await fetch(buildSiemPath("/logout"), {
        method: "POST",
        credentials: "include",
      });
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
  }, [isAuthenticated]);

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
    return alerts.filter((alert) => {
      const matchesSearch =
        !searchTerm ||
        alert.source_ip?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        alert.message?.toLowerCase().includes(searchTerm.toLowerCase());

      const matchesSeverity =
        !severityFilter || severityFilter === "all" || alert.severity === severityFilter;

      const matchesStatus =
        !statusFilter || statusFilter === "all" || alert.status === statusFilter;

      const matchesSource =
        !sourceFilter || sourceFilter === "all" || (alert.source || "legacy") === sourceFilter;

      return matchesSearch && matchesSeverity && matchesStatus && matchesSource;
    });
  }, [alerts, searchTerm, severityFilter, statusFilter, sourceFilter]);

  const sortedAlerts = useMemo(() => {
    return [...filteredAlerts].sort((a, b) => {
      if (sortOption === "newest") {
        return new Date(b.created_at) - new Date(a.created_at);
      }

      if (sortOption === "oldest") {
        return new Date(a.created_at) - new Date(b.created_at);
      }

      if (sortOption === "severity") {
        const order = { critical: 4, high: 3, medium: 2, low: 1 };
        return (order[b.severity] || 0) - (order[a.severity] || 0);
      }

      return 0;
    });
  }, [filteredAlerts, sortOption]);

  const isSuperAdmin = userRole === "super_admin";
  const isAnalyst = userRole === "analyst";
  const canTakeAlertActions = isSuperAdmin || isAnalyst;
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
      const response = await fetch(buildSiemPath(`/alerts/${id}/status`), {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ status }),
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.message || errorData.error || "Failed to update alert status");
      }

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
    const highCount = filteredAlerts.filter((alert) => alert.severity === "high").length;
    const mediumCount = filteredAlerts.filter((alert) => alert.severity === "medium").length;
    const lowCount = filteredAlerts.filter((alert) => alert.severity === "low").length;
    const uniqueIPs = new Set(filteredAlerts.map((alert) => alert.source_ip)).size;

    return {
      totalAlerts: filteredAlerts.length,
      highCount,
      mediumCount,
      lowCount,
      uniqueIPs,
    };
  }, [filteredAlerts]);


  const topIPChartData = useMemo(() => {
    const counts = {};

    filteredAlerts.forEach((alert) => {
      counts[alert.source_ip] = (counts[alert.source_ip] || 0) + 1;
    });

    return Object.entries(counts)
      .map(([ip, count]) => ({
        name: ip,
        value: count,
      }))
      .sort((a, b) => b.value - a.value)
      .slice(0, 5);
  }, [filteredAlerts]);

  const alertTimelineData = useMemo(() => {
    const bucketCounts = new Map();
    const dayKeys = new Set();

    filteredAlerts.forEach((alert) => {
      if (!alert?.created_at) return;

      const createdAt = new Date(alert.created_at);
      if (Number.isNaN(createdAt.getTime())) return;

      const bucketStart = Date.UTC(
        createdAt.getUTCFullYear(),
        createdAt.getUTCMonth(),
        createdAt.getUTCDate(),
        createdAt.getUTCHours()
      );

      const dayKey = `${createdAt.getUTCFullYear()}-${createdAt.getUTCMonth()}-${createdAt.getUTCDate()}`;
      dayKeys.add(dayKey);
      bucketCounts.set(bucketStart, (bucketCounts.get(bucketStart) || 0) + 1);
    });

    const showDateInLabel = dayKeys.size > 1;

    return Array.from(bucketCounts.entries())
      .sort((a, b) => a[0] - b[0])
      .map(([bucketStart, count]) => {
        const bucketDate = new Date(bucketStart);
        const month = String(bucketDate.getUTCMonth() + 1).padStart(2, "0");
        const day = String(bucketDate.getUTCDate()).padStart(2, "0");
        const hour = String(bucketDate.getUTCHours()).padStart(2, "0");

        return {
          time: showDateInLabel
            ? `${month}/${day} ${hour}:00 UTC`
            : `${hour}:00 UTC`,
          count,
          bucketStart,
        };
      });
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

          <label style={{ display: "block", marginBottom: "6px", fontSize: "14px" }}>
            Username
          </label>
          <input
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

          <label style={{ display: "block", marginBottom: "6px", fontSize: "14px" }}>
            Password
          </label>
          <input
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
    <div style={pageStyle}>
      <div style={containerStyle}>
        <header style={headerStyle}>
          <div style={topBarStyle}>
            <div>
              <p style={eyebrowStyle}>SIEM</p>
              <h1 style={titleStyle}>SIEM Dashboard</h1>
            </div>
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
              <button
                onClick={handleLogout}
                style={logoutButtonStyle}
              >
                Switch Account / Logout
              </button>
            </div>
          </div>
          {sessionNotice && <div style={sessionNoticeStyle}>{sessionNotice}</div>}
        </header>
        <div style={sectionNavStyle}>
          <button
            type="button"
            onClick={() => setActiveSection("dashboard")}
            style={{
              ...sectionTabStyle,
              ...(activeSection === "dashboard" ? activeSectionTabStyle : inactiveSectionTabStyle),
            }}
          >
            Dashboard
          </button>
          {canTakeAlertActions && (
            <button
              type="button"
              onClick={() => setActiveSection("blocklist")}
              style={{
                ...sectionTabStyle,
                ...(activeSection === "blocklist" ? activeSectionTabStyle : inactiveSectionTabStyle),
              }}
            >
              Blocklist
            </button>
          )}
          {canTakeAlertActions && (
            <button
              type="button"
              onClick={() => setActiveSection("threat-hunt")}
              style={{
                ...sectionTabStyle,
                ...(activeSection === "threat-hunt" ? activeSectionTabStyle : inactiveSectionTabStyle),
              }}
            >
              Threat Hunt
            </button>
          )}
          {isSuperAdmin && (
            <button
              type="button"
              onClick={() => setActiveSection("administration")}
              style={{
                ...sectionTabStyle,
                ...(activeSection === "administration" ? activeSectionTabStyle : inactiveSectionTabStyle),
              }}
            >
              Administration
            </button>
          )}
        </div>

        {activeSection === "dashboard" && (
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

        {canTakeAlertActions && activeSection === "threat-hunt" && (
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

        {canTakeAlertActions && activeSection === "blocklist" && (
          <BlocklistManagerPanel
            cardStyle={cardStyle}
            cardHeaderStyle={cardHeaderStyle}
            cardTitleStyle={cardTitleStyle}
            cardSubtitleStyle={cardSubtitleStyle}
            filterLabelStyle={filterLabelStyle}
            selectStyle={selectStyle}
          />
        )}

        {isSuperAdmin && activeSection === "administration" && (
          <>
            <DetectionRulesPanel
              cardStyle={cardStyle}
              cardHeaderStyle={cardHeaderStyle}
              cardTitleStyle={cardTitleStyle}
              cardSubtitleStyle={cardSubtitleStyle}
            />
            <AdminUsersPanel
              cardStyle={cardStyle}
              cardHeaderStyle={cardHeaderStyle}
              cardTitleStyle={cardTitleStyle}
              cardSubtitleStyle={cardSubtitleStyle}
              filterLabelStyle={filterLabelStyle}
              selectStyle={selectStyle}
            />
            <AuditLogPanel
              cardStyle={cardStyle}
              cardHeaderStyle={cardHeaderStyle}
              cardTitleStyle={cardTitleStyle}
              cardSubtitleStyle={cardSubtitleStyle}
            />
          </>
        )}


          
         

      </div>
    </div>
  );
}

const pageStyle = {
  minHeight: "100vh",
  backgroundColor: "#0d1117",
  color: "#e6edf3",
  fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
};

const containerStyle = {
  maxWidth: "1400px",
  margin: "0 auto",
  padding: "18px 32px 32px",
};

const headerStyle = {
  marginBottom: "14px",
  paddingBottom: "10px",
  borderBottom: "1px solid #21262d",
};

const sectionNavStyle = {
  display: "flex",
  alignItems: "center",
  gap: "10px",
  marginBottom: "24px",
  flexWrap: "wrap",
};

const sectionTabStyle = {
  padding: "8px 14px",
  borderRadius: "999px",
  border: "1px solid #30363d",
  fontSize: "13px",
  fontWeight: "700",
  cursor: "pointer",
  transition: "background-color 120ms ease, border-color 120ms ease, color 120ms ease",
};

const activeSectionTabStyle = {
  backgroundColor: "#1f6feb",
  borderColor: "#1f6feb",
  color: "#ffffff",
};

const inactiveSectionTabStyle = {
  backgroundColor: "#0d1117",
  borderColor: "#30363d",
  color: "#c9d1d9",
};

const topBarStyle = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  gap: "12px",
  flexWrap: "wrap",
};

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

const eyebrowStyle = {
  margin: "0 0 2px 0",
  color: "#8b949e",
  fontSize: "10px",
  fontWeight: "700",
  letterSpacing: "0.14em",
  textTransform: "uppercase",
};

const titleStyle = {
  margin: 0,
  fontSize: "18px",
  fontWeight: "600",
  color: "#e6edf3",
  letterSpacing: "-0.01em",
};

const subtitleStyle = {
  margin: 0,
  color: "#8b949e",
  fontSize: "16px",
  maxWidth: "760px",
  lineHeight: "1.5",
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
