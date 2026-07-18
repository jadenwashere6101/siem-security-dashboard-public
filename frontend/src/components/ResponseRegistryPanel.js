import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import BlocklistManagerPanel from "./BlocklistManagerPanel";
import {
  REGISTRY_VIEWS,
  executeRegistryCommand,
  loadRegistryDetail,
  loadRegistryRecords,
} from "../services/responseRegistryService";
import { formatTimestamp } from "../utils/displayFormatting";
import {
  actionSummaryLabel,
  dispositionSummaryLabel,
  formatCanonicalActionSuccess,
} from "../utils/responseStateLabels";
import {
  registryActionLabel,
  registryInvestigateTarget,
  registryOutcomeLabel,
  registryOutcomeTone,
  registryRecommendedNextStep,
} from "../utils/responseRegistryPresentation";
import { keysOverlap, useResponseSync } from "../context/ResponseSyncContext";
import AiAssistantButton from "./AiAssistantButton";

const PAGE_SIZE = 50;

function removeTrackingControlTitle(canMutate, restrictionTitle, blocklistEntry) {
  if (!canMutate) return restrictionTitle;
  if (!blocklistEntry) {
    return "No linked Blocklist tracking record. Use Track in Blocklist first, or open the Blocklist Tracking view.";
  }
  if (blocklistEntry.status !== "active") {
    return `Tracking status is "${blocklistEntry.status}". History remains readable; Remove Tracking applies only to active SIEM tracking.`;
  }
  return "Ends SIEM Blocklist tracking only. History and audit remain. Does not change any firewall, provider, or host.";
}

const SORT_OPTIONS = [
  { value: "updated_at_desc", label: "Last updated (newest)" },
  { value: "updated_at_asc", label: "Last updated (oldest)" },
  { value: "created_at_desc", label: "First seen (newest)" },
  { value: "indicator_value_asc", label: "Indicator A–Z" },
];

const DISPOSITION_FILTERS = [
  "all",
  "monitored",
  "blocklist_tracked",
  "escalated",
  "pending",
  "failed",
  "rejected",
  "expired",
  "removed",
  "observed",
];

const buttonStyle = (disabled) => ({
  padding: "6px 12px",
  borderRadius: "6px",
  border: "1px solid #30363d",
  background: disabled ? "#21262d" : "#1f6feb",
  color: disabled ? "#8b949e" : "#ffffff",
  cursor: disabled ? "not-allowed" : "pointer",
  fontSize: "13px",
});

const secondaryButtonStyle = (disabled) => ({
  ...buttonStyle(disabled),
  background: "#21262d",
  color: disabled ? "#8b949e" : "#c9d1d9",
});

const inputStyle = {
  width: "100%",
  padding: "8px 10px",
  borderRadius: "6px",
  border: "1px solid #30363d",
  background: "#0d1117",
  color: "#c9d1d9",
  fontSize: "13px",
};

const feedbackStyles = {
  error: {
    border: "#f85149",
    color: "#ffa198",
    background: "#3d1214",
  },
  info: {
    border: "#388bfd",
    color: "#93c5fd",
    background: "#0d1b2a",
  },
  success: {
    border: "#238636",
    color: "#3fb950",
    background: "#0d2818",
  },
};

const outcomeToneStyles = {
  success: {
    color: "#86efac",
    backgroundColor: "rgba(34, 197, 94, 0.12)",
    border: "1px solid rgba(34, 197, 94, 0.30)",
  },
  warning: {
    color: "#fcd34d",
    backgroundColor: "rgba(251, 191, 36, 0.12)",
    border: "1px solid rgba(251, 191, 36, 0.30)",
  },
  info: {
    color: "#93c5fd",
    backgroundColor: "rgba(59, 130, 246, 0.12)",
    border: "1px solid rgba(59, 130, 246, 0.30)",
  },
  neutral: {
    color: "#c9d1d9",
    backgroundColor: "rgba(148, 163, 184, 0.10)",
    border: "1px solid rgba(148, 163, 184, 0.24)",
  },
  danger: {
    color: "#fca5a5",
    backgroundColor: "rgba(239, 68, 68, 0.14)",
    border: "1px solid rgba(239, 68, 68, 0.34)",
  },
};

const linkButtonStyle = {
  background: "transparent",
  border: "1px solid #388bfd",
  color: "#58a6ff",
  borderRadius: "999px",
  padding: "4px 10px",
  cursor: "pointer",
  fontSize: "12px",
};

function outcomeBadgeStyle(label) {
  return {
    display: "inline-flex",
    alignItems: "center",
    padding: "4px 8px",
    borderRadius: "999px",
    fontSize: "12px",
    fontWeight: 600,
    ...(outcomeToneStyles[registryOutcomeTone(label)] || outcomeToneStyles.neutral),
  };
}

function summaryValueStyle(mono = false) {
  return {
    margin: 0,
    fontFamily: mono ? "monospace" : "inherit",
    color: "#e6edf3",
  };
}

function dispositionLabel(value) {
  if (!value) return "—";
  return String(value).replace(/_/g, " ");
}

