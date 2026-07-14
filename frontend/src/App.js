import React, { useCallback, useEffect, useState, useMemo, useRef } from "react";

import DashboardSection from "./components/DashboardSection";
import AdminUsersPanel from "./components/AdminUsersPanel";
import AuditLogPanel from "./components/AuditLogPanel";
import DetectionRulesPanel from "./components/DetectionRulesPanel";
import PfsenseIngestFiltersPanel from "./components/PfsenseIngestFiltersPanel";
import IncidentsPanel from "./components/IncidentsPanel";
import ApprovalsPanel from "./components/ApprovalsPanel";
import SoarQueuePanel from "./components/SoarQueuePanel";
import PlaybooksPanel from "./components/PlaybooksPanel";
import IntegrationStatusPanel from "./components/IntegrationStatusPanel";
import SoarMetricsDashboard from "./components/SoarMetricsDashboard";
import DeadLettersPanel from "./components/DeadLettersPanel";
import SocCommandCenter from "./components/SocCommandCenter";
import ThreatHuntPanel from "./components/ThreatHuntPanel";
import ResponseRegistryPanel from "./components/ResponseRegistryPanel";
import LiveLogsPanel from "./components/LiveLogsPanel";
import SourceHealthPanel from "./components/SourceHealthPanel";
import DetectionSimulatorPanel from "./components/DetectionSimulatorPanel";
import SettingsPanel from "./components/SettingsPanel";
import SidebarLayout from "./components/SidebarLayout";
import { UiSettingsProvider, useUiSettings } from "./context/UiSettingsContext";
import { ResponseSyncProvider } from "./context/ResponseSyncContext";
import {
  attentionNavTarget,
  buildRegistryNavigation,
} from "./utils/responseNavigation";
import {
  readStoredSessionIdentity,
  writeStoredSessionIdentity,
} from "./utils/sessionIdentity";
import { updateAlertStatusRequest } from "./services/alertStatusService";
import { loadAlertDashboardSummary, loadAlerts } from "./services/alertsService";
import {
  loadCurrentSession,
  loginToDashboard,
  logoutFromDashboard,
} from "./services/authService";
import { isSectionVisible, normalizeWorkspaceDestination, sectionsConfig } from "./utils/sectionsConfig";
import { getSeverityBadgeStyle } from "./utils/severityDisplay";
import {
  NAVIGATION_DESTINATIONS,
  WORKSPACE_TARGETS,
  createWorkspaceNavigationRequest,
} from "./utils/workspaceNavigation";
import { OPERATIONAL_SCOPE_SINCE_TUNING } from "./components/OperationalScopeToggle";
import packageJson from "../package.json";

const DEFAULT_ALERT_PAGE_SIZE = 50;
const MAX_ALERT_PAGE_SIZE = 100;

const createAlertRowsState = () => ({
  items: [],
  total: 0,
  limit: DEFAULT_ALERT_PAGE_SIZE,
  offset: 0,
  loading: true,
  refreshing: false,
  error: "",
  hasLoadedOnce: false,
});

const createAlertSummaryState = () => ({
  metrics: null,
  topSourceIps: [],
  timeline: [],
  mapMarkers: [],
  loading: true,
  refreshing: false,
  error: "",
  hasLoadedOnce: false,
});

function resolveAlertPageSize(rowsPerPage) {
  if (rowsPerPage === "all" || rowsPerPage === undefined || rowsPerPage === null) {
    return DEFAULT_ALERT_PAGE_SIZE;
  }
  const parsed = Number(rowsPerPage);
  if (!Number.isFinite(parsed) || parsed < 1) {
    return DEFAULT_ALERT_PAGE_SIZE;
  }
  return Math.min(parsed, MAX_ALERT_PAGE_SIZE);
}

