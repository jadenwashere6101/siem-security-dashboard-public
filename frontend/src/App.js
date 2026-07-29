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
import ReconWorkspace from "./components/ReconWorkspace";
import SeverityResponseMatrixPanel from "./components/SeverityResponseMatrixPanel";
import ThreatHuntPanel from "./components/ThreatHuntPanel";
import ResponseRegistryPanel from "./components/ResponseRegistryPanel";
import LiveLogsPanel from "./components/LiveLogsPanel";
import SourceHealthPanel from "./components/SourceHealthPanel";
import DetectionSimulatorPanel from "./components/DetectionSimulatorPanel";
import SocBriefingsPanel from "./components/SocBriefingsPanel";
import SettingsPanel from "./components/SettingsPanel";
import SidebarLayout from "./components/SidebarLayout";
import AiResponsePanel from "./components/AiResponsePanel";
import AnakinCommandSurface from "./components/AnakinCommandSurface";
import CommandPalette from "./components/CommandPalette";
import AnalystWorkspace from "./components/AnalystWorkspace";
import InvestigationDrawer from "./components/InvestigationDrawer";
import ThreatBrief, { buildThreatBriefModel } from "./components/ThreatBrief";
import RepoArchitectureAssistantPanel from "./components/RepoArchitectureAssistantPanel";
import { theme } from "./theme";
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
import { loadAlertDashboardSummary, loadAlertRuleOptions, loadAlerts } from "./services/alertsService";
import { requestAiChat, requestAiDraft, requestAiExplanation, requestAiInvestigation } from "./services/aiService";
import {
  createEvidenceReference,
  createInvestigation,
  createWorkspaceHypothesis,
  createWorkspaceNote,
  createWorkspaceTask,
  loadAnalystWorkspace,
  pinWorkspaceItem,
  removeWorkspacePin,
} from "./services/investigationWorkspaceService";
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
import {
  canGoBackWorkspaceHistory,
  canGoForwardWorkspaceHistory,
  clearWorkspaceHistory,
  createWorkspaceBrowserState,
  createWorkspaceHistory,
  goBackWorkspaceHistory,
  goForwardWorkspaceHistory,
  isWorkspaceBrowserState,
  pushWorkspaceHistoryEntry,
  restoreWorkspaceHistoryEntry,
  updateCurrentWorkspaceHistoryEntry,
} from "./utils/workspaceHistory";
import { OPERATIONAL_SCOPE_SINCE_TUNING } from "./components/OperationalScopeToggle";
import {
  ANAKIN_COMMAND_INTENTS,
  buildCommandContext,
  commandToAiOptions,
  createCommandRegistry,
  createDefaultAnakinCommands,
  createExtensionCommandSlots,
  normalizeContextualAiOptions,
} from "./utils/anakinCommandRegistry";
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
  ruleFilter: "all",
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
    view.ruleFilter === baseline.ruleFilter &&
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
    ruleFilter: "all",
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
  const [alertRuleOptions, setAlertRuleOptions] = useState([]);
  const [selectedAlertId, setSelectedAlertId] = useState(null);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [currentUsername, setCurrentUsername] = useState(null);
  const [userRole, setUserRole] = useState(null);
  const { settings, updateSettings } = useUiSettings();
  const [activeSection, setActiveSection] = useState("dashboard");
  const [workspaceNavigationRequest, setWorkspaceNavigationRequest] = useState(null);
  const [workspaceHistory, setWorkspaceHistory] = useState(() =>
    createWorkspaceHistory({ sectionId: "dashboard", label: "Dashboard", state: {} })
  );
  const [workspaceRestoreRequest, setWorkspaceRestoreRequest] = useState(null);
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
  const activeSectionRef = useRef(activeSection);
  const userRoleRef = useRef(userRole);
  const alertViewRef = useRef(alertView);
  const selectedAlertIdRef = useRef(selectedAlertId);
  const registryInitialViewRef = useRef(registryInitialView);
  const registryNavigationRequestRef = useRef(registryNavigationRequest);
  const approvalsInitialStatusRef = useRef(approvalsInitialStatus);
  const approvalsInitialRequestRef = useRef(approvalsInitialRequest);
  const incidentsInitialRequestRef = useRef(incidentsInitialRequest);
  const playbooksInitialExecutionRequestRef = useRef(playbooksInitialExecutionRequest);
  const workspaceHistoryRef = useRef(workspaceHistory);
  const workspaceChildStateRef = useRef({});
  const resetWorkspaceHistoryRef = useRef(null);
  const isRestoringWorkspaceHistoryRef = useRef(false);
  const ignoreNextPopstateEntryIdRef = useRef(null);
  const [aiPanelState, setAiPanelState] = useState({
    status: "idle",
    title: "",
    response: null,
    error: "",
    stale: false,
    request: null,
  });
  const [aiChatHistory, setAiChatHistory] = useState([]);
  const [investigationDrawerOpen, setInvestigationDrawerOpen] = useState(false);
  const [workspaceState, setWorkspaceState] = useState(null);
  const [workspaceLoading, setWorkspaceLoading] = useState(false);
  const [workspaceError, setWorkspaceError] = useState("");

  useEffect(() => {
    activeSectionRef.current = activeSection;
  }, [activeSection]);

  useEffect(() => {
    userRoleRef.current = userRole;
  }, [userRole]);

  useEffect(() => {
    alertViewRef.current = alertView;
  }, [alertView]);

  useEffect(() => {
    selectedAlertIdRef.current = selectedAlertId;
  }, [selectedAlertId]);

  useEffect(() => {
    registryInitialViewRef.current = registryInitialView;
  }, [registryInitialView]);

  useEffect(() => {
    registryNavigationRequestRef.current = registryNavigationRequest;
  }, [registryNavigationRequest]);

  useEffect(() => {
    approvalsInitialStatusRef.current = approvalsInitialStatus;
  }, [approvalsInitialStatus]);

  useEffect(() => {
    approvalsInitialRequestRef.current = approvalsInitialRequest;
  }, [approvalsInitialRequest]);

  useEffect(() => {
    incidentsInitialRequestRef.current = incidentsInitialRequest;
  }, [incidentsInitialRequest]);

  useEffect(() => {
    playbooksInitialExecutionRequestRef.current = playbooksInitialExecutionRequest;
  }, [playbooksInitialExecutionRequest]);

  useEffect(() => {
    workspaceHistoryRef.current = workspaceHistory;
  }, [workspaceHistory]);

  const getMainScrollTop = useCallback(() => {
    if (typeof document === "undefined") return null;
    const main = document.querySelector("main");
    return main && Number.isFinite(Number(main.scrollTop)) ? Number(main.scrollTop) : null;
  }, []);

  const buildWorkspaceHistoryEntry = useCallback((sectionId, overrides = {}) => {
    const normalizedSectionId = String(sectionId || activeSectionRef.current || "dashboard").trim() || "dashboard";
    const childState = workspaceChildStateRef.current[normalizedSectionId] || {};
    const baseState = {
      alertView: alertViewRef.current,
      selectedAlertId: selectedAlertIdRef.current,
      registryInitialView: registryInitialViewRef.current,
      registryNavigationRequest: registryNavigationRequestRef.current,
      approvalsInitialStatus: approvalsInitialStatusRef.current,
      approvalsInitialRequest: approvalsInitialRequestRef.current,
      incidentsInitialRequest: incidentsInitialRequestRef.current,
      playbooksInitialExecutionRequest: playbooksInitialExecutionRequestRef.current,
      childState,
    };
    return {
      sectionId: normalizedSectionId,
      label: overrides.label || normalizedSectionId,
      target: overrides.target || null,
      scrollTop: overrides.scrollTop ?? getMainScrollTop(),
      state: {
        ...baseState,
        ...(overrides.state || {}),
      },
    };
  }, [getMainScrollTop]);

  const syncBrowserHistoryEntry = useCallback((entry, mode = "push") => {
    if (typeof window === "undefined" || !entry?.id) return;
    const state = createWorkspaceBrowserState(entry);
    if (mode === "replace") {
      window.history.replaceState(state, "", window.location.href);
      return;
    }
    window.history.pushState(state, "", window.location.href);
  }, []);

  const applyWorkspaceHistoryEntry = useCallback((entry) => {
    if (!entry) return;
    const currentRole = userRoleRef.current;
    const visibilityFlags = {
      isSuperAdmin: currentRole === "super_admin",
      isAnalyst: currentRole === "analyst",
      canTakeAlertActions: currentRole === "super_admin" || currentRole === "analyst",
    };
    const visibleSection = isSectionVisible(entry.sectionId, visibilityFlags) ? entry.sectionId : "dashboard";
    const state = visibleSection === entry.sectionId ? entry.state || {} : {};
    isRestoringWorkspaceHistoryRef.current = true;

    setAlertView(state.alertView || createAlertViewState());
    setSelectedAlertId(state.selectedAlertId ?? null);
    setRegistryInitialView(state.registryInitialView || "all");
    setRegistryNavigationRequest(
      state.registryNavigationRequest
        ? { ...state.registryNavigationRequest, nonce: Date.now() }
        : null
    );
    setApprovalsInitialStatus(state.approvalsInitialStatus || "all");
    setApprovalsInitialRequest(
      state.approvalsInitialRequest ? { ...state.approvalsInitialRequest, nonce: Date.now() } : null
    );
    setIncidentsInitialRequest(
      state.incidentsInitialRequest ? { ...state.incidentsInitialRequest, nonce: Date.now() } : null
    );
    setPlaybooksInitialExecutionRequest(
      state.playbooksInitialExecutionRequest
        ? { ...state.playbooksInitialExecutionRequest, nonce: Date.now() }
        : null
    );
    setWorkspaceRestoreRequest({
      sectionId: visibleSection,
      state: state.childState || {},
      nonce: Date.now(),
    });
    setWorkspaceNavigationRequest(createWorkspaceNavigationRequest(visibleSection, {
      destination: entry.target?.destination || NAVIGATION_DESTINATIONS.top,
      targetKey: entry.target?.targetKey || null,
      context: entry.target?.context || null,
      restoreScrollTop: entry.scrollTop,
      historyEntryId: entry.id,
      historyAction: "restore",
    }));
    setActiveSection(visibleSection);
    const clearRestoring = () => {
      isRestoringWorkspaceHistoryRef.current = false;
    };
    if (typeof window !== "undefined") {
      window.setTimeout(clearRestoring, 0);
    } else {
      clearRestoring();
    }
  }, []);

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

  const setRuleFilter = useCallback((value) => {
    setAlertsPendingLabel("Updating recent alerts…");
    setSummaryPendingLabel("Updating dashboard summary…");
    applyAlertViewPatch({ ruleFilter: value }, { clearExactPivots: false });
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
      ruleFilter: alertView.ruleFilter,
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
      ruleFilter: alertView.ruleFilter,
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
      setAlertRuleOptions([]);
      resetWorkspaceHistory("dashboard");
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
      resetWorkspaceHistory("dashboard");
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
      setAlertRuleOptions([]);
      resetWorkspaceHistory("dashboard");
      writeStoredSessionIdentity(null);
    }
  };

  useEffect(() => {
    checkAuth();
    // Auth bootstrap intentionally runs once; session changes are handled by API responses and logout/login flows.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!isAuthenticated) return;
    fetchAlertRows();
  }, [fetchAlertRows, isAuthenticated]);

  useEffect(() => {
    if (!isAuthenticated) {
      setAlertRuleOptions([]);
      return;
    }

    let cancelled = false;
    loadAlertRuleOptions()
      .then((items) => {
        if (!cancelled) {
          setAlertRuleOptions(items);
        }
      })
      .catch((err) => {
        console.error("Error fetching alert rule options:", err);
        if (!cancelled) {
          setAlertRuleOptions([]);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [isAuthenticated]);

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
      resetWorkspaceHistoryRef.current?.(legacyDestination.sectionId);
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
    resetWorkspaceHistoryRef.current?.(preferredSection);
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

  const applyWorkspaceNavigation = useCallback((sectionId, options = {}) => {
    setWorkspaceNavigationRequest(createWorkspaceNavigationRequest(sectionId, options));
    setActiveSection(sectionId);
  }, []);

  const navigateWorkspace = useCallback((sectionId, options = {}, historyOptions = {}) => {
    if (!isRestoringWorkspaceHistoryRef.current) {
      setWorkspaceHistory((current) => {
        const latestCurrent = buildWorkspaceHistoryEntry(activeSectionRef.current, {
          target: workspaceNavigationRequest?.targetKey
            ? {
                destination: workspaceNavigationRequest.destination,
                targetKey: workspaceNavigationRequest.targetKey,
                context: workspaceNavigationRequest.context,
              }
            : null,
        });
        const withCurrent = updateCurrentWorkspaceHistoryEntry(current, latestCurrent);
        const target = {
          destination: options.destination || NAVIGATION_DESTINATIONS.top,
          targetKey: options.targetKey || null,
          context: options.context || null,
        };
        const next = pushWorkspaceHistoryEntry(
          withCurrent,
          buildWorkspaceHistoryEntry(sectionId, {
            target,
            state: historyOptions.state || {},
            scrollTop: 0,
            label: historyOptions.label,
          })
        );
        if (next.current?.id && next.current.id !== withCurrent.current?.id) {
          syncBrowserHistoryEntry(next.current, "push");
        }
        workspaceHistoryRef.current = next;
        return next;
      });
    }
    applyWorkspaceNavigation(sectionId, options);
  }, [applyWorkspaceNavigation, buildWorkspaceHistoryEntry, syncBrowserHistoryEntry, workspaceNavigationRequest]);

  const resetWorkspaceHistory = useCallback((sectionId = "dashboard") => {
    const entry = buildWorkspaceHistoryEntry(sectionId, { scrollTop: 0 });
    const next = clearWorkspaceHistory(entry);
    setWorkspaceHistory(next);
    workspaceHistoryRef.current = next;
    if (next.current) {
      syncBrowserHistoryEntry(next.current, "replace");
    }
  }, [buildWorkspaceHistoryEntry, syncBrowserHistoryEntry]);
  resetWorkspaceHistoryRef.current = resetWorkspaceHistory;

  const restoreWorkspaceHistory = useCallback((entry, nextHistory, { updateBrowser = false } = {}) => {
    if (!entry || !nextHistory) return;
    setWorkspaceHistory(nextHistory);
    workspaceHistoryRef.current = nextHistory;
    applyWorkspaceHistoryEntry(entry);
    if (updateBrowser && entry.id) {
      ignoreNextPopstateEntryIdRef.current = entry.id;
      syncBrowserHistoryEntry(entry, "push");
    }
  }, [applyWorkspaceHistoryEntry, syncBrowserHistoryEntry]);

  const handleWorkspaceBack = useCallback(() => {
    const { history, entry } = goBackWorkspaceHistory(workspaceHistoryRef.current);
    if (!entry) return;
    setWorkspaceHistory(history);
    workspaceHistoryRef.current = history;
    applyWorkspaceHistoryEntry(entry);
    ignoreNextPopstateEntryIdRef.current = entry.id;
    if (typeof window !== "undefined" && typeof window.history?.back === "function") {
      window.history.back();
    }
  }, [applyWorkspaceHistoryEntry]);

  const handleWorkspaceForward = useCallback(() => {
    const { history, entry } = goForwardWorkspaceHistory(workspaceHistoryRef.current);
    if (!entry) return;
    setWorkspaceHistory(history);
    workspaceHistoryRef.current = history;
    applyWorkspaceHistoryEntry(entry);
    ignoreNextPopstateEntryIdRef.current = entry.id;
    if (typeof window !== "undefined" && typeof window.history?.forward === "function") {
      window.history.forward();
    }
  }, [applyWorkspaceHistoryEntry]);

  const handleWorkspaceChildStateChange = useCallback((sectionId, nextState) => {
    const normalizedSectionId = String(sectionId || "").trim();
    if (!normalizedSectionId || isRestoringWorkspaceHistoryRef.current) return;
    workspaceChildStateRef.current = {
      ...workspaceChildStateRef.current,
      [normalizedSectionId]: nextState && typeof nextState === "object" ? nextState : {},
    };
    if (activeSectionRef.current !== normalizedSectionId) return;
    setWorkspaceHistory((current) => {
      const next = updateCurrentWorkspaceHistoryEntry(
        current,
        buildWorkspaceHistoryEntry(normalizedSectionId)
      );
      workspaceHistoryRef.current = next;
      if (next.current) {
        syncBrowserHistoryEntry(next.current, "replace");
      }
      return next;
    });
  }, [buildWorkspaceHistoryEntry, syncBrowserHistoryEntry]);

  useEffect(() => {
    if (!isAuthenticated) return undefined;
    const onPopState = (event) => {
      if (!isWorkspaceBrowserState(event.state)) return;
      if (ignoreNextPopstateEntryIdRef.current === event.state.entryId) {
        ignoreNextPopstateEntryIdRef.current = null;
        return;
      }
      const restored = restoreWorkspaceHistoryEntry(workspaceHistoryRef.current, event.state.entryId);
      if (!restored.entry) return;
      restoreWorkspaceHistory(restored.entry, restored.history);
    };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, [isAuthenticated, restoreWorkspaceHistory]);

  const handleNavigate = useCallback((sectionId) => {
    const destination = normalizeWorkspaceDestination(sectionId);
    if (destination.registryView) {
      setRegistryInitialView(destination.registryView);
      navigateWorkspace(destination.sectionId, {
        destination: NAVIGATION_DESTINATIONS.element,
        targetKey: WORKSPACE_TARGETS.responseRegistry,
      }, {
        state: {
          registryInitialView: destination.registryView,
        },
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
    }, {
      state: {
        registryInitialView: target.view || "all",
        registryNavigationRequest: target,
      },
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
    } : undefined, target.statusFilter ? {
      state: {
        approvalsInitialStatus: target.statusFilter,
      },
    } : undefined);
  }, [navigateWorkspace]);

  const handleOpenPlaybookExecution = useCallback((executionId) => {
    if (executionId == null) return;
    setPlaybooksInitialExecutionRequest({
      executionId: Number(executionId),
      nonce: Date.now(),
    });
    navigateWorkspace("soar-playbooks", undefined, {
      state: {
        playbooksInitialExecutionRequest: { executionId: Number(executionId) },
      },
    });
  }, [navigateWorkspace]);

  const handleOpenIncident = useCallback((incidentId) => {
    if (incidentId == null) return;
    setIncidentsInitialRequest({
      incidentId: Number(incidentId),
      nonce: Date.now(),
    });
    navigateWorkspace("soar-incidents", undefined, {
      state: {
        incidentsInitialRequest: { incidentId: Number(incidentId) },
      },
    });
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
    }, {
      state: {
        approvalsInitialRequest: { approvalId: Number(approvalId) },
      },
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
    }, {
      state: {
        alertView: buildContextualAlertView(alertViewRef.current, { alertId: Number(alertId) }),
        selectedAlertId: Number(alertId),
      },
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
    }, {
      state: {
        alertView: buildContextualAlertView(alertViewRef.current, {
          sourceIp: normalizedSourceIp,
          targetIp: normalizedTargetIp,
          alertId: Number.isFinite(normalizedAlertId) ? normalizedAlertId : null,
        }),
        selectedAlertId: null,
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

  const selectedAlert = useMemo(
    () =>
      selectedAlertId !== null && selectedAlertId !== undefined
        ? alertsState.items.find((alert) => String(alert.id ?? alert.alert_id) === String(selectedAlertId)) || null
        : null,
    [alertsState.items, selectedAlertId]
  );

  const refreshAnalystWorkspace = useCallback(async () => {
    if (!canTakeAlertActions) return null;
    setWorkspaceLoading(true);
    setWorkspaceError("");
    try {
      const data = await loadAnalystWorkspace();
      setWorkspaceState(data);
      return data;
    } catch (error) {
      setWorkspaceError(error.message || "Unable to load analyst workspace");
      return null;
    } finally {
      setWorkspaceLoading(false);
    }
  }, [canTakeAlertActions]);

  const pinAlertToWorkspace = useCallback(async (alert) => {
    if (!alert) return null;
    const alertId = alert.id ?? alert.alert_id;
    try {
      const item = await pinWorkspaceItem({
        item_type: "alert",
        referenced_object_type: "alert",
        referenced_object_id: String(alertId),
        label: `Alert #${alertId} ${alert.alert_type || ""}`.trim(),
        metadata: { source_ip: alert.source_ip || "", severity: alert.severity || "" },
      });
      await refreshAnalystWorkspace();
      return item;
    } catch (error) {
      setWorkspaceError(error.message || "Unable to pin alert");
      return null;
    }
  }, [refreshAnalystWorkspace]);

  const saveInvestigationState = useCallback(async (context) => {
    const alert = context?.alert;
    const incident = context?.incident;
    try {
      const investigation = await createInvestigation({
        title: alert ? `Investigation for alert #${alert.id ?? alert.alert_id}` : incident?.title || "Investigation",
        linked_alert_id: alert?.id ?? alert?.alert_id ?? null,
        linked_incident_id: incident?.id ?? null,
        linked_source_ip: context?.sourceIp || alert?.source_ip || incident?.source_ip || null,
        summary: "Saved from Investigation Drawer",
        saved_state: {
          source: "investigation_drawer",
          has_timeline: Boolean(context?.timeline?.length),
          has_response_history: Boolean(context?.responseHistory?.length),
        },
      });
      await refreshAnalystWorkspace();
      return investigation;
    } catch (error) {
      setWorkspaceError(error.message || "Unable to save investigation");
      return null;
    }
  }, [refreshAnalystWorkspace]);

  const createPrivateNote = useCallback(async (body) => {
    try {
      await createWorkspaceNote({ body });
      await refreshAnalystWorkspace();
    } catch (error) {
      setWorkspaceError(error.message || "Unable to create note");
    }
  }, [refreshAnalystWorkspace]);

  const createPrivateHypothesis = useCallback(async (title) => {
    try {
      await createWorkspaceHypothesis({ title });
      await refreshAnalystWorkspace();
    } catch (error) {
      setWorkspaceError(error.message || "Unable to create hypothesis");
    }
  }, [refreshAnalystWorkspace]);

  const createPrivateTask = useCallback(async (title) => {
    try {
      await createWorkspaceTask({ title });
      await refreshAnalystWorkspace();
    } catch (error) {
      setWorkspaceError(error.message || "Unable to create task");
    }
  }, [refreshAnalystWorkspace]);

  const deletePrivatePin = useCallback(async (itemId) => {
    try {
      await removeWorkspacePin(itemId);
      await refreshAnalystWorkspace();
    } catch (error) {
      setWorkspaceError(error.message || "Unable to remove workspace item");
    }
  }, [refreshAnalystWorkspace]);

  const saveAlertEvidenceReference = useCallback(async (alert) => {
    if (!alert) return;
    const alertId = alert.id ?? alert.alert_id;
    try {
      await createEvidenceReference({
        referenced_object_type: "alert",
        referenced_object_id: String(alertId),
        label: `Evidence for alert #${alertId}`,
        source: "investigation_drawer",
      });
      await refreshAnalystWorkspace();
    } catch (error) {
      setWorkspaceError(error.message || "Unable to save evidence reference");
    }
  }, [refreshAnalystWorkspace]);

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
  const threatBriefModel = useMemo(
    () =>
      buildThreatBriefModel({
        alerts: alertsState.items,
        metrics,
        sourceErrors: dashboardRefreshError ? ["dashboard"] : [],
        stale: dashboardRefreshing,
      }),
    [alertsState.items, dashboardRefreshError, dashboardRefreshing, metrics]
  );
  const anakinCommandContext = useMemo(
    () =>
      buildCommandContext({
        activeSection,
        alertView,
        selectedAlertId,
        alerts: alertsState.items,
        metrics,
        currentUsername,
        userRole,
        canTakeAlertActions,
        threatBrief: threatBriefModel,
      }),
    [
      activeSection,
      alertView,
      alertsState.items,
      canTakeAlertActions,
      currentUsername,
      metrics,
      selectedAlertId,
      threatBriefModel,
      userRole,
    ]
  );
  const investigationCommands = useMemo(
    () => [
      {
        id: "investigation.open-drawer",
        label: "Open Investigation Drawer",
        group: "Investigation",
        intent: ANAKIN_COMMAND_INTENTS.extension,
        readOnly: true,
        description: "Open the focused investigation drawer for the selected alert context.",
        availability: (context) => Boolean(context.object?.alert),
        execute: () => {
          setInvestigationDrawerOpen(true);
          refreshAnalystWorkspace();
        },
      },
      {
        id: "investigation.pin-selected-alert",
        label: "Pin selected alert",
        group: "Investigation",
        intent: ANAKIN_COMMAND_INTENTS.extension,
        readOnly: false,
        description: "Manually pin the selected alert to the private Analyst Workspace.",
        availability: (context) => Boolean(context.object?.alert),
        execute: () => pinAlertToWorkspace(selectedAlert),
      },
      {
        id: "investigation.open-workspace",
        label: "Open Analyst Workspace",
        group: "Investigation",
        intent: ANAKIN_COMMAND_INTENTS.navigate,
        readOnly: true,
        description: "Open the private analyst investigation notebook.",
        execute: () => {
          handleNavigate("analyst-workspace");
          refreshAnalystWorkspace();
        },
      },
    ],
    [handleNavigate, pinAlertToWorkspace, refreshAnalystWorkspace, selectedAlert]
  );
  const anakinRegistry = useMemo(
    () => createCommandRegistry([...createDefaultAnakinCommands(), ...createExtensionCommandSlots(), ...investigationCommands]),
    [investigationCommands]
  );
  const anakinCommands = useMemo(
    () => anakinRegistry.available(anakinCommandContext),
    [anakinCommandContext, anakinRegistry]
  );
  useEffect(() => {
    if (activeSection === "analyst-workspace" && canTakeAlertActions) {
      refreshAnalystWorkspace();
    }
  }, [activeSection, canTakeAlertActions, refreshAnalystWorkspace]);
  const paletteCommands = useMemo(() => {
    const visibleSections = sectionsConfig
      .filter((section) => section.visibleWhen(roleFlags))
      .map((section) => ({
        id: `navigate.${section.id}`,
        label: section.label,
        group: "Navigation",
        intent: ANAKIN_COMMAND_INTENTS.navigate,
        readOnly: true,
        description: `Open ${section.label}`,
        execute: () => handleNavigate(section.id),
        keywords: [section.id, section.group],
      }));
    const filterCommands = [
      {
        id: "filter.severity.high",
        label: "Filter high severity alerts",
        group: "Quick filters",
        intent: ANAKIN_COMMAND_INTENTS.filter,
        readOnly: true,
        description: "Show high severity alerts on the dashboard.",
        execute: () => {
          handleNavigate("dashboard");
          setSeverityFilter("high");
        },
        keywords: ["alert", "severity", "high"],
      },
      {
        id: "filter.reset-dashboard",
        label: "Reset dashboard filters",
        group: "Quick filters",
        intent: ANAKIN_COMMAND_INTENTS.filter,
        readOnly: true,
        description: "Reset dashboard filters without changing backend state.",
        execute: resetAlertView,
        keywords: ["dashboard", "filter", "reset"],
      },
      {
        id: "action.open-recent-alerts",
        label: "Open recent alerts",
        group: "Common actions",
        intent: ANAKIN_COMMAND_INTENTS.navigate,
        readOnly: true,
        description: "Navigate to the dashboard recent alerts target.",
        execute: () =>
          navigateWorkspace("dashboard", {
            destination: NAVIGATION_DESTINATIONS.element,
            targetKey: "recent-alerts",
          }),
        keywords: ["alerts", "recent"],
      },
    ];
    return [...anakinCommands, ...visibleSections, ...filterCommands];
  }, [anakinCommands, handleNavigate, navigateWorkspace, resetAlertView, roleFlags, setSeverityFilter]);
  const paletteObjects = useMemo(() => {
    const alertObjects = alertsState.items.slice(0, 25).map((alert) => ({
      id: `alert.${alert.alert_id ?? alert.id}`,
      label: alert.alert_type || `Alert ${alert.alert_id ?? alert.id}`,
      group: "Alert lookup",
      description: [alert.severity, alert.source_ip, alert.status].filter(Boolean).join(" • "),
      meta: [alert.severity, alert.source_ip].filter(Boolean).join(" • "),
      keywords: [String(alert.alert_id ?? alert.id ?? ""), alert.source_ip, alert.alert_type],
      execute: () => {
        handleOpenAlert(alert.alert_id ?? alert.id);
      },
    }));
    const sourceObjects = Array.from(new Set(alertsState.items.map((alert) => alert.source_ip).filter(Boolean)))
      .slice(0, 20)
      .map((sourceIp) => ({
        id: `source-ip.${sourceIp}`,
        label: sourceIp,
        group: "IP lookup",
        description: "Open related alerts for this source IP.",
        keywords: [sourceIp, "ip", "source"],
        execute: () => handleViewRelatedAlerts(sourceIp),
      }));
    return [...alertObjects, ...sourceObjects];
  }, [alertsState.items, handleOpenAlert, handleViewRelatedAlerts]);

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
        rule_id: alertView.ruleFilter,
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
      const contextualCommand = normalizeContextualAiOptions(options);
      const contextKey = JSON.stringify({
        section: activeSection,
        selectedAlertId,
        filters: visibleContext.visible_filters,
        command: contextualCommand.id,
      });
      const context = {
        ...visibleContext,
        command: {
          id: contextualCommand.id,
          label: contextualCommand.label,
          intent: contextualCommand.intent,
          read_only: contextualCommand.readOnly,
        },
        ...(options.context || {}),
      };
      const payload = options.draftType
        ? {
            draft_type: options.draftType,
            instruction: options.instruction || options.question || "",
            context_type: options.contextType,
            context,
            use_tools: options.useTools !== false,
            tool_policy: options.toolPolicy || { max_tool_calls: 3, time_window_hours: 24 },
          }
        : {
            context_type: options.contextType,
            action: options.action,
            question: options.question || "",
            context,
          };
      const executor = options.investigation
        ? requestAiInvestigation
        : options.draftType
          ? requestAiDraft
          : requestAiExplanation;
      runAiRequest({
        title: options.title || (options.investigation ? "Guided AI investigation" : options.draftType ? "AI draft" : "AI explanation"),
        request: payload,
        executor,
        contextKey,
      });
    },
    [activeSection, buildVisibleAiContext, runAiRequest, selectedAlertId]
  );

  const executeAnakinCommand = useCallback(
    (command, runtime = {}) => {
      if (!command) return;
      if (typeof command.execute === "function") {
        command.execute();
        return;
      }
      if (command.intent === ANAKIN_COMMAND_INTENTS.ask && runtime.question?.trim()) {
        const visibleContext = buildVisibleAiContext();
        runAiRequest({
          title: "Ask Anakin",
          request: {
            message: runtime.question.trim(),
            visible_context: {
              ...visibleContext,
              command_context: anakinCommandContext,
            },
            client_history: aiChatHistory,
            use_tools: true,
            tool_policy: { max_tool_calls: 5, time_window_hours: 24 },
          },
          executor: requestAiChat,
          contextKey: JSON.stringify({
            section: activeSection,
            filters: visibleContext.visible_filters,
            command: command.id,
          }),
        });
        return;
      }
      const options = commandToAiOptions(command, anakinCommandContext, runtime.question || "");
      handleAskAi(options);
    },
    [activeSection, aiChatHistory, anakinCommandContext, buildVisibleAiContext, handleAskAi, runAiRequest]
  );

  const executePaletteCommand = useCallback(
    (command) => {
      if (!command) return;
      executeAnakinCommand(command);
    },
    [executeAnakinCommand]
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
        style={loginShellStyle}
      >
        <div style={loginStatusStyle}>Checking authentication...</div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <div style={loginShellStyle}>
        <form
          onSubmit={handleLogin}
          style={loginCardStyle}
          aria-labelledby="siem-login-title"
        >
          <div style={loginIdentityStyle}>
            <span aria-hidden="true" style={loginMarkStyle}>SIEM</span>
            <div>
              <p style={loginEyebrowStyle}>Anakin analyst console</p>
              <h2 id="siem-login-title" style={loginTitleStyle}>SIEM Dashboard Login</h2>
            </div>
          </div>
          <p style={loginSubtitleStyle}>Sign in to access alerts and response actions.</p>

          <label
            htmlFor="login-username"
            style={loginLabelStyle}
          >
            Username
          </label>
          <input
            id="login-username"
            type="text"
            value={loginUsername}
            onChange={(e) => setLoginUsername(e.target.value)}
            style={loginInputStyle}
          />

          <label
            htmlFor="login-password"
            style={loginLabelStyle}
          >
            Password
          </label>
          <input
            id="login-password"
            type="password"
            value={loginPassword}
            onChange={(e) => setLoginPassword(e.target.value)}
            style={loginInputStyle}
          />

          {loginError && (
            <div
              style={loginErrorStyle}
            >
              {loginError}
            </div>
          )}

          <button
            type="submit"
            style={loginButtonStyle}
          >
            Log In
          </button>
          <div style={loginFooterStyle}>
            <span>Operational console</span>
            <span>v{packageJson.version}</span>
          </div>
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
      navigationControls={
        <div style={workspaceHistoryControlsStyle} aria-label="Workspace history controls">
          <button
            type="button"
            onClick={handleWorkspaceBack}
            disabled={!canGoBackWorkspaceHistory(workspaceHistory)}
            style={{
              ...workspaceHistoryButtonStyle,
              ...(!canGoBackWorkspaceHistory(workspaceHistory) ? workspaceHistoryButtonDisabledStyle : null),
            }}
            aria-label="Back"
          >
            ← Back
          </button>
          <button
            type="button"
            onClick={handleWorkspaceForward}
            disabled={!canGoForwardWorkspaceHistory(workspaceHistory)}
            style={{
              ...workspaceHistoryButtonStyle,
              ...(!canGoForwardWorkspaceHistory(workspaceHistory) ? workspaceHistoryButtonDisabledStyle : null),
            }}
            aria-label="Forward"
          >
            Forward →
          </button>
        </div>
      }
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

        {canTakeAlertActions ? (
          <ThreatBrief
            model={threatBriefModel}
            loading={dashboardInitialLoading}
          />
        ) : null}

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
            ruleFilter={alertView.ruleFilter}
            setRuleFilter={setRuleFilter}
            ruleFilterOptions={alertRuleOptions}
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
            onOpenInvestigation={(alert) => {
              setSelectedAlertId(alert?.id ?? alert?.alert_id ?? null);
              setInvestigationDrawerOpen(true);
              refreshAnalystWorkspace();
            }}
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
            restoreRequest={
              workspaceRestoreRequest?.sectionId === "threat-hunt" ? workspaceRestoreRequest : null
            }
            onHistoryStateChange={(state) =>
              handleWorkspaceChildStateChange("threat-hunt", { threatHunt: state })
            }
          />
        )}

        {activeSection === "analyst-workspace" && isSectionVisible("analyst-workspace", roleFlags) && (
          <AnalystWorkspace
            workspaceState={workspaceState}
            loading={workspaceLoading}
            error={workspaceError}
            onRefresh={refreshAnalystWorkspace}
            onCreateNote={createPrivateNote}
            onCreateHypothesis={createPrivateHypothesis}
            onCreateTask={createPrivateTask}
            onRemovePin={deletePrivatePin}
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
            onOpenReconWorkspace={() => handleNavigate("recon-history")}
            onAskAi={handleAskAi}
            aiEnabled={canTakeAlertActions}
            restoreRequest={
              workspaceRestoreRequest?.sectionId === "soc-command-center" ? workspaceRestoreRequest : null
            }
            onHistoryStateChange={(state) =>
              handleWorkspaceChildStateChange("soc-command-center", { socCommandCenter: state })
            }
          />
        )}

        {activeSection === "soc-briefings" && isSectionVisible("soc-briefings", roleFlags) && (
          <SocBriefingsPanel />
        )}

        {activeSection === "recon-history" && isSectionVisible("recon-history", roleFlags) && (
          <ReconWorkspace
            onViewRelatedAlerts={handleViewRelatedAlerts}
            onOpenIncident={handleOpenIncident}
            restoreRequest={
              workspaceRestoreRequest?.sectionId === "recon-history" ? workspaceRestoreRequest : null
            }
            onHistoryStateChange={(state) =>
              handleWorkspaceChildStateChange("recon-history", { recon: state })
            }
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

        {activeSection === "repo-architecture-assistant" &&
          isSectionVisible("repo-architecture-assistant", roleFlags) && (
          <RepoArchitectureAssistantPanel
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
            restoreRequest={
              workspaceRestoreRequest?.sectionId === "soar-queue" ? workspaceRestoreRequest : null
            }
            onHistoryStateChange={(state) =>
              handleWorkspaceChildStateChange("soar-queue", { soarQueue: state })
            }
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
          <InvestigationDrawer
            open={investigationDrawerOpen}
            onClose={() => setInvestigationDrawerOpen(false)}
            alert={selectedAlert}
            timeline={alertTimelineData}
            workspace={workspaceState}
            observations={workspaceState?.notes || []}
            onPinAlert={pinAlertToWorkspace}
            onSaveEvidence={saveAlertEvidenceReference}
            onCreateInvestigation={saveInvestigationState}
          />
        ) : null}
        {canTakeAlertActions ? (
          <>
            <CommandPalette
              commands={paletteCommands}
              objects={paletteObjects}
              onExecute={executePaletteCommand}
              disabled={aiPanelState.status === "loading"}
            />
            <AiResponsePanel
              state={aiPanelState}
              onDismiss={dismissAiPanel}
              onRetry={retryAiRequest}
              onCancel={cancelAiRequest}
              userRole={userRole}
            />
            <AnakinCommandSurface
              commands={anakinCommands}
              context={anakinCommandContext}
              onExecute={executeAnakinCommand}
              disabled={aiPanelState.status === "loading"}
              status={aiPanelState.status}
              triggerAriaLabel="Open general Anakin SIEM chat"
            />
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

const loginShellStyle = {
  minHeight: "100dvh",
  width: "100%",
  boxSizing: "border-box",
  backgroundColor: "#0b1020",
  backgroundImage:
    "linear-gradient(rgba(88, 166, 255, 0.035) 1px, transparent 1px), linear-gradient(90deg, rgba(88, 166, 255, 0.035) 1px, transparent 1px)",
  backgroundSize: "36px 36px",
  color: theme.color.text,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  padding: "16px",
  fontFamily: "Arial, sans-serif",
  overflowX: "hidden",
};

const loginStatusStyle = {
  color: theme.color.textSoft,
  fontWeight: 700,
};

const loginCardStyle = {
  width: "100%",
  maxWidth: "420px",
  minWidth: 0,
  flexShrink: 1,
  boxSizing: "border-box",
  backgroundColor: "#111827",
  border: "1px solid #1f2937",
  borderRadius: theme.radius.lg,
  padding: "clamp(18px, 5vw, 26px)",
  boxShadow: theme.shadow.raised,
};

const loginIdentityStyle = {
  display: "flex",
  alignItems: "center",
  gap: "12px",
  marginBottom: "12px",
  minWidth: 0,
};

const loginMarkStyle = {
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  width: "44px",
  height: "44px",
  borderRadius: theme.radius.sm,
  border: "1px solid rgba(125, 211, 252, 0.35)",
  backgroundColor: theme.color.aiBg,
  color: theme.color.aiSoft,
  fontSize: "11px",
  fontWeight: 900,
  letterSpacing: "0.08em",
  flexShrink: 0,
};

const loginEyebrowStyle = {
  margin: "0 0 2px",
  color: theme.color.aiSoft,
  fontSize: "11px",
  fontWeight: 800,
  letterSpacing: "0.08em",
  textTransform: "uppercase",
};

const loginTitleStyle = {
  margin: 0,
  color: theme.color.text,
  fontSize: "clamp(21px, 6vw, 25px)",
  lineHeight: 1.15,
};

const loginSubtitleStyle = {
  margin: "0 0 20px",
  color: "#9ca3af",
  lineHeight: 1.4,
};

const loginLabelStyle = {
  display: "block",
  marginBottom: "6px",
  fontSize: "14px",
  color: theme.color.text,
};

const loginInputStyle = {
  width: "100%",
  minWidth: 0,
  padding: "11px 12px",
  marginBottom: "16px",
  borderRadius: theme.radius.sm,
  border: "1px solid #374151",
  backgroundColor: "#0f172a",
  color: "white",
  boxSizing: "border-box",
};

const loginErrorStyle = {
  marginBottom: "16px",
  padding: "10px 12px",
  borderRadius: theme.radius.sm,
  backgroundColor: theme.color.dangerBg,
  border: "1px solid rgba(239, 68, 68, 0.35)",
  color: theme.color.dangerSoft,
  fontSize: "14px",
};

const loginButtonStyle = {
  width: "100%",
  padding: "11px 12px",
  borderRadius: theme.radius.sm,
  border: "none",
  backgroundColor: "#2563eb",
  color: "white",
  fontWeight: "700",
  cursor: "pointer",
};

const loginFooterStyle = {
  display: "flex",
  justifyContent: "space-between",
  gap: "12px",
  flexWrap: "wrap",
  marginTop: "16px",
  color: theme.color.textMuted,
  fontSize: "11px",
};

const workspaceHistoryControlsStyle = {
  display: "inline-flex",
  alignItems: "center",
  gap: "6px",
};

const workspaceHistoryButtonStyle = {
  border: "1px solid #30363d",
  backgroundColor: "#161b22",
  color: "#e6edf3",
  borderRadius: "8px",
  padding: "8px 10px",
  fontSize: "12px",
  fontWeight: 700,
  cursor: "pointer",
  whiteSpace: "nowrap",
};

const workspaceHistoryButtonDisabledStyle = {
  color: "#6e7681",
  cursor: "not-allowed",
  opacity: 0.55,
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
  gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 400px), 1fr))",
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
