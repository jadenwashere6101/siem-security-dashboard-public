import React, { useCallback, useEffect, useState, useMemo, useRef } from "react";

import DashboardSection from "./components/DashboardSection";
import AdminUsersPanel from "./components/AdminUsersPanel";
import AuditLogPanel from "./components/AuditLogPanel";
import DetectionRulesPanel from "./components/DetectionRulesPanel";
import PfsenseIngestFiltersPanel from "./components/PfsenseIngestFiltersPanel";
import NotificationPolicyPanel from "./components/NotificationPolicyPanel";
import IncidentsPanel from "./components/IncidentsPanel";
import ApprovalsPanel from "./components/ApprovalsPanel";
import SoarQueuePanel from "./components/SoarQueuePanel";
import PlaybooksPanel from "./components/PlaybooksPanel";
import IntegrationStatusPanel from "./components/IntegrationStatusPanel";
import SoarMetricsDashboard from "./components/SoarMetricsDashboard";
import DeadLettersPanel from "./components/DeadLettersPanel";
import SocCommandCenter from "./components/SocCommandCenter";
import SeverityResponseMatrixPanel from "./components/SeverityResponseMatrixPanel";
import ThreatHuntPanel from "./components/ThreatHuntPanel";
import ResponseRegistryPanel from "./components/ResponseRegistryPanel";
import LiveLogsPanel from "./components/LiveLogsPanel";
import SourceHealthPanel from "./components/SourceHealthPanel";
import DetectionSimulatorPanel from "./components/DetectionSimulatorPanel";
import SettingsPanel from "./components/SettingsPanel";
import SidebarLayout from "./components/SidebarLayout";
import AiResponsePanel from "./components/AiResponsePanel";
import FloatingSiemChat from "./components/FloatingSiemChat";
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
import { requestAiChat, requestAiExplanation } from "./services/aiService";
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
const DEFAULT_ALERT_TIMELINE_RANGE = "7d";

const createAlertViewState = () => ({
  searchTerm: "",
  exactSourceIp: "",
  exactTargetIp: "",
  exactAlertId: null,
  sourceFilter: "all",
  severityFilter: "",
  statusFilter: "",
  operationalScope: OPERATIONAL_SCOPE_SINCE_TUNING,
  sortOption: "newest",
  timelineRange: DEFAULT_ALERT_TIMELINE_RANGE,
  offset: 0,
});

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
  timelineMeta: {
    range: DEFAULT_ALERT_TIMELINE_RANGE,
    bucket: "6 hours",
    windowStart: null,
  },
  mapMarkers: [],
  loading: true,
  refreshing: false,
  error: "",
  hasLoadedOnce: false,
});

function isAlertViewAtDefault(view) {
  const baseline = createAlertViewState();
  return (
    view.searchTerm === baseline.searchTerm &&
    view.exactSourceIp === baseline.exactSourceIp &&
    view.exactTargetIp === baseline.exactTargetIp &&
    view.exactAlertId === baseline.exactAlertId &&
    view.sourceFilter === baseline.sourceFilter &&
    view.severityFilter === baseline.severityFilter &&
    view.statusFilter === baseline.statusFilter &&
    view.operationalScope === baseline.operationalScope &&
    view.sortOption === baseline.sortOption &&
    view.timelineRange === baseline.timelineRange &&
    view.offset === baseline.offset
  );
}

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

function buildContextualAlertView(current, { sourceIp = "", targetIp = "", alertId = null } = {}) {
  return {
    ...current,
    searchTerm: "",
    exactSourceIp: sourceIp,
    exactTargetIp: targetIp,
    exactAlertId: alertId,
    sourceFilter: "all",
    severityFilter: "",
    statusFilter: "",
    offset: 0,
  };
}