function AppInner() {
  const [alertsState, setAlertsState] = useState(createAlertRowsState);
  const [alertSummaryState, setAlertSummaryState] = useState(createAlertSummaryState);
  const [searchTerm, setSearchTerm] = useState("");
  const [sourceFilter, setSourceFilter] = useState("all");
  const [severityFilter, setSeverityFilter] = useState("");
  const [selectedAlertId, setSelectedAlertId] = useState(null);
  const [statusFilter, setStatusFilter] = useState("");
  const [operationalScope, setOperationalScope] = useState(OPERATIONAL_SCOPE_SINCE_TUNING);
  const [sortOption, setSortOption] = useState("newest");
  const [alertOffset, setAlertOffset] = useState(0);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [currentUsername, setCurrentUsername] = useState(null);
  const [userRole, setUserRole] = useState(null);
  const { settings, updateSettings } = useUiSettings();
  const [activeSection, setActiveSection] = useState("dashboard");
  const [workspaceNavigationRequest, setWorkspaceNavigationRequest] = useState(null);
  const [registryInitialView, setRegistryInitialView] = useState("all");
  const [registryNavigationRequest, setRegistryNavigationRequest] = useState(null);
  const [approvalsInitialStatus, setApprovalsInitialStatus] = useState("all");
  const [playbooksInitialExecutionRequest, setPlaybooksInitialExecutionRequest] = useState(null);
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
  const hasAppliedLandingRef = useRef(false);
  const alertsTableRef = useRef(null);
  const alertPageSize = resolveAlertPageSize(settings.display?.rowsPerPage);
  const alertQuery = useMemo(
    () => ({
      searchTerm,
      severityFilter,
      statusFilter,
      sourceFilter,
      sortOption,
      operationalScope,
      limit: alertPageSize,
      offset: alertOffset,
    }),
    [
      alertOffset,
      alertPageSize,
      operationalScope,
      searchTerm,
      severityFilter,
      sourceFilter,
      sortOption,
      statusFilter,
    ]
  );

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
    } catch (err) {
      console.error("Error checking auth:", err);
      setIsAuthenticated(false);
      setCurrentUsername(null);
      setUserRole(null);
      setAlertsState(createAlertRowsState());
      setAlertSummaryState(createAlertSummaryState());
      writeStoredSessionIdentity(null);
    } finally {
      setAuthLoading(false);
    }
  };

  const fetchAlerts = useCallback(async ({ quiet = false } = {}) => {
    if (!isAuthenticated) return;

    if (quiet) {
      setAlertsState((current) => ({ ...current, refreshing: true, error: "" }));
      setAlertSummaryState((current) => ({ ...current, refreshing: true, error: "" }));
    } else {
      setAlertsState((current) => ({ ...current, loading: !current.hasLoadedOnce, error: "" }));
      setAlertSummaryState((current) => ({ ...current, loading: !current.hasLoadedOnce, error: "" }));
    }

    try {
      const [rowData, summaryData] = await Promise.all([
        loadAlerts(alertQuery),
        loadAlertDashboardSummary(alertQuery),
      ]);

      setAlertsState({
        items: Array.isArray(rowData?.items) ? rowData.items : [],
        total: Number(rowData?.total) || 0,
        limit: Number(rowData?.limit) || alertPageSize,
        offset: Number(rowData?.offset) || 0,
        loading: false,
        refreshing: false,
        error: "",
        hasLoadedOnce: true,
      });
      setAlertSummaryState({
        metrics: summaryData?.metrics || null,
        topSourceIps: Array.isArray(summaryData?.top_source_ips) ? summaryData.top_source_ips : [],
        timeline: Array.isArray(summaryData?.timeline) ? summaryData.timeline : [],
        mapMarkers: Array.isArray(summaryData?.map_markers) ? summaryData.map_markers : [],
        loading: false,
        refreshing: false,
        error: "",
        hasLoadedOnce: true,
      });
    } catch (err) {
      console.error("Error fetching alerts:", err);
      const message = err.message || "Unable to load dashboard alerts";
      setAlertsState((current) => ({
        ...current,
        items: current.hasLoadedOnce ? current.items : [],
        total: current.hasLoadedOnce ? current.total : 0,
        loading: false,
        refreshing: false,
        error: message,
      }));
      setAlertSummaryState((current) => ({
        ...current,
        metrics: current.hasLoadedOnce ? current.metrics : null,
        topSourceIps: current.hasLoadedOnce ? current.topSourceIps : [],
        timeline: current.hasLoadedOnce ? current.timeline : [],
        mapMarkers: current.hasLoadedOnce ? current.mapMarkers : [],
        loading: false,
        refreshing: false,
        error: message,
      }));
    }
  }, [alertPageSize, alertQuery, isAuthenticated]);

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
      setAlertsState(createAlertRowsState());
      setAlertSummaryState(createAlertSummaryState());
      writeStoredSessionIdentity(null);
    }
  };

  useEffect(() => {
    checkAuth();
  }, []);

  useEffect(() => {
    if (!isAuthenticated) return;

    fetchAlerts();
    if (settings.autoRefreshIntervalMs === 0) {
      return undefined;
    }

    const interval = setInterval(() => {
      fetchAlerts({ quiet: true });
    }, settings.autoRefreshIntervalMs);

    return () => clearInterval(interval);
  }, [isAuthenticated, fetchAlerts, settings.autoRefreshIntervalMs]);

  useEffect(() => {
    setAlertOffset(0);
  }, [alertPageSize, operationalScope, searchTerm, severityFilter, sourceFilter, sortOption, statusFilter]);

  useEffect(() => {
    if (!isAuthenticated) {
      hasAppliedLandingRef.current = false;
      return;
    }
    if (hasAppliedLandingRef.current) {
      return;
    }

    const visibilityFlags = {
      isSuperAdmin: userRole === "super_admin",
      isAnalyst: userRole === "analyst",
      canTakeAlertActions: userRole === "super_admin" || userRole === "analyst",
    };
    const legacyDestination = normalizeWorkspaceDestination(settings.defaultLandingPage);
    if (legacyDestination.registryView) {
      setRegistryInitialView(legacyDestination.registryView);
      setActiveSection(legacyDestination.sectionId);
      hasAppliedLandingRef.current = true;
      return;
    }
    const preferredSection = isSectionVisible(settings.defaultLandingPage, visibilityFlags)
      ? settings.defaultLandingPage
      : "dashboard";
    if (preferredSection === "response-registry") {
      setRegistryInitialView("all");
    }
    setActiveSection(preferredSection);
    hasAppliedLandingRef.current = true;
  }, [isAuthenticated, settings.defaultLandingPage, userRole]);

  useEffect(() => {
    if (!sessionNotice) return;

    const timeout = setTimeout(() => {
      setSessionNotice("");
    }, 5000);

    return () => clearTimeout(timeout);
  }, [sessionNotice]);

  const isSuperAdmin = userRole === "super_admin";
  const isAnalyst = userRole === "analyst";
  const canTakeAlertActions = isSuperAdmin || isAnalyst;
  const roleFlags = useMemo(
    () => ({ isSuperAdmin, isAnalyst, canTakeAlertActions }),
    [isSuperAdmin, isAnalyst, canTakeAlertActions]
  );

  const navigateWorkspace = useCallback((sectionId, options = {}) => {
    setWorkspaceNavigationRequest(createWorkspaceNavigationRequest(sectionId, options));
    setActiveSection(sectionId);
  }, []);

  const handleNavigate = useCallback((sectionId) => {
    const destination = normalizeWorkspaceDestination(sectionId);
    if (destination.registryView) {
      setRegistryInitialView(destination.registryView);
      navigateWorkspace(destination.sectionId, {
        destination: NAVIGATION_DESTINATIONS.element,
        targetKey: WORKSPACE_TARGETS.responseRegistry,
      });
      return;
    }
    if (destination.sectionId === "response-registry") {
      setRegistryInitialView("all");
    }
    navigateWorkspace(destination.sectionId);
  }, [navigateWorkspace]);

  const handleOpenResponseRegistry = useCallback((nav = {}) => {
    const target = buildRegistryNavigation(nav);
    setRegistryInitialView(target.view || "all");
    setRegistryNavigationRequest({
      ...target,
      nonce: Date.now(),
    });
    navigateWorkspace("response-registry", {
      destination: NAVIGATION_DESTINATIONS.element,
      targetKey: WORKSPACE_TARGETS.responseRegistry,
      context: target,
    });
  }, [navigateWorkspace]);

  const handleOpenAttentionTarget = useCallback((label) => {
    const target = attentionNavTarget(label);
    if (target.statusFilter) {
      setApprovalsInitialStatus(target.statusFilter);
    }
    navigateWorkspace(target.sectionId, target.statusFilter ? {
      destination: NAVIGATION_DESTINATIONS.element,
      targetKey: WORKSPACE_TARGETS.approvals,
      context: target,
    } : undefined);
  }, [navigateWorkspace]);

  const handleOpenPlaybookExecution = useCallback((executionId) => {
    if (executionId == null) return;
    setPlaybooksInitialExecutionRequest({
      executionId: Number(executionId),
      nonce: Date.now(),
    });
    navigateWorkspace("soar-playbooks");
  }, [navigateWorkspace]);

  const handleViewRelatedAlerts = (sourceIp) => {
    setSearchTerm(sourceIp || "");
    setSelectedAlertId(null);
    navigateWorkspace("dashboard", {
      destination: NAVIGATION_DESTINATIONS.element,
      targetKey: WORKSPACE_TARGETS.recentAlerts,
      context: { sourceIp: sourceIp || "" },
    });
  };

  const handleOpenIncidentWorkspace = useCallback(() => {
    handleNavigate("soar-incidents");
  }, [handleNavigate]);

  const displayRoleLabel =
    userRole === "super_admin"
      ? "Super Admin"
      : userRole === "analyst"
      ? "Analyst"
      : userRole === "viewer"
      ? "Auditor"
      : userRole || "unknown";
  const activeLiveLogsSection = sectionsConfig.find(
    (section) => section.id === activeSection && section.group === "live logs"
  );
  const landingPageOptions = useMemo(
    () =>
      sectionsConfig
        .filter((section) => section.id !== "settings" && isSectionVisible(section.id, roleFlags))
        .map((section) => ({ id: section.id, label: section.label })),
    [roleFlags]
  );

  const handleUpdateStatus = useCallback(async (id, status) => {
    try {
      await updateAlertStatusRequest(id, status);
      await fetchAlerts({ quiet: true });

      return { ok: true };
    } catch (err) {
      console.error("Failed to update status", err);
      return {
        ok: false,
        message: err.message || "Failed to update alert status",
      };
    }
  }, [fetchAlerts]);

  const metrics = useMemo(() => {
    if (!alertSummaryState.metrics) {
      return {
        totalAlerts: 0,
        highCount: 0,
        mediumCount: 0,
        lowCount: 0,
        uniqueIPs: 0,
      };
    }

    return {
      totalAlerts: Number(alertSummaryState.metrics.total_alerts) || 0,
      highCount: Number(alertSummaryState.metrics.high_count) || 0,
      mediumCount: Number(alertSummaryState.metrics.medium_count) || 0,
      lowCount: Number(alertSummaryState.metrics.low_count) || 0,
      uniqueIPs: Number(alertSummaryState.metrics.unique_source_ips) || 0,
    };
  }, [alertSummaryState.metrics]);

  const topIPChartData = useMemo(
    () => alertSummaryState.topSourceIps,
    [alertSummaryState.topSourceIps]
  );

  const alertTimelineData = useMemo(
    () => alertSummaryState.timeline,
    [alertSummaryState.timeline]
  );

  const alertMapMarkers = useMemo(
    () => alertSummaryState.mapMarkers,
    [alertSummaryState.mapMarkers]
  );

  const dashboardInitialLoading =
    (alertsState.loading || alertSummaryState.loading) &&
    (!alertsState.hasLoadedOnce || !alertSummaryState.hasLoadedOnce);
  const dashboardInitialError =
    !dashboardInitialLoading &&
    ((!alertsState.hasLoadedOnce && alertsState.error) ||
      (!alertSummaryState.hasLoadedOnce && alertSummaryState.error) ||
      "");
  const dashboardRefreshing = alertsState.refreshing || alertSummaryState.refreshing;
  const dashboardRefreshError =
    (alertsState.hasLoadedOnce || alertSummaryState.hasLoadedOnce) &&
    !dashboardRefreshing
      ? alertsState.error || alertSummaryState.error || ""
      : "";
  const alertPageEnd = Math.min(alertsState.offset + alertsState.items.length, alertsState.total);
  const canGoToPreviousAlertPage = alertsState.offset > 0;
  const canGoToNextAlertPage = alertsState.offset + alertsState.limit < alertsState.total;

  const handleNextAlertPage = useCallback(() => {
    if (!canGoToNextAlertPage) return;
    setAlertOffset((current) => current + alertPageSize);
  }, [alertPageSize, canGoToNextAlertPage]);

  const handlePreviousAlertPage = useCallback(() => {
    if (!canGoToPreviousAlertPage) return;
    setAlertOffset((current) => Math.max(0, current - alertPageSize));
  }, [alertPageSize, canGoToPreviousAlertPage]);

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
      onNavigate={handleNavigate}
      navigationRequest={workspaceNavigationRequest}
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
            mapMarkers={alertMapMarkers}
            alerts={alertsState.items}
            alertsTableRef={alertsTableRef}
            canTakeAlertActions={canTakeAlertActions}
            searchTerm={searchTerm}
            setSearchTerm={setSearchTerm}
            sortOption={sortOption}
            setSortOption={setSortOption}
            operationalScope={operationalScope}
            setOperationalScope={setOperationalScope}
            severityFilter={severityFilter}
            setSeverityFilter={setSeverityFilter}
            sourceFilter={sourceFilter}
            setSourceFilter={setSourceFilter}
            selectedAlertId={selectedAlertId}
            setSelectedAlertId={setSelectedAlertId}
            getSeverityBadgeStyle={(severity) => ({
              ...severityBadgeBase,
              ...getSeverityBadgeStyle(severity, settings.display?.severityColorPreset),
            })}
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
            displaySettings={settings.display}
            onOpenResponseRegistry={handleOpenResponseRegistry}
            onReviewIncident={handleOpenIncidentWorkspace}
            loading={dashboardInitialLoading}
            error={dashboardInitialError}
            refreshing={dashboardRefreshing}
            refreshError={dashboardRefreshError}
            onRetry={() => fetchAlerts({ quiet: false })}
            totalAlerts={alertsState.total}
            pageOffset={alertsState.offset}
            pageLimit={alertsState.limit}
            pageEnd={alertPageEnd}
            canGoToPreviousPage={canGoToPreviousAlertPage}
            canGoToNextPage={canGoToNextAlertPage}
            onPreviousPage={handlePreviousAlertPage}
            onNextPage={handleNextAlertPage}
            onRefreshAlerts={() => fetchAlerts({ quiet: true })}
          />
        )}

        {activeSection === "source-health" && isSectionVisible("source-health", roleFlags) && (
          <SourceHealthPanel
            pollIntervalMs={settings.autoRefreshIntervalMs}
            displaySettings={settings.display}
            onOpenLiveLogs={handleNavigate}
          />
        )}

        {activeSection === "threat-hunt" && isSectionVisible("threat-hunt", roleFlags) && (
          <ThreatHuntPanel
            displaySettings={settings.display}
            cardStyle={cardStyle}
            cardHeaderStyle={cardHeaderStyle}
            cardTitleStyle={cardTitleStyle}
            cardSubtitleStyle={cardSubtitleStyle}
            filterLabelStyle={filterLabelStyle}
            selectStyle={selectStyle}
            onViewRelatedAlerts={handleViewRelatedAlerts}
            onOpenResponseRegistry={handleOpenResponseRegistry}
          />
        )}

        {activeSection === "detection-simulator" && isSectionVisible("detection-simulator", roleFlags) && (
          <DetectionSimulatorPanel />
        )}

        {activeSection === "soc-command-center" && isSectionVisible("soc-command-center", roleFlags) && (
          <SocCommandCenter
            alerts={alertsState.items}
            userRole={userRole}
            currentUsername={currentUsername}
            onNavigate={handleNavigate}
            onOpenAttentionItem={handleOpenAttentionTarget}
            onOpenResponseRegistry={handleOpenResponseRegistry}
          />
        )}

        {activeSection === "response-registry" &&
          isSectionVisible("response-registry", roleFlags) && (
          <div
            data-navigation-target={WORKSPACE_TARGETS.responseRegistry}
            aria-label="Response Registry workspace"
          >
            <ResponseRegistryPanel
              cardStyle={cardStyle}
              cardHeaderStyle={cardHeaderStyle}
              cardTitleStyle={cardTitleStyle}
              cardSubtitleStyle={cardSubtitleStyle}
              filterLabelStyle={filterLabelStyle}
              selectStyle={selectStyle}
              canTakeAlertActions={canTakeAlertActions}
              initialView={registryInitialView}
              navigationRequest={registryNavigationRequest}
            />
          </div>
        )}

        {activeLiveLogsSection && isSectionVisible(activeLiveLogsSection.id, roleFlags) && (
          <LiveLogsPanel
            source={activeLiveLogsSection.source}
            label={activeLiveLogsSection.label}
            pollIntervalMs={settings.autoRefreshIntervalMs}
            displaySettings={settings.display}
            cardStyle={cardStyle}
            cardHeaderStyle={cardHeaderStyle}
            cardTitleStyle={cardTitleStyle}
            cardSubtitleStyle={cardSubtitleStyle}
          />
        )}

        {activeSection === "settings" && isSectionVisible("settings", roleFlags) && (
          <SettingsPanel
            settings={settings}
            landingPageOptions={landingPageOptions}
            onDefaultLandingPageChange={(defaultLandingPage) =>
              updateSettings((previous) => ({ ...previous, defaultLandingPage }))
            }
            onAutoRefreshIntervalChange={(autoRefreshIntervalMs) =>
              updateSettings((previous) => ({ ...previous, autoRefreshIntervalMs }))
            }
            onDisplaySettingsChange={(displayUpdate) =>
              updateSettings((previous) => ({
                ...previous,
                display: {
                  ...previous.display,
                  ...displayUpdate,
                },
              }))
            }
            onNotificationSettingsChange={(notificationUpdate) =>
              updateSettings((previous) => ({
                ...previous,
                notifications: {
                  ...previous.notifications,
                  ...notificationUpdate,
                },
              }))
            }
            cardStyle={cardStyle}
            cardHeaderStyle={cardHeaderStyle}
            cardTitleStyle={cardTitleStyle}
            cardSubtitleStyle={cardSubtitleStyle}
            filterLabelStyle={filterLabelStyle}
            selectStyle={selectStyle}
            sections={sectionsConfig}
            roleFlags={roleFlags}
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

        {activeSection === "pfsense-ingest-filters" && isSectionVisible("pfsense-ingest-filters", roleFlags) && (
          <PfsenseIngestFiltersPanel
            displaySettings={settings.display}
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
            onOpenResponseRegistry={handleOpenResponseRegistry}
          />
        )}

        {activeSection === "soar-incidents" && isSectionVisible("soar-incidents", roleFlags) && (
          <IncidentsPanel
            displaySettings={settings.display}
            cardStyle={cardStyle}
            cardHeaderStyle={cardHeaderStyle}
            cardTitleStyle={cardTitleStyle}
            cardSubtitleStyle={cardSubtitleStyle}
            filterLabelStyle={filterLabelStyle}
            selectStyle={selectStyle}
            canTakeAlertActions={canTakeAlertActions}
            onOpenResponseRegistry={handleOpenResponseRegistry}
            onViewRelatedAlerts={handleViewRelatedAlerts}
          />
        )}

        {activeSection === "soar-approvals" && isSectionVisible("soar-approvals", roleFlags) && (
          <div
            data-navigation-target={WORKSPACE_TARGETS.approvals}
            aria-label="SOAR Approvals workspace"
          >
            <ApprovalsPanel
              displaySettings={settings.display}
              cardStyle={cardStyle}
              cardHeaderStyle={cardHeaderStyle}
              cardTitleStyle={cardTitleStyle}
              cardSubtitleStyle={cardSubtitleStyle}
              filterLabelStyle={filterLabelStyle}
              selectStyle={selectStyle}
              userRole={userRole}
              initialStatusFilter={approvalsInitialStatus}
              onOpenResponseRegistry={handleOpenResponseRegistry}
            />
          </div>
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
            onOpenResponseRegistry={handleOpenResponseRegistry}
            initialExecutionRequest={playbooksInitialExecutionRequest}
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
            displaySettings={settings.display}
            cardStyle={cardStyle}
            cardHeaderStyle={cardHeaderStyle}
            cardTitleStyle={cardTitleStyle}
            cardSubtitleStyle={cardSubtitleStyle}
            filterLabelStyle={filterLabelStyle}
            selectStyle={selectStyle}
            userRole={userRole}
            onOpenPlaybookExecution={handleOpenPlaybookExecution}
            onOpenResponseRegistry={handleOpenResponseRegistry}
            onOpenPendingApprovals={() => handleOpenAttentionTarget("Pending approvals")}
            onOpenPlaybooks={() => handleNavigate("soar-playbooks")}
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

function App() {
  return (
    <UiSettingsProvider>
      <ResponseSyncProvider>
        <AppInner />
      </ResponseSyncProvider>
    </UiSettingsProvider>
  );
}

export default App;