function ResponseRegistryPanel({
  cardStyle,
  cardHeaderStyle,
  cardTitleStyle,
  cardSubtitleStyle,
  filterLabelStyle,
  selectStyle,
  canTakeAlertActions = false,
  initialView = "all",
  navigationRequest = null,
  onOpenAlert = null,
  onOpenIncident = null,
  onOpenPlaybookExecution = null,
  onOpenApproval = null,
  onOpenSourceContext = null,
  onAskAi = null,
  aiEnabled = false,
}) {
  const { publishMutation, subscribe } = useResponseSync();
  const [view, setView] = useState(initialView || "all");
  const [records, setRecords] = useState([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [relatedAlertId, setRelatedAlertId] = useState(null);
  const [relatedIncidentId, setRelatedIncidentId] = useState(null);
  const [relatedPlaybookExecutionId, setRelatedPlaybookExecutionId] = useState(null);
  const [relatedApprovalRequestId, setRelatedApprovalRequestId] = useState(null);
  const [feedback, setFeedback] = useState({ type: "", message: "" });

  const [search, setSearch] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [exactIndicator, setExactIndicator] = useState("");
  const [dispositionFilter, setDispositionFilter] = useState("all");
  const [originFilter, setOriginFilter] = useState("");
  const [outcomeFilter, setOutcomeFilter] = useState("");
  const [enforcementFilter, setEnforcementFilter] = useState("");
  const [sort, setSort] = useState("updated_at_desc");

  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");

  const [actionBusy, setActionBusy] = useState("");
  const [noteText, setNoteText] = useState("");
  const [monitorExpiry, setMonitorExpiry] = useState("");
  const [trackReason, setTrackReason] = useState("");
  const [incidentReason, setIncidentReason] = useState("");
  const submitLockRef = useRef(false);
  const lastRequestedOffsetRef = useRef(0);

  useEffect(() => {
    setView(initialView || "all");
  }, [initialView]);

  useEffect(() => {
    if (!navigationRequest || !navigationRequest.nonce) return;
    if (navigationRequest.view) {
      setView(navigationRequest.view);
    }
    const nextExactIndicator = String(navigationRequest.exactIndicator || "").trim();
    if (navigationRequest.q != null) {
      const nextQ = String(navigationRequest.q || "").trim();
      setSearch(nextQ);
      setSearchInput(nextQ || nextExactIndicator);
    } else {
      setSearch("");
      setSearchInput(nextExactIndicator);
    }
    setExactIndicator(nextExactIndicator);
    setDispositionFilter("all");
    setOriginFilter("");
    setOutcomeFilter("");
    setEnforcementFilter("");
    setSort("updated_at_desc");
    setOffset(0);
    setRecords([]);
    setTotal(0);
    setError("");
    setRelatedAlertId(navigationRequest.relatedAlertId || null);
    setRelatedIncidentId(navigationRequest.relatedIncidentId || null);
    setRelatedPlaybookExecutionId(navigationRequest.relatedPlaybookExecutionId || null);
    setRelatedApprovalRequestId(navigationRequest.relatedApprovalRequestId || null);
    setSelectedId(null);
    setDetail(null);
  }, [navigationRequest]);

  const loadList = useCallback(
    async ({ quiet = false, nextOffset = offset } = {}) => {
      try {
        lastRequestedOffsetRef.current = nextOffset;
        if (quiet) {
          setRefreshing(true);
        } else {
          setLoading(true);
        }
        setError("");
        const data = await loadRegistryRecords({
          view,
          q: search || undefined,
          exactIndicator: exactIndicator || undefined,
          disposition: dispositionFilter,
          origin: originFilter || undefined,
          outcome: outcomeFilter || undefined,
          enforcement: enforcementFilter || undefined,
          relatedAlertId: relatedAlertId || undefined,
          relatedIncidentId: relatedIncidentId || undefined,
          sort,
          limit: PAGE_SIZE,
          offset: nextOffset,
        });
        setRecords(Array.isArray(data?.items) ? data.items : []);
        setTotal(Number(data?.total) || 0);
        setOffset(nextOffset);
      } catch (err) {
        setError(err.message || "Unable to load response registry.");
        if (!quiet) {
          setRecords([]);
          setTotal(0);
        }
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [
      view,
      search,
      exactIndicator,
      dispositionFilter,
      originFilter,
      outcomeFilter,
      enforcementFilter,
      relatedAlertId,
      relatedIncidentId,
      sort,
      offset,
    ]
  );

  const loadDetail = useCallback(async (registryId) => {
    if (!registryId) return;
    try {
      setDetailLoading(true);
      setDetailError("");
      const data = await loadRegistryDetail(registryId);
      setDetail(data);
    } catch (err) {
      setDetail(null);
      setDetailError(err.message || "Unable to load registry detail.");
    } finally {
      setDetailLoading(false);
    }
  }, []);

  useEffect(() => {
    loadList({ nextOffset: 0 });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    view,
    search,
    exactIndicator,
    dispositionFilter,
    originFilter,
    outcomeFilter,
    enforcementFilter,
    relatedAlertId,
    relatedIncidentId,
    sort,
  ]);

  useEffect(() => {
    return subscribe((keys) => {
      if (
        keysOverlap(keys, [
          "response_registry",
          "blocklist",
          relatedAlertId ? `alert:${relatedAlertId}` : null,
          relatedIncidentId ? `incident:${relatedIncidentId}` : null,
          relatedPlaybookExecutionId ? `playbook_execution:${relatedPlaybookExecutionId}` : null,
          relatedApprovalRequestId ? `approval_request:${relatedApprovalRequestId}` : null,
        ].filter(Boolean))
      ) {
        loadList({ quiet: true, nextOffset: offset });
        if (selectedId) {
          loadDetail(selectedId);
        }
      }
    });
  }, [
    subscribe,
    loadList,
    loadDetail,
    offset,
    selectedId,
    relatedAlertId,
    relatedIncidentId,
    relatedPlaybookExecutionId,
    relatedApprovalRequestId,
  ]);

  useEffect(() => {
    if (selectedId) {
      loadDetail(selectedId);
    }
  }, [selectedId, loadDetail]);

  const pageLabel = useMemo(() => {
    if (total === 0) return "0 of 0";
    const start = offset + 1;
    const end = Math.min(offset + records.length, total);
    return `${start}–${end} of ${total}`;
  }, [offset, records.length, total]);

  const record = detail?.record;
  const canMutate = Boolean(canTakeAlertActions);
  const restrictionTitle = "Viewers can review registry history but cannot mutate responses.";
  const latestEvent = detail?.latest_event ?? null;
  const currentOutcomeLabel = useMemo(
    () =>
      registryOutcomeLabel({
        currentDisposition: record?.current_disposition,
        latestOutcome: latestEvent?.outcome,
        latestRequestedAction: latestEvent?.requested_action,
        enforcement: latestEvent?.enforcement || detail?.enforcement,
        safeMetadata: latestEvent?.safe_metadata || {},
      }),
    [detail?.enforcement, latestEvent, record?.current_disposition]
  );
  const investigateTarget = useMemo(
    () =>
      registryInvestigateTarget(detail, {
        relatedAlertId,
        relatedIncidentId,
        sourceIp: record?.indicator_value,
      }),
    [detail, record?.indicator_value, relatedAlertId, relatedIncidentId]
  );
  const recommendedNextStep = useMemo(
    () =>
      registryRecommendedNextStep(detail, {
        relatedAlertId,
        relatedIncidentId,
        sourceIp: record?.indicator_value,
      }),
    [detail, record?.indicator_value, relatedAlertId, relatedIncidentId]
  );

  const runCommand = async (action, extras = {}) => {
    if (!canMutate || !record || submitLockRef.current) return;
    const indicatorValue = record.indicator_value;
    if (!indicatorValue) return;

    submitLockRef.current = true;
    setActionBusy(action);
    setFeedback({ type: "", message: "" });
    try {
      const result = await executeRegistryCommand({
        action,
        indicatorValue,
        reason: extras.reason,
        expiresAt: extras.expiresAt,
        alertId:
          extras.alertId ??
          detail?.relationships?.alerts?.primary_id ??
          latestEvent?.alert_id ??
          relatedAlertId ??
          null,
        incidentId:
          extras.incidentId ??
          detail?.relationships?.incidents?.primary_id ??
          latestEvent?.incident_id ??
          relatedIncidentId ??
          null,
        playbookExecutionId:
          extras.playbookExecutionId ??
          detail?.relationships?.playbooks?.primary_id ??
          latestEvent?.playbook_execution_id ??
          relatedPlaybookExecutionId ??
          null,
        approvalRequestId:
          extras.approvalRequestId ??
          detail?.relationships?.approvals?.primary_id ??
          latestEvent?.approval_request_id ??
          relatedApprovalRequestId ??
          null,
        idempotencyKey:
          extras.idempotencyKey ||
          `${action}-${record.id}-${Date.now()}`,
      });
      setFeedback({
        type: "success",
        message: formatCanonicalActionSuccess(result, action),
      });
      setNoteText("");
      setTrackReason("");
      setIncidentReason("");
      setMonitorExpiry("");
      publishMutation(result.affected_resource_keys || [], { action, result });
      await loadDetail(record.id);
      await loadList({ quiet: true, nextOffset: offset });
    } catch (err) {
      setFeedback({
        type: "error",
        message: err.message || "Command failed.",
      });
    } finally {
      setActionBusy("");
      submitLockRef.current = false;
    }
  };

  const handleCloseDetail = () => {
    setSelectedId(null);
    setDetail(null);
    setDetailError("");
    setFeedback({ type: "", message: "" });
  };

  const handleInvestigate = useCallback(() => {
    if (investigateTarget.kind === "incident" && typeof onOpenIncident === "function") {
      onOpenIncident(investigateTarget.id);
      return;
    }
    if (investigateTarget.kind === "alert" && typeof onOpenAlert === "function") {
      onOpenAlert(investigateTarget.id, investigateTarget.sourceIp || record?.indicator_value || "");
      return;
    }
    if (investigateTarget.kind === "source_ip" && typeof onOpenSourceContext === "function") {
      onOpenSourceContext(investigateTarget.sourceIp);
      return;
    }
    setFeedback({
      type: "info",
      message: investigateTarget.label,
    });
  }, [investigateTarget, onOpenIncident, onOpenAlert, onOpenSourceContext, record?.indicator_value]);

  const openRelationship = useCallback(
    (kind) => {
      if (kind === "alerts" && typeof onOpenAlert === "function") {
        const primaryId = detail?.relationships?.alerts?.primary_id;
        const sourceIp = detail?.primary_alert?.source_ip || record?.indicator_value || "";
        if (primaryId != null) {
          onOpenAlert(primaryId, sourceIp);
          return;
        }
      }
      if (kind === "incidents" && typeof onOpenIncident === "function") {
        const primaryId = detail?.relationships?.incidents?.primary_id;
        if (primaryId != null) {
          onOpenIncident(primaryId);
          return;
        }
      }
      if (kind === "playbooks" && typeof onOpenPlaybookExecution === "function") {
        const primaryId = detail?.relationships?.playbooks?.primary_id;
        if (primaryId != null) {
          onOpenPlaybookExecution(primaryId);
          return;
        }
      }
      if (kind === "approvals" && typeof onOpenApproval === "function") {
        const primaryId = detail?.relationships?.approvals?.primary_id;
        if (primaryId != null) {
          onOpenApproval(primaryId);
          return;
        }
      }
      setFeedback({
        type: "info",
        message: `No linked ${kind} destination is available for this record.`,
      });
    },
    [detail, onOpenAlert, onOpenApproval, onOpenIncident, onOpenPlaybookExecution, record?.indicator_value]
  );

  const feedbackStyle = feedbackStyles[feedback.type] || feedbackStyles.success;

  return (
    <section
      style={{ ...cardStyle, color: "#e6edf3" }}
      data-testid="response-registry-panel"
    >
      <div style={cardHeaderStyle}>
        <div>
          <h2 style={cardTitleStyle}>Response Registry</h2>
          <p style={cardSubtitleStyle}>
            Sole workspace for canonical indicator dispositions and Blocklist Tracking.
            Blocklist tracking is SIEM-only: Remove Tracking ends active tracking and preserves
            history; it never implies firewall, provider, or host enforcement changes.
          </p>
        </div>
        <button
          type="button"
          onClick={() => loadList({ quiet: true, nextOffset: offset })}
          disabled={loading || refreshing}
          style={secondaryButtonStyle(loading || refreshing)}
        >
          {refreshing ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      <div style={{ padding: "20px" }}>
      <div
        role="tablist"
        aria-label="Registry views"
        data-testid={`registry-view-${view}`}
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
          gap: "10px",
          marginBottom: "20px",
        }}
      >
        {REGISTRY_VIEWS.map((entry) => {
          const active = view === entry.id;
          return (
            <button
              key={entry.id}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => {
                setView(entry.id);
                setSelectedId(null);
                setDetail(null);
              }}
              style={{
                ...secondaryButtonStyle(false),
                background: active ? "#1f6feb" : "#21262d",
                color: active ? "#ffffff" : "#c9d1d9",
                borderColor: active ? "#1f6feb" : "#30363d",
                minHeight: "38px",
                width: "100%",
              }}
            >
              {entry.label}
            </button>
          );
        })}
      </div>

      {view === "blocklist_tracking" && (
        <div style={{ marginBottom: "20px" }} data-testid="registry-blocklist-embed">
          <BlocklistManagerPanel
            cardStyle={{
              ...cardStyle,
              margin: 0,
              border: "1px solid #30363d",
              boxShadow: "none",
            }}
            cardHeaderStyle={cardHeaderStyle}
            cardTitleStyle={cardTitleStyle}
            cardSubtitleStyle={cardSubtitleStyle}
            filterLabelStyle={filterLabelStyle}
            selectStyle={selectStyle}
            canTakeAlertActions={canTakeAlertActions}
            onMutationComplete={() => loadList({ quiet: true, nextOffset: 0 })}
          />
        </div>
      )}

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
          gap: "12px",
          marginBottom: "16px",
        }}
      >
        <label style={{ display: "grid", gap: "4px" }}>
          <span style={filterLabelStyle}>Search indicator</span>
          <input
            aria-label="Search indicator"
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                setSearch(searchInput.trim());
                setExactIndicator("");
              }
            }}
            placeholder="IP address"
            style={inputStyle}
          />
        </label>
        <label style={{ display: "grid", gap: "4px" }}>
          <span style={filterLabelStyle}>Disposition</span>
          <select
            aria-label="Disposition filter"
            value={dispositionFilter}
            onChange={(event) => setDispositionFilter(event.target.value)}
            style={selectStyle}
          >
            {DISPOSITION_FILTERS.map((value) => (
              <option key={value} value={value}>
                {value === "all" ? "All dispositions" : dispositionLabel(value)}
              </option>
            ))}
          </select>
        </label>
        <label style={{ display: "grid", gap: "4px" }}>
          <span style={filterLabelStyle}>Origin</span>
          <input
            aria-label="Origin filter"
            value={originFilter}
            onChange={(event) => setOriginFilter(event.target.value.trim())}
            placeholder="e.g. response_registry"
            style={inputStyle}
          />
        </label>
        <label style={{ display: "grid", gap: "4px" }}>
          <span style={filterLabelStyle}>Outcome</span>
          <input
            aria-label="Outcome filter"
            value={outcomeFilter}
            onChange={(event) => setOutcomeFilter(event.target.value.trim())}
            placeholder="e.g. succeeded"
            style={inputStyle}
          />
        </label>
        <label style={{ display: "grid", gap: "4px" }}>
          <span style={filterLabelStyle}>Enforcement</span>
          <input
            aria-label="Enforcement filter"
            value={enforcementFilter}
            onChange={(event) => setEnforcementFilter(event.target.value.trim())}
            placeholder="none"
            style={inputStyle}
          />
        </label>
        <label style={{ display: "grid", gap: "4px" }}>
          <span style={filterLabelStyle}>Sort</span>
          <select
            aria-label="Sort registry"
            value={sort}
            onChange={(event) => setSort(event.target.value)}
            style={selectStyle}
          >
            {SORT_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <div style={{ display: "flex", alignItems: "end", gap: "8px" }}>
          <button
            type="button"
            onClick={() => {
              setSearch(searchInput.trim());
              setExactIndicator("");
            }}
            style={buttonStyle(false)}
          >
            Apply search
          </button>
        </div>
      </div>

      {error && (
        <div
          role="alert"
          style={{
            marginBottom: "12px",
            padding: "10px 12px",
            borderRadius: "6px",
            border: "1px solid #f85149",
            color: "#ffa198",
            background: "#3d1214",
          }}
        >
          {error}{" "}
          <button
            type="button"
            onClick={() => loadList({ nextOffset: lastRequestedOffsetRef.current })}
            style={secondaryButtonStyle(false)}
          >
            Retry
          </button>
        </div>
      )}

      {feedback.message && (
        <div
          role="status"
          style={{
            marginBottom: "12px",
            padding: "10px 12px",
            borderRadius: "6px",
            border: `1px solid ${feedbackStyle.border}`,
            color: feedbackStyle.color,
            background: feedbackStyle.background,
          }}
        >
          {feedback.message}
        </div>
      )}
      )}

      <div style={{ display: "grid", gridTemplateColumns: selectedId ? "1.2fr 1fr" : "1fr", gap: "16px" }}>
        <div>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              marginBottom: "8px",
              color: "#8b949e",
              fontSize: "13px",
            }}
          >
            <span>{pageLabel}</span>
            <div style={{ display: "flex", gap: "8px" }}>
              <button
                type="button"
                disabled={offset <= 0 || loading}
                onClick={() => loadList({ nextOffset: Math.max(0, offset - PAGE_SIZE) })}
                style={secondaryButtonStyle(offset <= 0 || loading)}
              >
                Previous
              </button>
              <button
                type="button"
                disabled={offset + PAGE_SIZE >= total || loading}
                onClick={() => loadList({ nextOffset: offset + PAGE_SIZE })}
                style={secondaryButtonStyle(offset + PAGE_SIZE >= total || loading)}
              >
                Next
              </button>
            </div>
          </div>

          {loading ? (
            <p aria-live="polite">Loading response registry…</p>
          ) : records.length === 0 ? (
            <p aria-live="polite">
              {exactIndicator || relatedAlertId || relatedIncidentId
                ? "No response registry records match the requested context."
                : "No registry records match the current filters."}
            </p>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "13px" }}>
                <thead>
                  <tr style={{ textAlign: "left", color: "#8b949e" }}>
                    <th style={{ padding: "8px" }}>Indicator</th>
                    <th style={{ padding: "8px" }}>Disposition</th>
                    <th style={{ padding: "8px" }}>Action</th>
                    <th style={{ padding: "8px" }}>Outcome</th>
                    <th style={{ padding: "8px" }}>Enforcement</th>
                    <th style={{ padding: "8px" }}>Origin</th>
                    <th style={{ padding: "8px" }}>Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {records.map((item) => {
                    const selected = selectedId === item.id;
                    return (
                      <tr
                        key={item.id}
                        onClick={() => setSelectedId(item.id)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" || event.key === " ") {
                            event.preventDefault();
                            setSelectedId(item.id);
                          }
                        }}
                        tabIndex={0}
                        aria-label={`Registry record ${item.indicator_value}`}
                        aria-selected={selected}
                        style={{
                          cursor: "pointer",
                          background: selected ? "#1c2128" : "transparent",
                          borderTop: "1px solid #21262d",
                        }}
                      >
                        <td style={{ padding: "8px", fontFamily: "monospace" }}>
                          {item.indicator_value}
                        </td>
                        <td style={{ padding: "8px" }}>
                          {dispositionLabel(item.current_disposition)}
                        </td>
                        <td style={{ padding: "8px" }}>
                          {item.latest_requested_action || "—"}
                        </td>
                        <td style={{ padding: "8px" }}>
                          <span
                            style={outcomeBadgeStyle(
                              registryOutcomeLabel({
                                currentDisposition: item.current_disposition,
                                latestOutcome: item.latest_outcome,
                                latestRequestedAction: item.latest_requested_action,
                                enforcement: item.enforcement,
                              })
                            )}
                          >
                            {registryOutcomeLabel({
                              currentDisposition: item.current_disposition,
                              latestOutcome: item.latest_outcome,
                              latestRequestedAction: item.latest_requested_action,
                              enforcement: item.enforcement,
                            })}
                          </span>
                        </td>
                        <td style={{ padding: "8px" }}>{item.enforcement || "none"}</td>
                        <td style={{ padding: "8px" }}>
                          {item.latest_origin_surface || "—"}
                        </td>
                        <td style={{ padding: "8px" }}>
                          {formatTimestamp(item.updated_at) || "—"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {selectedId && (
          <aside
            aria-label="Registry detail"
            style={{
              border: "1px solid #30363d",
              borderRadius: "8px",
              padding: "14px",
              background: "#0d1117",
              minHeight: "320px",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", gap: "8px", flexWrap: "wrap" }}>
              <h3 style={{ margin: 0, fontSize: "16px" }}>Indicator detail</h3>
              <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", justifyContent: "flex-end" }}>
                {aiEnabled && record && typeof onAskAi === "function" ? (
                  <AiAssistantButton
                    onClick={() =>
                      onAskAi({
                        contextType: "response_registry",
                        action: "explain_response",
                        title: `Response registry #${record.id}`,
                        question: "Explain this response registry record and its current response state.",
                        context: { registry_id: record.id },
                      })
                    }
                  >
                    Explain this response
                  </AiAssistantButton>
                ) : null}
                <button type="button" onClick={handleCloseDetail} style={secondaryButtonStyle(false)}>
                  Close
                </button>
              </div>
            </div>

            {detailLoading && <p aria-live="polite">Loading detail…</p>}
            {detailError && (
              <div role="alert" style={{ color: "#ffa198", display: "grid", gap: "8px" }}>
                <span>{detailError}</span>
                <button
                  type="button"
                  onClick={() => loadDetail(selectedId)}
                  style={secondaryButtonStyle(false)}
                >
                  Retry detail
                </button>
              </div>
            )}

            {!detailLoading && record && (
              <>
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "start",
                    gap: "10px",
                    marginTop: "12px",
                    marginBottom: "14px",
                  }}
                >
                  <div style={{ display: "grid", gap: "8px", flex: 1 }}>
                    <div>
                      <div style={{ color: "#8b949e", fontSize: "12px", marginBottom: "4px" }}>
                        Response Summary
                      </div>
                      <div
                        style={{
                          display: "grid",
                          gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
                          gap: "10px",
                          fontSize: "13px",
                        }}
                      >
                        <div>
                          <div style={{ color: "#8b949e" }}>Alert</div>
                          <p style={summaryValueStyle()}>
                            {detail.primary_alert
                              ? `#${detail.primary_alert.id} · ${detail.primary_alert.alert_type || "Alert"}`
                              : "None recorded"}
                          </p>
                        </div>
                        <div>
                          <div style={{ color: "#8b949e" }}>Indicator</div>
                          <p style={summaryValueStyle(true)}>{record.indicator_value}</p>
                        </div>
                        <div>
                          <div style={{ color: "#8b949e" }}>Response</div>
                          <p style={summaryValueStyle()}>
                            {registryActionLabel(
                              latestEvent?.requested_action,
                              record.current_disposition
                            )}
                          </p>
                        </div>
                        <div>
                          <div style={{ color: "#8b949e" }}>Outcome</div>
                          <span style={outcomeBadgeStyle(currentOutcomeLabel)}>
                            {currentOutcomeLabel}
                          </span>
                        </div>
                      </div>
                    </div>
                    <div>
                      <div style={{ color: "#8b949e", fontSize: "12px", marginBottom: "4px" }}>
                        Recommended Next Step
                      </div>
                      <p style={{ margin: 0, fontSize: "13px" }}>{recommendedNextStep}</p>
                    </div>
                    <div>
                      <div style={{ color: "#8b949e", fontSize: "12px", marginBottom: "6px" }}>
                        Related
                      </div>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: "8px" }}>
                        {[
                          ["alerts", "Alerts", detail.relationships?.alerts?.count || 0],
                          ["incidents", "Incident", detail.relationships?.incidents?.count || 0],
                          ["playbooks", "Playbook", detail.relationships?.playbooks?.count || 0],
                          ["approvals", "Approvals", detail.relationships?.approvals?.count || 0],
                        ].map(([kind, label, count]) => (
                          <button
                            key={kind}
                            type="button"
                            disabled={!count}
                            onClick={() => openRelationship(kind)}
                            style={{
                              ...linkButtonStyle,
                              opacity: count ? 1 : 0.55,
                              cursor: count ? "pointer" : "not-allowed",
                            }}
                          >
                            {label} ({count})
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>
                  <div style={{ display: "grid", gap: "8px" }}>
                    <button
                      type="button"
                      onClick={handleInvestigate}
                      style={buttonStyle(false)}
                    >
                      Investigate
                    </button>
                    {investigateTarget.kind === "none" ? (
                      <p style={{ margin: 0, color: "#8b949e", fontSize: "12px", maxWidth: "220px" }}>
                        {investigateTarget.label}
                      </p>
                    ) : null}
                  </div>
                </div>

                <dl style={{ display: "grid", gridTemplateColumns: "140px 1fr", gap: "8px", fontSize: "13px" }}>
                  <dt style={{ color: "#8b949e" }}>Current state</dt>
                  <dd style={{ margin: 0 }}>{dispositionSummaryLabel(record.current_disposition) || dispositionLabel(record.current_disposition)}</dd>
                  <dt style={{ color: "#8b949e" }}>First seen</dt>
                  <dd style={{ margin: 0 }}>{formatTimestamp(detail.first_seen) || "—"}</dd>
                  <dt style={{ color: "#8b949e" }}>Last updated</dt>
                  <dd style={{ margin: 0 }}>{formatTimestamp(detail.last_updated) || "—"}</dd>
                  <dt style={{ color: "#8b949e" }}>Response source</dt>
                  <dd style={{ margin: 0 }}>{detail.response_source || "—"}</dd>
                  <dt style={{ color: "#8b949e" }}>Enforcement</dt>
                  <dd style={{ margin: 0 }}>{detail.enforcement_statement}</dd>
                </dl>

                {detail.blocklist_entry ? (
                  <div
                    style={{
                      marginTop: "12px",
                      padding: "10px",
                      borderRadius: "6px",
                      border: "1px solid #388bfd",
                      background: "#0d1b2a",
                    }}
                    data-testid="registry-blocklist-status"
                  >
                    <strong>
                      {detail.blocklist_entry.status === "active"
                        ? "Blocklist tracking active"
                        : `Blocklist tracking ${detail.blocklist_entry.status}`}
                    </strong>
                    <p style={{ margin: "6px 0 0", fontSize: "13px", color: "#c9d1d9" }}>
                      Status: {detail.blocklist_entry.status}. Tracking only; no firewall
                      enforcement. Reason: {detail.blocklist_entry.reason || "—"}.
                      Expires: {formatTimestamp(detail.blocklist_entry.expires_at) || "never"}.
                      {detail.blocklist_entry.status !== "active"
                        ? " Historical evidence remains readable."
                        : " Use Remove Tracking below to end active SIEM tracking without changing any firewall."}
                    </p>
                  </div>
                ) : (
                  <p
                    data-testid="registry-blocklist-absent"
                    style={{ marginTop: "12px", color: "#8b949e", fontSize: "13px" }}
                  >
                    No linked Blocklist tracking record. Open the Blocklist Tracking view to
                    manage SIEM tracking entries, or use Track in Blocklist.
                  </p>
                )}

                <div style={{ marginTop: "16px" }}>
                  <h4 style={{ margin: "0 0 8px", fontSize: "14px" }}>Actions</h4>
                  {!canMutate && (
                    <p title={restrictionTitle} style={{ color: "#8b949e", fontSize: "13px" }}>
                      Mutation controls are locked for this role. {restrictionTitle}
                    </p>
                  )}
                  <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", marginBottom: "10px" }}>
                    <button
                      type="button"
                      disabled={!canMutate || Boolean(actionBusy)}
                      title={canMutate ? "Start or renew monitoring" : restrictionTitle}
                      aria-disabled={!canMutate}
                      onClick={() =>
                        runCommand("monitor", {
                          reason: "Monitor from Response Registry",
                          expiresAt: monitorExpiry
                            ? new Date(monitorExpiry).toISOString()
                            : undefined,
                        })
                      }
                      style={buttonStyle(!canMutate || Boolean(actionBusy))}
                    >
                      {actionBusy === "monitor" ? "Working…" : "Monitor"}
                    </button>
                    <button
                      type="button"
                      disabled={
                        !canMutate ||
                        Boolean(actionBusy) ||
                        record.current_disposition !== "monitored"
                      }
                      title={canMutate ? "Stop monitoring" : restrictionTitle}
                      aria-disabled={!canMutate}
                      onClick={() => runCommand("stop_monitor", { reason: "Stopped from registry" })}
                      style={secondaryButtonStyle(
                        !canMutate ||
                          Boolean(actionBusy) ||
                          record.current_disposition !== "monitored"
                      )}
                    >
                      {actionBusy === "stop_monitor" ? "Working…" : "Stop Monitoring"}
                    </button>
                    <button
                      type="button"
                      disabled={!canMutate || Boolean(actionBusy)}
                      title={canMutate ? "Track in Blocklist (tracking only)" : restrictionTitle}
                      aria-disabled={!canMutate}
                      onClick={() =>
                        runCommand("block_ip", {
                          reason: trackReason || "Tracked from Response Registry",
                        })
                      }
                      style={buttonStyle(!canMutate || Boolean(actionBusy))}
                    >
                      {actionBusy === "block_ip" ? "Working…" : "Track in Blocklist"}
                    </button>
                    <button
                      type="button"
                      disabled={
                        !canMutate ||
                        Boolean(actionBusy) ||
                        !detail.blocklist_entry ||
                        detail.blocklist_entry.status !== "active"
                      }
                      title={removeTrackingControlTitle(
                        canMutate,
                        restrictionTitle,
                        detail.blocklist_entry
                      )}
                      aria-disabled={
                        !canMutate ||
                        !detail.blocklist_entry ||
                        detail.blocklist_entry.status !== "active"
                      }
                      onClick={() =>
                        runCommand("remove_tracking", { reason: "Removed from registry" })
                      }
                      style={secondaryButtonStyle(
                        !canMutate ||
                          Boolean(actionBusy) ||
                          !detail.blocklist_entry ||
                          detail.blocklist_entry.status !== "active"
                      )}
                    >
                      {actionBusy === "remove_tracking" ? "Working…" : "Remove Tracking"}
                    </button>
                    <button
                      type="button"
                      disabled={!canMutate || Boolean(actionBusy)}
                      title={canMutate ? "Create or link an incident" : restrictionTitle}
                      aria-disabled={!canMutate}
                      onClick={() =>
                        runCommand("flag_high_priority", {
                          reason: incidentReason || "Create or link incident from Response Registry",
                        })
                      }
                      style={buttonStyle(!canMutate || Boolean(actionBusy))}
                    >
                      {actionBusy === "flag_high_priority" ? "Working…" : "Create / Link Incident"}
                    </button>
                  </div>

                  <label style={{ display: "grid", gap: "4px", marginBottom: "8px" }}>
                    <span style={filterLabelStyle}>Monitor expiry (optional)</span>
                    <input
                      type="datetime-local"
                      value={monitorExpiry}
                      disabled={!canMutate}
                      onChange={(event) => setMonitorExpiry(event.target.value)}
                      style={inputStyle}
                    />
                  </label>
                  <label style={{ display: "grid", gap: "4px", marginBottom: "8px" }}>
                    <span style={filterLabelStyle}>Tracking reason</span>
                    <input
                      value={trackReason}
                      disabled={!canMutate}
                      onChange={(event) => setTrackReason(event.target.value)}
                      style={inputStyle}
                    />
                  </label>
                  <label style={{ display: "grid", gap: "4px", marginBottom: "8px" }}>
                    <span style={filterLabelStyle}>Incident reason</span>
                    <input
                      value={incidentReason}
                      disabled={!canMutate}
                      onChange={(event) => setIncidentReason(event.target.value)}
                      style={inputStyle}
                    />
                  </label>
                  <label style={{ display: "grid", gap: "4px" }}>
                    <span style={filterLabelStyle}>Add note</span>
                    <textarea
                      value={noteText}
                      disabled={!canMutate || Boolean(actionBusy)}
                      onChange={(event) => setNoteText(event.target.value)}
                      rows={3}
                      style={{ ...inputStyle, resize: "vertical" }}
                    />
                  </label>
                  <button
                    type="button"
                    disabled={!canMutate || Boolean(actionBusy) || !noteText.trim()}
                    title={canMutate ? "Append note to history" : restrictionTitle}
                    aria-disabled={!canMutate}
                    onClick={() => runCommand("add_note", { reason: noteText.trim() })}
                    style={{
                      ...buttonStyle(!canMutate || Boolean(actionBusy) || !noteText.trim()),
                      marginTop: "8px",
                    }}
                  >
                    {actionBusy === "add_note" ? "Saving…" : "Save note"}
                  </button>
                </div>

                <div style={{ marginTop: "18px" }}>
                  <h4 style={{ margin: "0 0 8px", fontSize: "14px" }}>Response history</h4>
                  {(detail.events || []).length === 0 ? (
                    <p style={{ color: "#8b949e", fontSize: "13px" }}>No events recorded.</p>
                  ) : (
                    <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
                      {detail.events.map((event) => (
                        <li
                          key={event.id}
                          style={{
                            borderTop: "1px solid #21262d",
                            padding: "8px 0",
                            fontSize: "12px",
                          }}
                        >
                          <div>
                            <strong>{event.event_type}</strong> ·{" "}
                            {actionSummaryLabel(event.requested_action) || event.requested_action} ·{" "}
                            <span style={outcomeBadgeStyle(
                              registryOutcomeLabel({
                                currentDisposition: event.disposition_after,
                                latestOutcome: event.outcome,
                                latestRequestedAction: event.requested_action,
                                enforcement: event.enforcement,
                                safeMetadata: event.safe_metadata || {},
                              })
                            )}>
                              {registryOutcomeLabel({
                                currentDisposition: event.disposition_after,
                                latestOutcome: event.outcome,
                                latestRequestedAction: event.requested_action,
                                enforcement: event.enforcement,
                                safeMetadata: event.safe_metadata || {},
                              })}
                            </span>
                          </div>
                          <div style={{ color: "#8b949e" }}>
                            {formatTimestamp(event.created_at)} · {event.origin_surface || "—"} ·
                            disposition {dispositionSummaryLabel(event.disposition_after) || dispositionLabel(event.disposition_after)}
                          </div>
                          {event.reason && <div>{event.reason}</div>}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </>
            )}
          </aside>
        )}
      </div>
      </div>
    </section>
  );
}

export default ResponseRegistryPanel;
