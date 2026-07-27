import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  loadReconActivities,
  loadReconActivity,
  loadReconActivityAlerts,
} from "../services/reconActivityService";

const PAGE_SIZE = 20;
const LINKED_ALERT_PAGE_SIZE = 10;

const defaultFilters = {
  search: "",
  status: "",
  severity: "",
  confidence: "",
  classification: "",
  timeRange: "30d",
  sort: "last_seen_desc",
};

function titleCase(value) {
  return String(value || "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatDate(value) {
  if (!value) return "Unavailable";
  try {
    return new Intl.DateTimeFormat(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(value));
  } catch (_error) {
    return value;
  }
}

function Badge({ children, tone = "neutral" }) {
  return <span style={{ ...badgeStyle, ...(badgeToneStyles[tone] || badgeToneStyles.neutral) }}>{children}</span>;
}

function EmptyState({ children }) {
  return <div style={emptyStateStyle}>{children}</div>;
}

function ReconWorkspace({
  onViewRelatedAlerts = null,
  onOpenIncident = null,
  restoreRequest = null,
  onHistoryStateChange = null,
}) {
  const [filters, setFilters] = useState(defaultFilters);
  const [draftSearch, setDraftSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [listState, setListState] = useState({ items: [], total: 0, loading: true, error: "" });
  const [selectedId, setSelectedId] = useState(null);
  const [detailState, setDetailState] = useState({ detail: null, loading: false, error: "" });
  const [alertOffset, setAlertOffset] = useState(0);
  const [linkedAlerts, setLinkedAlerts] = useState({ items: [], total: 0, loading: false, error: "" });
  const handledRestoreNonceRef = useRef(null);

  const loadList = useCallback(() => {
    setListState((current) => ({ ...current, loading: true, error: "" }));
    loadReconActivities({
      limit: PAGE_SIZE,
      offset,
      search: filters.search || undefined,
      status: filters.status || undefined,
      severity: filters.severity || undefined,
      confidence: filters.confidence || undefined,
      classification: filters.classification || undefined,
      timeRange: filters.timeRange || undefined,
      sort: filters.sort,
    })
      .then((payload) => {
        const items = Array.isArray(payload.items) ? payload.items : [];
        setListState({
          items,
          total: Number(payload.total ?? payload.count ?? items.length),
          loading: false,
          error: "",
        });
        setSelectedId((current) => {
          if (current && items.some((item) => String(item.id) === String(current))) return current;
          return items[0]?.id ?? null;
        });
      })
      .catch((error) => {
        setListState((current) => ({
          ...current,
          loading: false,
          error: error.message || "Unable to load recon history",
        }));
      });
  }, [filters, offset]);

  useEffect(() => {
    loadList();
  }, [loadList]);

  useEffect(() => {
    if (!selectedId) {
      setDetailState({ detail: null, loading: false, error: "" });
      setLinkedAlerts({ items: [], total: 0, loading: false, error: "" });
      return;
    }
    let isCurrent = true;
    setDetailState((current) => ({ ...current, loading: true, error: "" }));
    loadReconActivity(selectedId)
      .then((detail) => {
        if (!isCurrent) return;
        setDetailState({ detail, loading: false, error: "" });
      })
      .catch((error) => {
        if (!isCurrent) return;
        setDetailState({ detail: null, loading: false, error: error.message || "Unable to load recon detail" });
      });
    return () => {
      isCurrent = false;
    };
  }, [selectedId]);

  useEffect(() => {
    if (!restoreRequest || handledRestoreNonceRef.current === restoreRequest.nonce) return;
    const state = restoreRequest.state?.recon || {};
    handledRestoreNonceRef.current = restoreRequest.nonce;
    if (state.filters && typeof state.filters === "object") {
      const nextFilters = { ...defaultFilters, ...state.filters };
      setFilters(nextFilters);
      setDraftSearch(nextFilters.search || "");
    }
    if (Number.isFinite(Number(state.offset))) {
      setOffset(Math.max(0, Number(state.offset)));
    }
    setSelectedId(state.selectedId ?? null);
    if (Number.isFinite(Number(state.alertOffset))) {
      setAlertOffset(Math.max(0, Number(state.alertOffset)));
    }
  }, [restoreRequest]);

  useEffect(() => {
    if (typeof onHistoryStateChange !== "function") return;
    onHistoryStateChange({
      filters,
      draftSearch,
      offset,
      selectedId,
      alertOffset,
    });
  }, [alertOffset, draftSearch, filters, offset, onHistoryStateChange, selectedId]);

  useEffect(() => {
    if (!selectedId) return;
    let isCurrent = true;
    setLinkedAlerts((current) => ({ ...current, loading: true, error: "" }));
    loadReconActivityAlerts(selectedId, { limit: LINKED_ALERT_PAGE_SIZE, offset: alertOffset })
      .then((payload) => {
        if (!isCurrent) return;
        const items = Array.isArray(payload.items) ? payload.items : [];
        setLinkedAlerts({
          items,
          total: Number(payload.total ?? payload.count ?? items.length),
          loading: false,
          error: "",
        });
      })
      .catch((error) => {
        if (!isCurrent) return;
        setLinkedAlerts((current) => ({
          ...current,
          loading: false,
          error: error.message || "Unable to load linked alerts",
        }));
      });
    return () => {
      isCurrent = false;
    };
  }, [selectedId, alertOffset]);

  const pageEnd = Math.min(offset + PAGE_SIZE, listState.total);
  const linkedAlertEnd = Math.min(alertOffset + LINKED_ALERT_PAGE_SIZE, linkedAlerts.total);
  const canReset = useMemo(
    () => JSON.stringify(filters) !== JSON.stringify(defaultFilters) || offset !== 0,
    [filters, offset]
  );
  const selectedDetail = detailState.detail;
  const intelligence = selectedDetail?.recon_intelligence || selectedDetail?.summary?.recon_intelligence || {};

  const updateFilter = (field, value) => {
    setFilters((current) => ({ ...current, [field]: value }));
    setOffset(0);
  };

  return (
    <section style={panelStyle}>
      <div style={panelHeaderStyle}>
        <div>
          <p style={sectionLabelStyle}>Recon Workspace</p>
          <h2 style={titleStyle}>Distributed recon history</h2>
          <p style={subtitleStyle}>
            Complete paginated recon activity with evidence tiers and linked alert pivots.
          </p>
        </div>
        <button type="button" onClick={loadList} style={secondaryButtonStyle}>
          {listState.loading ? "Refreshing..." : "Refresh"}
        </button>
      </div>

      <div style={filterBarStyle}>
        <label style={filterLabelStyle}>
          Search
          <form
            onSubmit={(event) => {
              event.preventDefault();
              updateFilter("search", draftSearch.trim());
            }}
            style={searchFormStyle}
          >
            <input
              value={draftSearch}
              onChange={(event) => setDraftSearch(event.target.value)}
              placeholder="Source, target, service, assessment"
              style={inputStyle}
            />
            <button type="submit" style={secondaryButtonStyle}>Apply</button>
          </form>
        </label>
        <SelectFilter label="Time" value={filters.timeRange} onChange={(value) => updateFilter("timeRange", value)}>
          <option value="24h">Last 24 hours</option>
          <option value="7d">Last 7 days</option>
          <option value="30d">Last 30 days</option>
          <option value="90d">Last 90 days</option>
          <option value="all">All history</option>
        </SelectFilter>
        <SelectFilter label="Status" value={filters.status} onChange={(value) => updateFilter("status", value)}>
          <option value="">All</option>
          <option value="open">Open</option>
          <option value="monitoring">Monitoring</option>
          <option value="resolved">Resolved</option>
        </SelectFilter>
        <SelectFilter label="Severity" value={filters.severity} onChange={(value) => updateFilter("severity", value)}>
          <option value="">All</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </SelectFilter>
        <SelectFilter label="Confidence" value={filters.confidence} onChange={(value) => updateFilter("confidence", value)}>
          <option value="">All</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </SelectFilter>
        <SelectFilter label="Tier" value={filters.classification} onChange={(value) => updateFilter("classification", value)}>
          <option value="">All</option>
          <option value="campaign_recon">Campaign Recon</option>
          <option value="possible_campaign">Possible Campaign</option>
          <option value="recon_cluster">Recon Cluster</option>
        </SelectFilter>
        <SelectFilter label="Sort" value={filters.sort} onChange={(value) => updateFilter("sort", value)}>
          <option value="last_seen_desc">Last seen newest</option>
          <option value="last_seen_asc">Last seen oldest</option>
          <option value="first_seen_desc">First seen newest</option>
          <option value="severity_desc">Severity</option>
        </SelectFilter>
        <button
          type="button"
          disabled={!canReset}
          onClick={() => {
            setFilters(defaultFilters);
            setDraftSearch("");
            setOffset(0);
          }}
          style={{ ...secondaryButtonStyle, opacity: canReset ? 1 : 0.5 }}
        >
          Reset
        </button>
      </div>

      {listState.error ? <div style={warningStyle}>{listState.error}</div> : null}

      <div style={workspaceGridStyle}>
        <div style={listPaneStyle}>
          <div style={paneHeaderStyle}>
            <strong>History</strong>
            <span style={mutedTextStyle}>
              {listState.total === 0 ? "0 records" : `${offset + 1}-${pageEnd} of ${listState.total}`}
            </span>
          </div>
          {listState.loading && listState.items.length === 0 ? (
            <EmptyState>Loading recon history...</EmptyState>
          ) : listState.items.length === 0 ? (
            <EmptyState>No recon activity matches the current filters.</EmptyState>
          ) : (
            listState.items.map((activity) => {
              const itemIntel = activity.recon_intelligence || {};
              return (
                <button
                  key={activity.id}
                  type="button"
                  onClick={() => {
                    setSelectedId(activity.id);
                    setAlertOffset(0);
                  }}
                  style={{
                    ...activityButtonStyle,
                    ...(String(selectedId) === String(activity.id) ? activityButtonActiveStyle : {}),
                  }}
                >
                  <span style={activityTitleStyle}>{activity.display?.headline || activity.label}</span>
                  <span style={activityMetaStyle}>
                    {titleCase(itemIntel.classification || "recon_cluster")} · {titleCase(itemIntel.confidence || "low")} confidence
                  </span>
                  <span style={activityMetaStyle}>
                    {activity.display?.target_summary || activity.protected_range_key || "Target unavailable"} · {formatDate(activity.last_seen)}
                  </span>
                </button>
              );
            })
          )}
          <Pagination
            offset={offset}
            pageSize={PAGE_SIZE}
            total={listState.total}
            onPrevious={() => setOffset(Math.max(offset - PAGE_SIZE, 0))}
            onNext={() => setOffset(offset + PAGE_SIZE)}
          />
        </div>

        <div style={detailPaneStyle}>
          {detailState.loading ? (
            <EmptyState>Loading recon detail...</EmptyState>
          ) : detailState.error ? (
            <div style={warningStyle}>{detailState.error}</div>
          ) : !selectedDetail ? (
            <EmptyState>Select recon activity to review evidence.</EmptyState>
          ) : (
            <>
              <div style={detailHeaderStyle}>
                <div>
                  <p style={sectionLabelStyle}>Recon Activity #{selectedDetail.id}</p>
                  <h3 style={detailTitleStyle}>{selectedDetail.display?.headline || selectedDetail.label}</h3>
                  <p style={subtitleStyle}>{selectedDetail.assessment_text}</p>
                </div>
                <div style={badgeRowStyle}>
                  <Badge tone={intelligence.classification === "campaign_recon" ? "warning" : "info"}>
                    {titleCase(intelligence.classification || "recon_cluster")}
                  </Badge>
                  <Badge tone={intelligence.confidence === "high" ? "warning" : "neutral"}>
                    {titleCase(intelligence.confidence || "low")} confidence
                  </Badge>
                </div>
              </div>

              <dl style={summaryGridStyle}>
                <Metric label="Linked alerts" value={selectedDetail.display?.linked_alert_count ?? 0} />
                <Metric label="Sources" value={(selectedDetail.summary?.source_ip_count ?? 0)} />
                <Metric label="Duration" value={`${intelligence.duration_minutes ?? 0} min`} />
                <Metric label="Incident" value={selectedDetail.related_incident_id ? `#${selectedDetail.related_incident_id}` : "None"} />
              </dl>

              <EvidenceList title="Evidence" items={intelligence.reasons || []} empty="No campaign-grade evidence yet." />
              <EvidenceList title="Missing evidence" items={intelligence.missing_evidence || []} empty="No missing evidence reported." />

              <div style={pivotRowStyle}>
                {typeof onViewRelatedAlerts === "function" && selectedDetail.display?.representative_source ? (
                  <button type="button" style={linkButtonStyle} onClick={() => onViewRelatedAlerts({ sourceIp: selectedDetail.display.representative_source })}>
                    View alerts for source
                  </button>
                ) : null}
                {typeof onViewRelatedAlerts === "function" && selectedDetail.display?.primary_target ? (
                  <button type="button" style={linkButtonStyle} onClick={() => onViewRelatedAlerts({ targetIp: selectedDetail.display.primary_target })}>
                    View alerts for target
                  </button>
                ) : null}
                {typeof onOpenIncident === "function" && selectedDetail.related_incident_id ? (
                  <button type="button" style={linkButtonStyle} onClick={() => onOpenIncident(selectedDetail.related_incident_id)}>
                    Open incident
                  </button>
                ) : null}
              </div>

              <section style={linkedAlertsStyle} aria-label="Linked alerts">
                <div style={paneHeaderStyle}>
                  <strong>Linked alerts</strong>
                  <span style={mutedTextStyle}>
                    {linkedAlerts.total === 0 ? "0 alerts" : `${alertOffset + 1}-${linkedAlertEnd} of ${linkedAlerts.total}`}
                  </span>
                </div>
                {linkedAlerts.error ? <div style={warningStyle}>{linkedAlerts.error}</div> : null}
                {linkedAlerts.loading && linkedAlerts.items.length === 0 ? (
                  <EmptyState>Loading linked alerts...</EmptyState>
                ) : linkedAlerts.items.length === 0 ? (
                  <EmptyState>No linked alerts found.</EmptyState>
                ) : (
                  linkedAlerts.items.map((alert) => (
                    <div key={alert.id} style={alertRowStyle}>
                      <div>
                        <strong>#{alert.id} {alert.alert_type}</strong>
                        <p style={mutedTextStyle}>{alert.source_ip || "No source"} · {formatDate(alert.created_at)}</p>
                      </div>
                      <Badge tone={String(alert.severity).toLowerCase() === "high" ? "warning" : "neutral"}>
                        {titleCase(alert.severity)}
                      </Badge>
                    </div>
                  ))
                )}
                <Pagination
                  offset={alertOffset}
                  pageSize={LINKED_ALERT_PAGE_SIZE}
                  total={linkedAlerts.total}
                  onPrevious={() => setAlertOffset(Math.max(alertOffset - LINKED_ALERT_PAGE_SIZE, 0))}
                  onNext={() => setAlertOffset(alertOffset + LINKED_ALERT_PAGE_SIZE)}
                />
              </section>
            </>
          )}
        </div>
      </div>
    </section>
  );
}

function SelectFilter({ label, value, onChange, children }) {
  return (
    <label style={filterLabelStyle}>
      {label}
      <select value={value} onChange={(event) => onChange(event.target.value)} style={selectStyle}>
        {children}
      </select>
    </label>
  );
}

function Metric({ label, value }) {
  return (
    <div>
      <dt style={metricLabelStyle}>{label}</dt>
      <dd style={metricValueStyle}>{value}</dd>
    </div>
  );
}

function EvidenceList({ title, items, empty }) {
  return (
    <section style={evidenceSectionStyle}>
      <h4 style={sectionTitleStyle}>{title}</h4>
      {items.length === 0 ? (
        <p style={mutedTextStyle}>{empty}</p>
      ) : (
        <ul style={evidenceListStyle}>
          {items.map((item) => (
            <li key={item.id || item.text} style={evidenceItemStyle}>{item.text || item.id}</li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Pagination({ offset, pageSize, total, onPrevious, onNext }) {
  return (
    <div style={paginationStyle}>
      <button type="button" onClick={onPrevious} disabled={offset <= 0} style={secondaryButtonStyle}>
        Previous
      </button>
      <button type="button" onClick={onNext} disabled={offset + pageSize >= total} style={secondaryButtonStyle}>
        Next
      </button>
    </div>
  );
}

const panelStyle = { display: "flex", flexDirection: "column", gap: "18px" };
const panelHeaderStyle = { display: "flex", justifyContent: "space-between", gap: "16px", alignItems: "flex-start", flexWrap: "wrap" };
const sectionLabelStyle = { margin: 0, color: "#7dd3fc", fontSize: "0.74rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0" };
const titleStyle = { margin: "4px 0 0", color: "#f8fafc", fontSize: "1.55rem", letterSpacing: "0" };
const subtitleStyle = { margin: "6px 0 0", color: "#94a3b8", lineHeight: 1.5 };
const filterBarStyle = { display: "flex", gap: "12px", flexWrap: "wrap", alignItems: "flex-end", padding: "14px", border: "1px solid #30363d", background: "#0f172a", borderRadius: "8px" };
const filterLabelStyle = { display: "flex", flexDirection: "column", gap: "6px", color: "#cbd5e1", fontSize: "0.78rem", fontWeight: 700 };
const searchFormStyle = { display: "flex", gap: "8px", flexWrap: "wrap" };
const inputStyle = { minWidth: "240px", border: "1px solid #334155", background: "#020617", color: "#e2e8f0", borderRadius: "6px", padding: "9px 10px" };
const selectStyle = { border: "1px solid #334155", background: "#020617", color: "#e2e8f0", borderRadius: "6px", padding: "9px 10px" };
const secondaryButtonStyle = { border: "1px solid #334155", background: "#111827", color: "#e5e7eb", borderRadius: "6px", padding: "9px 12px", cursor: "pointer" };
const linkButtonStyle = { ...secondaryButtonStyle, color: "#93c5fd", borderColor: "#2563eb" };
const workspaceGridStyle = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 340px), 1fr))", gap: "16px" };
const listPaneStyle = { border: "1px solid #30363d", borderRadius: "8px", background: "#0b1120", minHeight: "540px", overflow: "hidden" };
const detailPaneStyle = { border: "1px solid #30363d", borderRadius: "8px", background: "#0b1120", padding: "16px", minHeight: "540px" };
const paneHeaderStyle = { display: "flex", justifyContent: "space-between", gap: "12px", padding: "12px", borderBottom: "1px solid #1f2937", color: "#e5e7eb" };
const activityButtonStyle = { width: "100%", display: "flex", flexDirection: "column", gap: "5px", textAlign: "left", padding: "12px", border: "0", borderBottom: "1px solid #1f2937", background: "transparent", color: "#e5e7eb", cursor: "pointer" };
const activityButtonActiveStyle = { background: "#172554" };
const activityTitleStyle = { fontWeight: 800 };
const activityMetaStyle = { color: "#94a3b8", fontSize: "0.82rem" };
const detailHeaderStyle = { display: "flex", justifyContent: "space-between", gap: "14px", alignItems: "flex-start", flexWrap: "wrap" };
const detailTitleStyle = { margin: "4px 0 0", color: "#f8fafc", fontSize: "1.25rem", letterSpacing: "0" };
const badgeRowStyle = { display: "flex", gap: "8px", flexWrap: "wrap" };
const badgeStyle = { border: "1px solid #334155", borderRadius: "999px", padding: "4px 8px", fontSize: "0.72rem", fontWeight: 800 };
const badgeToneStyles = { neutral: { color: "#cbd5e1", background: "#111827" }, info: { color: "#bfdbfe", background: "#1e3a8a" }, warning: { color: "#fde68a", background: "#78350f" } };
const summaryGridStyle = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))", gap: "10px", margin: "16px 0" };
const metricLabelStyle = { color: "#94a3b8", fontSize: "0.74rem", textTransform: "uppercase", letterSpacing: "0" };
const metricValueStyle = { margin: "4px 0 0", color: "#f8fafc", fontWeight: 800 };
const evidenceSectionStyle = { marginTop: "14px" };
const sectionTitleStyle = { margin: "0 0 8px", color: "#e5e7eb", fontSize: "0.95rem" };
const evidenceListStyle = { margin: 0, paddingLeft: "18px", color: "#cbd5e1", lineHeight: 1.5 };
const evidenceItemStyle = { marginBottom: "4px" };
const pivotRowStyle = { display: "flex", gap: "8px", flexWrap: "wrap", marginTop: "14px" };
const linkedAlertsStyle = { marginTop: "18px", borderTop: "1px solid #1f2937", paddingTop: "12px" };
const alertRowStyle = { display: "flex", justifyContent: "space-between", gap: "10px", padding: "10px 0", borderBottom: "1px solid #1f2937", color: "#e5e7eb" };
const paginationStyle = { display: "flex", justifyContent: "flex-end", gap: "8px", padding: "12px" };
const emptyStateStyle = { padding: "18px", color: "#94a3b8" };
const mutedTextStyle = { margin: 0, color: "#94a3b8", fontSize: "0.84rem" };
const warningStyle = { border: "1px solid #854d0e", background: "#451a03", color: "#fde68a", padding: "10px 12px", borderRadius: "6px" };

export default ReconWorkspace;