function AppInner() {
  const [alertsState, setAlertsState] = useState(createAlertRowsState);
  const [alertSummaryState, setAlertSummaryState] = useState(createAlertSummaryState);
  const [alertView, setAlertView] = useState(createAlertViewState);
  const [alertsPendingLabel, setAlertsPendingLabel] = useState("");
  const [summaryPendingLabel, setSummaryPendingLabel] = useState("");
  const [selectedAlertId, setSelectedAlertId] = useState(null);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [currentUsername, setCurrentUsername] = useState(null);
  const [userRole, setUserRole] = useState(null);
  const { settings, updateSettings } = useUiSettings();
  const [activeSection, setActiveSection] = useState("dashboard");
  const [workspaceNavigationRequest, setWorkspaceNavigationRequest] = useState(null);
  const [registryInitialView, setRegistryInitialView] = useState("all");
  const [registryNavigationRequest, setRegistryNavigationRequest] = useState(null);
  const [approvalsInitialStatus, setApprovalsInitialStatus] = useState("all");
  const [approvalsInitialRequest, setApprovalsInitialRequest] = useState(null);
  const [incidentsInitialRequest, setIncidentsInitialRequest] = useState(null);
  const [playbooksInitialExecutionRequest, setPlaybooksInitialExecutionRequest] = useState(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [loginUsername, setLoginUsername] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [loginError, setLoginError] = useState("");
  const [sessionNotice, setSessionNotice] = useState("");
  const latestAlertRowsRequestRef = useRef(0);
  const latestAlertSummaryRequestRef = useRef(0);
  const aiRequestRef = useRef({ id: 0, controller: null, contextKey: "" });
  const previousSessionRef = useRef({
    authenticated: false,
    username: null,
    role: null,
  });
  const hasCheckedAuthRef = useRef(false);
  const hasAppliedLandingRef = useRef(false);
  const alertsTableRef = useRef(null);
  const [aiPanelState, setAiPanelState] = useState({
    status: "idle",
    title: "",
    response: null,
    error: "",
    stale: false,
    request: null,
  });
  const [aiChatHistory, setAiChatHistory] = useState([]);
  const applyAlertViewPatch = useCallback((patchOrUpdater, options = {}) => {
    const { resetOffset = true, clearExactPivots = true } = options;
    setAlertView((current) => {
      const patch =
        typeof patchOrUpdater === "function" ? patchOrUpdater(current) : patchOrUpdater || {};
      return {
        ...current,
        ...patch,
        ...(clearExactPivots
          ? {
              exactSourceIp: "",
              exactTargetIp: "",
              exactAlertId: null,
            }
          : null),
        offset:
          Object.hasOwn(patch, "offset") || !resetOffset
            ? patch.offset ?? current.offset
            : 0,
      };
    });
  }, []);

  const setSearchTerm = useCallback((value) => {
    setAlertsPendingLabel("Updating recent alerts…");
    setSummaryPendingLabel("Updating dashboard summary…");
    applyAlertViewPatch({ searchTerm: value }, { clearExactPivots: false });
  }, [applyAlertViewPatch]);

  const setSourceFilter = useCallback((value) => {
    setAlertsPendingLabel("Updating recent alerts…");
    setSummaryPendingLabel("Updating dashboard summary…");
    applyAlertViewPatch({ sourceFilter: value }, { clearExactPivots: false });
  }, [applyAlertViewPatch]);

  const setSeverityFilter = useCallback((value) => {
    setAlertsPendingLabel("Updating recent alerts…");
    setSummaryPendingLabel("Updating dashboard summary…");
    applyAlertViewPatch({ severityFilter: value }, { clearExactPivots: false });
  }, [applyAlertViewPatch]);

  const setStatusFilter = useCallback((value) => {
    setAlertsPendingLabel("Updating recent alerts…");
    setSummaryPendingLabel("Updating dashboard summary…");
    applyAlertViewPatch({ statusFilter: value }, { clearExactPivots: false });
  }, [applyAlertViewPatch]);

  const setOperationalScope = useCallback((value) => {
    setAlertsPendingLabel("Updating recent alerts…");
    setSummaryPendingLabel("Updating dashboard summary…");
    applyAlertViewPatch({ operationalScope: value }, { clearExactPivots: false });
  }, [applyAlertViewPatch]);

  const setSortOption = useCallback((value) => {
    setAlertsPendingLabel("Updating recent alerts…");
    applyAlertViewPatch({ sortOption: value }, { clearExactPivots: false });
  }, [applyAlertViewPatch]);

  const setTimelineRange = useCallback((value) => {
    setSummaryPendingLabel("Updating chart…");
    applyAlertViewPatch({ timelineRange: value }, { clearExactPivots: false });
  }, [applyAlertViewPatch]);

  const resetAlertView = useCallback(() => {
    setAlertsPendingLabel("Resetting filters…");
    setSummaryPendingLabel("Resetting dashboard summary…");
    setAlertView(createAlertViewState());
    setSelectedAlertId(null);
  }, []);

  const alertPageSize = resolveAlertPageSize(settings.display?.rowsPerPage);
  const alertQuery = useMemo(
    () => ({
      searchTerm: alertView.searchTerm,
      exactSourceIp: alertView.exactSourceIp,
      exactTargetIp: alertView.exactTargetIp,
      exactAlertId: alertView.exactAlertId,
      severityFilter: alertView.severityFilter,
      statusFilter: alertView.statusFilter,
      sourceFilter: alertView.sourceFilter,
      sortOption: alertView.sortOption,
      operationalScope: alertView.operationalScope,
      limit: alertPageSize,
      offset: alertView.offset,
    }),
    [alertPageSize, alertView]
  );

  const alertSummaryQuery = useMemo(
    () => ({
      searchTerm: alertView.searchTerm,
      exactSourceIp: alertView.exactSourceIp,
      exactTargetIp: alertView.exactTargetIp,
      exactAlertId: alertView.exactAlertId,
      severityFilter: alertView.severityFilter,
      statusFilter: alertView.statusFilter,
      sourceFilter: alertView.sourceFilter,
      sortOption: alertView.sortOption,
      operationalScope: alertView.operationalScope,
      timelineRange: alertView.timelineRange,
    }),
    [alertView]
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
      setAlertView(createAlertViewState());
      setAlertsState(createAlertRowsState());
      setAlertSummaryState(createAlertSummaryState());
      writeStoredSessionIdentity(null);
    } finally {
      setAuthLoading(false);
    }
  };

  const fetchAlertRows = useCallback(async ({ quiet = false } = {}) => {
    if (!isAuthenticated) return;
    const requestId = latestAlertRowsRequestRef.current + 1;
    latestAlertRowsRequestRef.current = requestId;

    if (quiet) {
      setAlertsState((current) => ({ ...current, refreshing: true, error: "" }));
    } else {
      setAlertsState((current) => ({
        ...current,
        loading: !current.hasLoadedOnce,
        refreshing: current.hasLoadedOnce,
        error: "",
      }));
    }

    try {
      const rowData = await loadAlerts(alertQuery);
      if (latestAlertRowsRequestRef.current !== requestId) {
        return;
      }

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
      setAlertsPendingLabel("");
    } catch (err) {
      if (latestAlertRowsRequestRef.current !== requestId) {
        return;
      }
      console.error("Error fetching alert rows:", err);
      const message = err.message || "Unable to load dashboard alerts";
      setAlertsState((current) => ({
        ...current,
        items: current.hasLoadedOnce ? current.items : [],
        total: current.hasLoadedOnce ? current.total : 0,
        loading: false,
        refreshing: false,
        error: message,
      }));
      setAlertsPendingLabel("");
    }
  }, [alertPageSize, alertQuery, isAuthenticated]);

  const fetchAlertSummary = useCallback(async ({ quiet = false } = {}) => {
    if (!isAuthenticated) return;
    const requestId = latestAlertSummaryRequestRef.current + 1;
    latestAlertSummaryRequestRef.current = requestId;

    if (quiet) {
      setAlertSummaryState((current) => ({ ...current, refreshing: true, error: "" }));
    } else {
      setAlertSummaryState((current) => ({
        ...current,
        loading: !current.hasLoadedOnce,
        refreshing: current.hasLoadedOnce,
        error: "",
      }));
    }

    try {
      const summaryData = await loadAlertDashboardSummary(alertSummaryQuery);
      if (latestAlertSummaryRequestRef.current !== requestId) {
        return;
      }

      setAlertSummaryState({
        metrics: summaryData?.metrics || null,
        topSourceIps: Array.isArray(summaryData?.top_source_ips) ? summaryData.top_source_ips : [],
        timeline: Array.isArray(summaryData?.timeline) ? summaryData.timeline : [],
        timelineMeta: {
          range: summaryData?.timeline_meta?.range || alertView.timelineRange,
          bucket: summaryData?.timeline_meta?.bucket || "6 hours",
          windowStart: summaryData?.timeline_meta?.window_start || null,
        },
        mapMarkers: Array.isArray(summaryData?.map_markers) ? summaryData.map_markers : [],
        loading: false,
        refreshing: false,
        error: "",
        hasLoadedOnce: true,
      });
      setSummaryPendingLabel("");
    } catch (err) {
      if (latestAlertSummaryRequestRef.current !== requestId) {
        return;
      }
      console.error("Error fetching alert dashboard summary:", err);
      const message = err.message || "Unable to load dashboard summary";
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
      setSummaryPendingLabel("");
    }
  }, [alertSummaryQuery, alertView.timelineRange, isAuthenticated]);

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
      setAlertView(createAlertViewState());
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
      setAlertView(createAlertViewState());
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
    fetchAlertRows();
  }, [fetchAlertRows, isAuthenticated]);

  useEffect(() => {
    if (!isAuthenticated) return;

    fetchAlertSummary();
  }, [fetchAlertSummary, isAuthenticated]);

  useEffect(() => {
    if (!isAuthenticated) return;

    if (settings.autoRefreshIntervalMs === 0) {
      return undefined;
    }

    const interval = setInterval(() => {
      fetchAlertRows({ quiet: true });
      fetchAlertSummary({ quiet: true });
    }, settings.autoRefreshIntervalMs);

    return () => clearInterval(interval);
  }, [fetchAlertRows, fetchAlertSummary, isAuthenticated, settings.autoRefreshIntervalMs]);

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

  const handleOpenIncident = useCallback((incidentId) => {
    if (incidentId == null) return;
    setIncidentsInitialRequest({
      incidentId: Number(incidentId),
      nonce: Date.now(),
    });
    navigateWorkspace("soar-incidents");
  }, [navigateWorkspace]);

  const handleOpenApproval = useCallback((approvalId) => {
    if (approvalId == null) return;
    setApprovalsInitialRequest({
      approvalId: Number(approvalId),
      nonce: Date.now(),
    });
    navigateWorkspace("soar-approvals", {
      destination: NAVIGATION_DESTINATIONS.element,
      targetKey: WORKSPACE_TARGETS.approvals,
    });
  }, [navigateWorkspace]);

  const handleOpenAlert = useCallback((alertId, sourceIp = "") => {
    if (alertId == null) return;
    setAlertsPendingLabel("Opening alert context…");
    setSummaryPendingLabel("Updating dashboard summary…");
    setAlertView((current) =>
      buildContextualAlertView(current, {
        alertId: Number(alertId),
      })
    );
    setSelectedAlertId(Number(alertId));
    navigateWorkspace("dashboard", {
      destination: NAVIGATION_DESTINATIONS.element,
      targetKey: WORKSPACE_TARGETS.recentAlerts,
      context: { alertId: Number(alertId), sourceIp: sourceIp || "" },
    });
  }, [navigateWorkspace]);

  const handleViewRelatedAlerts = useCallback((pivot) => {
    let nextPivot = {};
    if (typeof pivot === "string") {
      nextPivot = { sourceIp: pivot };
    } else if (pivot && typeof pivot === "object") {
      nextPivot = pivot;
    }
    const normalizedSourceIp = String(nextPivot.sourceIp || "").trim();
    const normalizedTargetIp = String(nextPivot.targetIp || "").trim();
    const normalizedAlertId =
      nextPivot.alertId == null || nextPivot.alertId === ""
        ? null
        : Number(nextPivot.alertId);
    let pendingLabel = "Updating recent alerts…";
    if (normalizedTargetIp) {
      pendingLabel = `Opening alerts for ${normalizedTargetIp}…`;
    } else if (normalizedSourceIp) {
      pendingLabel = `Opening alerts for ${normalizedSourceIp}…`;
    } else if (normalizedAlertId != null) {
      pendingLabel = `Opening linked alert #${normalizedAlertId}…`;
    }
    setAlertsPendingLabel(pendingLabel);
    setSummaryPendingLabel("Updating dashboard summary…");
    setAlertView((current) =>
      buildContextualAlertView(current, {
        sourceIp: normalizedSourceIp,
        targetIp: normalizedTargetIp,
        alertId: Number.isFinite(normalizedAlertId) ? normalizedAlertId : null,
      })
    );
    setSelectedAlertId(null);
    navigateWorkspace("dashboard", {
      destination: NAVIGATION_DESTINATIONS.element,
      targetKey: WORKSPACE_TARGETS.recentAlerts,
      context: {
        sourceIp: normalizedSourceIp,
        targetIp: normalizedTargetIp,
        alertId: Number.isFinite(normalizedAlertId) ? normalizedAlertId : null,
      },
    });
  }, [navigateWorkspace]);

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
      await Promise.all([fetchAlertRows({ quiet: true }), fetchAlertSummary({ quiet: true })]);

      return { ok: true };
    } catch (err) {
      console.error("Failed to update status", err);
      return {
        ok: false,
        message: err.message || "Failed to update alert status",
      };
    }
  }, [fetchAlertRows, fetchAlertSummary]);

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
  const alertTimelineMeta = useMemo(
    () => alertSummaryState.timelineMeta,
    [alertSummaryState.timelineMeta]
  );

  const alertMapMarkers = useMemo(
    () => alertSummaryState.mapMarkers,
    [alertSummaryState.mapMarkers]
  );

  const alertsBusy = alertsState.loading || alertsState.refreshing;
  const summaryBusy = alertSummaryState.loading || alertSummaryState.refreshing;
  const canResetAlertView = !isAlertViewAtDefault(alertView);

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
    if (!canGoToNextAlertPage || alertsBusy) return;
    setAlertsPendingLabel("Loading next page…");
    applyAlertViewPatch((current) => ({ offset: current.offset + alertPageSize }), {
      resetOffset: false,
      clearExactPivots: false,
    });
  }, [alertPageSize, alertsBusy, applyAlertViewPatch, canGoToNextAlertPage]);

  const handlePreviousAlertPage = useCallback(() => {
    if (!canGoToPreviousAlertPage || alertsBusy) return;
    setAlertsPendingLabel("Loading previous page…");
    applyAlertViewPatch((current) => ({ offset: Math.max(0, current.offset - alertPageSize) }), {
      resetOffset: false,
      clearExactPivots: false,
    });
  }, [alertPageSize, alertsBusy, applyAlertViewPatch, canGoToPreviousAlertPage]);

  const buildVisibleAiContext = useCallback(
    () => ({
      active_section: activeSection,
      visible_filters: {
        search: alertView.searchTerm,
        source: alertView.sourceFilter,
        severity: alertView.severityFilter,
        status: alertView.statusFilter,
        operational_scope: alertView.operationalScope,
        timeline_range: alertView.timelineRange,
        exact_source_ip: alertView.exactSourceIp,
        exact_target_ip: alertView.exactTargetIp,
        exact_alert_id: alertView.exactAlertId,
      },
      dashboard_summary: metrics,
      timeline: alertTimelineData.slice(0, 30),
      top_source_ips: topIPChartData.slice(0, 10),
      map_markers: alertMapMarkers.slice(0, 10),
      recent_alerts: alertsState.items.slice(0, 10).map((alert) => ({
        id: alert.id,
        alert_type: alert.alert_type,
        severity: alert.severity,
        status: alert.status,
        source_ip: alert.source_ip,
        message: alert.message,
        created_at: alert.created_at,
      })),
    }),
    [activeSection, alertMapMarkers, alertTimelineData, alertView, alertsState.items, metrics, topIPChartData]
  );

  const cancelAiRequest = useCallback(() => {
    if (aiRequestRef.current.controller) {
      aiRequestRef.current.controller.abort();
    }
  }, []);

  const runAiRequest = useCallback(async ({ title, request, executor, contextKey }) => {
    if (!canTakeAlertActions) return;
    cancelAiRequest();
    const controller = new AbortController();
    const requestId = aiRequestRef.current.id + 1;
    aiRequestRef.current = { id: requestId, controller, contextKey };
    setAiPanelState({
      status: "loading",
      title,
      response: null,
      error: "",
      stale: false,
      request: { title, request, executor, contextKey },
    });

    try {
      const response = await executor(request, { signal: controller.signal });
      if (aiRequestRef.current.id !== requestId) return;
      setAiPanelState({
        status: "success",
        title,
        response,
        error: "",
        stale: aiRequestRef.current.contextKey !== contextKey,
        request: { title, request, executor, contextKey },
      });
      if (request.message) {
        setAiChatHistory((current) =>
          [
            ...current,
            { role: "user", content: request.message },
            { role: "assistant", content: response.answer || response.error || "" },
          ].slice(-8)
        );
      }
    } catch (error) {
      if (error.name === "AbortError") {
        setAiPanelState((current) => ({
          ...current,
          status: "idle",
          error: "",
          response: null,
        }));
        return;
      }
      if (aiRequestRef.current.id !== requestId) return;
      setAiPanelState({
        status: "error",
        title,
        response: error.payload || null,
        error: error.message || "AI request failed.",
        stale: false,
        request: { title, request, executor, contextKey },
      });
    } finally {
      if (aiRequestRef.current.id === requestId) {
        aiRequestRef.current.controller = null;
      }
    }
  }, [canTakeAlertActions, cancelAiRequest]);

  const handleAskAi = useCallback(
    (options) => {
      if (!options) return;
      const visibleContext = buildVisibleAiContext();
      const contextKey = JSON.stringify({
        section: activeSection,
        selectedAlertId,
        filters: visibleContext.visible_filters,
      });
      const payload = {
        context_type: options.contextType,
        action: options.action,
        question: options.question || "",
        context: {
          ...visibleContext,
          ...(options.context || {}),
        },
      };
      runAiRequest({
        title: options.title || "AI explanation",
        request: payload,
        executor: requestAiExplanation,
        contextKey,
      });
    },
    [activeSection, buildVisibleAiContext, runAiRequest, selectedAlertId]
  );

  const handleAskAiChat = useCallback(
    (message) => {
      const visibleContext = buildVisibleAiContext();
      runAiRequest({
        title: "General SIEM question",
        request: {
          message,
          visible_context: visibleContext,
          client_history: aiChatHistory,
        },
        executor: requestAiChat,
        contextKey: JSON.stringify({ section: activeSection, filters: visibleContext.visible_filters }),
      });
    },
    [activeSection, aiChatHistory, buildVisibleAiContext, runAiRequest]
  );

  const retryAiRequest = useCallback(() => {
    if (aiPanelState.request) {
      runAiRequest(aiPanelState.request);
    }
  }, [aiPanelState.request, runAiRequest]);

  const dismissAiPanel = useCallback(() => {
    cancelAiRequest();
    setAiPanelState({
      status: "idle",
      title: "",
      response: null,
      error: "",
      stale: false,
      request: null,
    });
  }, [cancelAiRequest]);

  useEffect(() => {
    setAiPanelState((current) => {
      if (current.status !== "success" || current.stale) return current;
      return { ...current, stale: true };
    });
  }, [activeSection, alertView, selectedAlertId]);

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
            searchTerm={alertView.searchTerm}
            setSearchTerm={setSearchTerm}
            sortOption={alertView.sortOption}
            setSortOption={setSortOption}
            operationalScope={alertView.operationalScope}
            setOperationalScope={setOperationalScope}
            severityFilter={alertView.severityFilter}
            setSeverityFilter={setSeverityFilter}
            sourceFilter={alertView.sourceFilter}
            setSourceFilter={setSourceFilter}
            selectedAlertId={selectedAlertId}
            setSelectedAlertId={setSelectedAlertId}
            getSeverityBadgeStyle={(severity) => ({
              ...severityBadgeBase,
              ...getSeverityBadgeStyle(severity, settings.display?.severityColorPreset),
            })}
            onUpdateStatus={handleUpdateStatus}
            statusFilter={alertView.statusFilter}
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
            timelineRange={alertView.timelineRange}
            onTimelineRangeChange={setTimelineRange}
            timelineMeta={alertTimelineMeta}
            summaryPendingLabel={summaryPendingLabel}
            summaryBusy={summaryBusy}
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
            onRetry={() => {
              fetchAlertRows({ quiet: false });
              fetchAlertSummary({ quiet: false });
            }}
            totalAlerts={alertsState.total}
            pageOffset={alertsState.offset}
            pageLimit={alertsState.limit}
            pageEnd={alertPageEnd}
            canGoToPreviousPage={canGoToPreviousAlertPage}
            canGoToNextPage={canGoToNextAlertPage}
            onPreviousPage={handlePreviousAlertPage}
            onNextPage={handleNextAlertPage}
            onRefreshAlerts={() => fetchAlertRows({ quiet: true })}
            alertsPendingLabel={alertsPendingLabel}
            alertsBusy={alertsBusy}
            exactSourceIp={alertView.exactSourceIp}
            exactTargetIp={alertView.exactTargetIp}
            exactAlertId={alertView.exactAlertId}
            canResetFilters={canResetAlertView}
            onResetFilters={resetAlertView}
            onAskAi={handleAskAi}
            aiEnabled={canTakeAlertActions}
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
            onOpenIncident={handleOpenIncident}
            onViewRelatedAlerts={handleViewRelatedAlerts}
            onAskAi={handleAskAi}
            aiEnabled={canTakeAlertActions}
          />
        )}

        {activeSection === "severity-response-matrix" &&
          isSectionVisible("severity-response-matrix", roleFlags) && (
          <SeverityResponseMatrixPanel
            cardStyle={cardStyle}
            cardHeaderStyle={cardHeaderStyle}
            cardTitleStyle={cardTitleStyle}
            cardSubtitleStyle={cardSubtitleStyle}
            onNavigate={handleNavigate}
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
            onOpenAlert={handleOpenAlert}
            onOpenIncident={handleOpenIncident}
            onOpenPlaybookExecution={handleOpenPlaybookExecution}
            onOpenApproval={handleOpenApproval}
            onOpenSourceContext={handleViewRelatedAlerts}
            onAskAi={handleAskAi}
            aiEnabled={canTakeAlertActions}
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

        {activeSection === "notification-policy" && isSectionVisible("notification-policy", roleFlags) && (
          <NotificationPolicyPanel
            displaySettings={settings.display}
            cardStyle={cardStyle}
            cardHeaderStyle={cardHeaderStyle}
            cardTitleStyle={cardTitleStyle}
            cardSubtitleStyle={cardSubtitleStyle}
            onNavigate={handleNavigate}
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
            initialIncidentRequest={incidentsInitialRequest}
            onViewRelatedAlerts={handleViewRelatedAlerts}
            onAskAi={handleAskAi}
            aiEnabled={canTakeAlertActions}
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
              initialApprovalRequest={approvalsInitialRequest}
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
        {canTakeAlertActions ? (
          <>
            <AiResponsePanel
              state={aiPanelState}
              onDismiss={dismissAiPanel}
              onRetry={retryAiRequest}
              onCancel={cancelAiRequest}
            />
            <FloatingSiemChat onAsk={handleAskAiChat} disabled={aiPanelState.status === "loading"} />
          </>
        ) : null}
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
