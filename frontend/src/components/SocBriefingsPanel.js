import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  getSocBriefing,
  getSocBriefingControl,
  listSocBriefings,
  runSocBriefingNow,
  updateSocBriefingMode,
  updateSocBriefingPause,
} from "../services/socBriefingService";
import { formatTimestamp } from "../utils/displayFormatting";

const PAGE_SIZE = 10;
const CONTENT_STATUSES = ["all", "ready", "pending", "blocked", "failed", "skipped", "not_generated"];
const DELIVERY_STATUSES = ["all", "sent", "retry_scheduled", "failed", "blocked", "skipped"];
const NO_DATA = "No Data";
const AGENT_NAME = "Anakin";

const SECTION_CONFIG = [
  { key: "critical_findings", label: "Critical Findings" },
  { key: "escalations", label: "Escalations" },
  { key: "dismissed_low_priority_findings", label: "Low Priority Findings" },
  { key: "evidence", label: "Evidence Reviewed" },
  { key: "recommendations", label: "Recommendations" },
];

function labelize(value) {
  return String(value || "unknown")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function statusLabel(status) {
  const normalized = String(status || "none").toLowerCase();
  if (["success", "ready", "sent"].includes(normalized)) return "Completed";
  if (normalized === "retry_scheduled") return "Retry Scheduled";
  if (normalized === "not_generated") return "No Data";
  if (normalized === "none") return "No Data";
  return labelize(normalized);
}

function statusTone(status) {
  const normalized = String(status || "none").toLowerCase();
  if (["success", "ready", "sent", "completed"].includes(normalized)) {
    return { fg: "#7dd3fc", border: "rgba(125, 211, 252, 0.45)", bg: "rgba(14, 165, 233, 0.12)" };
  }
  if (["running", "pending", "retry_scheduled", "partial", "not_generated"].includes(normalized)) {
    return { fg: "#fde68a", border: "rgba(253, 230, 138, 0.38)", bg: "rgba(253, 230, 138, 0.1)" };
  }
  if (["failed", "blocked", "degraded"].includes(normalized)) {
    return { fg: "#fca5a5", border: "rgba(248, 113, 113, 0.38)", bg: "rgba(248, 113, 113, 0.1)" };
  }
  if (normalized === "skipped") {
    return { fg: "#c4b5fd", border: "rgba(196, 181, 253, 0.34)", bg: "rgba(139, 92, 246, 0.1)" };
  }
  return { fg: "#c9d1d9", border: "rgba(201, 209, 217, 0.26)", bg: "rgba(201, 209, 217, 0.07)" };
}

function StatusBadge({ label, status }) {
  const tone = statusTone(status);
  return (
    <span
      style={{
        color: tone.fg,
        backgroundColor: tone.bg,
        borderColor: tone.border,
        borderStyle: "solid",
        borderWidth: 1,
        borderRadius: 999,
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        fontSize: "0.72rem",
        fontWeight: 800,
        lineHeight: 1,
        padding: "6px 8px",
        whiteSpace: "nowrap",
      }}
    >
      {label ? `${label}: ` : ""}
      {statusLabel(status)}
    </span>
  );
}

function formatMetricValue(value) {
  if (value === null || value === undefined || value === "") return NO_DATA;
  return value;
}

function formatRuntime(ms) {
  const value = Number(ms);
  if (!Number.isFinite(value) || value <= 0) return NO_DATA;
  if (value < 1000) return `${Math.round(value)} ms`;
  return `${(value / 1000).toFixed(1)} sec`;
}

function inferSeverity(briefing, detail) {
  const source = detail || briefing || {};
  const sections = source.sections || {};
  const criticalCount = Array.isArray(sections.critical_findings) ? sections.critical_findings.length : 0;
  const escalationCount = Array.isArray(sections.escalations) ? sections.escalations.length : 0;
  if (criticalCount > 0) return "Critical";
  if (escalationCount > 0 || source.status === "partial") return "High";
  if (source.content_status === "failed" || source.status === "failed") return "Degraded";
  return "Advisory";
}

function severityTone(severity) {
  const normalized = String(severity || "").toLowerCase();
  if (normalized === "critical") return { color: "#fca5a5", border: "rgba(248, 113, 113, 0.4)", bg: "rgba(248, 113, 113, 0.1)" };
  if (normalized === "high") return { color: "#fde68a", border: "rgba(253, 230, 138, 0.38)", bg: "rgba(253, 230, 138, 0.1)" };
  if (normalized === "degraded") return { color: "#c4b5fd", border: "rgba(196, 181, 253, 0.34)", bg: "rgba(139, 92, 246, 0.1)" };
  return { color: "#7dd3fc", border: "rgba(125, 211, 252, 0.34)", bg: "rgba(14, 165, 233, 0.08)" };
}

function MiniAiMark() {
  return (
    <div aria-hidden="true" style={aiMarkStyle}>
      <div style={aiMarkCoreStyle}>A</div>
      <span style={{ ...aiNodeStyle, top: 10, left: 18 }} />
      <span style={{ ...aiNodeStyle, top: 18, right: 12 }} />
      <span style={{ ...aiNodeStyle, bottom: 14, left: 32 }} />
    </div>
  );
}

function SummaryCard({ label, value, detail, status }) {
  const tone = statusTone(status || value);
  return (
    <div style={summaryCardStyle}>
      <span style={summaryLabelStyle}>{label}</span>
      <strong style={{ ...summaryValueStyle, color: value === NO_DATA ? "#8b949e" : "#f0f9ff" }}>
        {formatMetricValue(value)}
      </strong>
      <span style={{ ...summaryDetailStyle, color: detail ? tone.fg : "#8b949e" }}>{detail || "Awaiting data"}</span>
    </div>
  );
}

function modeLabel(mode) {
  return mode === "scheduled_autonomous" ? "Scheduled autonomous" : "Manual only";
}

function boolStatus(value) {
  return value ? "success" : "blocked";
}

function getActiveJobTotal(control, triggerType) {
  const jobs = control?.active_jobs?.[triggerType] || {};
  return Number(jobs.pending || 0) + Number(jobs.running || 0);
}

function ControlPanel({
  control,
  loading,
  actionLoading,
  message,
  onRunNow,
  onModeChange,
  onTogglePause,
}) {
  const gateway = control?.ai?.gateway || {};
  const localProvider = control?.ai?.local_provider || {};
  const catchUp = control?.catch_up || {};
  const activeManual = getActiveJobTotal(control, "manual");
  const activeScheduled = getActiveJobTotal(control, "scheduled");
  const modelStatus = localProvider.ready ? "success" : (localProvider.status || "blocked");
  const nextRun = control?.next_scheduled_run?.next_due_at;
  const lastRun = control?.last_successful_run?.generated_at || control?.last_successful_run?.created_at;

  return (
    <section style={controlPanelStyle} aria-label="SOC briefing controls">
      <div style={controlHeaderStyle}>
        <div>
          <p style={eyebrowStyle}>Manual-first controls</p>
          <h3 style={controlTitleStyle}>Anakin Briefing Control</h3>
        </div>
        <button
          type="button"
          onClick={onRunNow}
          disabled={actionLoading || loading}
          style={primaryActionStyle}
        >
          {actionLoading ? "Starting..." : "Run Anakin Briefing Now"}
        </button>
      </div>

      <div style={controlGridStyle}>
        <label style={controlFieldStyle}>
          Briefing Mode
          <select
            aria-label="Briefing mode"
            value={control?.mode || "manual_only"}
            onChange={(event) => onModeChange(event.target.value)}
            disabled={actionLoading || loading}
            style={selectStyle}
          >
            <option value="manual_only">Manual only</option>
            <option value="scheduled_autonomous">Scheduled autonomous</option>
          </select>
        </label>
        <label style={toggleFieldStyle}>
          <input
            aria-label="Pause schedules"
            type="checkbox"
            checked={Boolean(control?.schedules_paused)}
            onChange={(event) => onTogglePause(event.target.checked)}
            disabled={actionLoading || loading}
          />
          Pause schedules
        </label>
        <MetaItem label="Mode" value={modeLabel(control?.mode)} />
        <MetaItem label="Last Successful Run" value={lastRun ? formatTimestamp(lastRun) : null} />
        <MetaItem label="Next Scheduled Run" value={nextRun ? formatTimestamp(nextRun) : null} />
        <MetaItem
          label="Catch-up"
          value={catchUp.status ? `${statusLabel(catchUp.status)} / ${catchUp.max_windows || 0} windows` : null}
        />
        <MetaItem label="Manual Active" value={activeManual ? String(activeManual) : "0"} />
        <MetaItem label="Scheduled Active" value={activeScheduled ? String(activeScheduled) : "0"} />
      </div>

      <div style={controlBadgeRowStyle}>
        <StatusBadge label="Local Model" status={modelStatus} />
        <StatusBadge label="Local Only" status={boolStatus(control?.ai?.local_only)} />
        <StatusBadge label="No Paid Fallback" status={boolStatus(control?.ai?.no_paid_fallback)} />
        <span style={controlHintStyle}>{gateway.local_model || localProvider.model || "No local model configured"}</span>
      </div>
      {message ? <div role="status" style={controlMessageStyle}>{message}</div> : null}
    </section>
  );
}

function EmptyState() {
  return (
    <div style={emptyStateStyle}>
      <MiniAiMark />
      <div>
        <h3 style={emptyTitleStyle}>Morning SOC Briefings</h3>
        <p style={emptyTextStyle}>
          Anakin's analyst summaries appear here after scheduled investigations complete.
        </p>
        <p style={emptyFinePrintStyle}>
          Includes critical findings, dismissals, escalations, evidence reviewed, and recommendations.
        </p>
      </div>
    </div>
  );
}

function SectionList({ title, items }) {
  const safeItems = Array.isArray(items) ? items : [];
  return (
    <section style={detailSectionStyle}>
      <div style={detailSectionHeaderStyle}>
        <h3 style={detailSectionTitleStyle}>{title}</h3>
        <span style={detailCountStyle}>{safeItems.length}</span>
      </div>
      {safeItems.length === 0 ? (
        <p style={mutedTextStyle}>No entries recorded.</p>
      ) : (
        <ul style={sectionListStyle}>
          {safeItems.map((item, index) => (
            <li key={`${title}-${index}`} style={sectionItemStyle}>
              {typeof item === "object" ? JSON.stringify(item) : String(item)}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function BriefingRow({ briefing, selected, onSelect, detail }) {
  const deliveryStatus = briefing.delivery?.latest_status || "none";
  const generatedAt = briefing.generated_at || briefing.created_at;
  const severity = inferSeverity(briefing, selected ? detail : null);
  const severityStyle = severityTone(severity);
  const provider = briefing.run?.provider_status || (selected ? detail?.run?.provider_status : null);
  const runtime = selected ? detail?.run?.runtime_ms : briefing.run?.runtime_ms;

  return (
    <button
      type="button"
      onClick={() => onSelect(briefing.id)}
      style={{
        ...briefingCardStyle,
        borderColor: selected ? "rgba(125, 211, 252, 0.62)" : "rgba(125, 211, 252, 0.16)",
        background: selected
          ? "linear-gradient(135deg, rgba(14, 165, 233, 0.16), rgba(15, 23, 42, 0.92))"
          : "rgba(13, 17, 23, 0.76)",
        boxShadow: selected ? "0 16px 36px rgba(14, 165, 233, 0.12)" : "none",
      }}
    >
      <div style={briefingCardHeaderStyle}>
        <div style={{ minWidth: 0 }}>
          <div style={briefingTitleStyle}>Morning SOC Briefing #{briefing.id}</div>
          <div style={briefingSubTitleStyle}>
            {formatTimestamp(generatedAt)} · {briefing.schedule?.name || "Scheduled SOC briefing"}
          </div>
        </div>
        <span style={{ ...severityPillStyle, color: severityStyle.color, borderColor: severityStyle.border, backgroundColor: severityStyle.bg }}>
          {severity}
        </span>
      </div>
      <p style={briefingSummaryStyle}>{briefing.summary || "No summary recorded."}</p>
      <div style={briefingMetaGridStyle}>
        <MetaItem label="Schedule" value={briefing.schedule?.name} />
        <MetaItem label="Runtime" value={formatRuntime(runtime)} />
        <MetaItem label="Provider" value={provider} />
        <MetaItem label="Model" value={briefing.run?.model || detail?.run?.model} />
      </div>
      <div style={briefingStatusRowStyle}>
        <StatusBadge label="Status" status={briefing.content_status || briefing.status} />
        <StatusBadge label="Slack" status={deliveryStatus} />
      </div>
    </button>
  );
}

function MetaItem({ label, value }) {
  return (
    <span style={metaItemStyle}>
      <span style={metaLabelStyle}>{label}</span>
      <strong style={metaValueStyle}>{formatMetricValue(value)}</strong>
    </span>
  );
}

export default function SocBriefingsPanel() {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [search, setSearch] = useState("");
  const [contentStatus, setContentStatus] = useState("all");
  const [deliveryStatus, setDeliveryStatus] = useState("all");
  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [control, setControl] = useState(null);
  const [controlLoading, setControlLoading] = useState(false);
  const [controlActionLoading, setControlActionLoading] = useState(false);
  const [controlMessage, setControlMessage] = useState("");
  const [error, setError] = useState("");

  const filters = useMemo(
    () => ({
      limit: PAGE_SIZE,
      offset,
      search,
      content_status: contentStatus === "all" ? "" : contentStatus,
      delivery_status: deliveryStatus === "all" ? "" : deliveryStatus,
    }),
    [contentStatus, deliveryStatus, offset, search]
  );

  const loadList = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const payload = await listSocBriefings(filters);
      const nextItems = payload.items || [];
      setItems(nextItems);
      setTotal(Number(payload.total || 0));
      if (!selectedId && nextItems.length) {
        setSelectedId(nextItems[0].id);
      }
      if (selectedId && !nextItems.some((item) => item.id === selectedId)) {
        setSelectedId(nextItems[0]?.id || null);
      }
    } catch (err) {
      setError(err.message || "Unable to load SOC briefings.");
    } finally {
      setLoading(false);
    }
  }, [filters, selectedId]);

  const loadControl = useCallback(async () => {
    setControlLoading(true);
    try {
      const payload = await getSocBriefingControl();
      setControl(payload);
    } catch (err) {
      setError(err.message || "Unable to load SOC briefing controls.");
    } finally {
      setControlLoading(false);
    }
  }, []);

  useEffect(() => {
    loadList();
  }, [loadList]);

  useEffect(() => {
    loadControl();
  }, [loadControl]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    setDetailLoading(true);
    getSocBriefing(selectedId)
      .then((payload) => {
        if (!cancelled) setDetail(payload);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message || "Unable to load SOC briefing detail.");
      })
      .finally(() => {
        if (!cancelled) setDetailLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  const selectedBriefing = items.find((item) => item.id === selectedId);
  const latestBriefing = items[0];
  const latestGeneratedAt = latestBriefing?.generated_at || latestBriefing?.created_at;
  const latestSlackStatus = latestBriefing?.delivery?.latest_status || detail?.deliveries?.[0]?.status;
  const agentStatus = detail?.run?.status || latestBriefing?.run?.status || (total > 0 ? "completed" : null);
  const handleRunNow = useCallback(async () => {
    setControlActionLoading(true);
    setControlMessage("");
    setError("");
    try {
      const payload = await runSocBriefingNow();
      if (payload.created) {
        setControlMessage("Anakin briefing queued. The worker will persist it into history after processing.");
      } else {
        setControlMessage("A manual Anakin briefing is already pending or running.");
      }
      await Promise.all([loadControl(), loadList()]);
    } catch (err) {
      setControlMessage("");
      setError(err.message || "Unable to run Anakin briefing now.");
    } finally {
      setControlActionLoading(false);
    }
  }, [loadControl, loadList]);

  const handleModeChange = useCallback(async (mode) => {
    setControlActionLoading(true);
    setControlMessage("");
    setError("");
    try {
      const payload = await updateSocBriefingMode(mode);
      setControl(payload);
      setControlMessage(`Briefing mode set to ${modeLabel(mode)}.`);
    } catch (err) {
      setError(err.message || "Unable to update briefing mode.");
    } finally {
      setControlActionLoading(false);
    }
  }, []);

  const handleTogglePause = useCallback(async (paused) => {
    setControlActionLoading(true);
    setControlMessage("");
    setError("");
    try {
      const payload = await updateSocBriefingPause(paused, paused ? "Paused from SOC Briefings workspace" : "");
      setControl(payload);
      setControlMessage(paused ? "Schedules paused. Manual runs remain available." : "Schedules unpaused.");
    } catch (err) {
      setError(err.message || "Unable to update schedule pause state.");
    } finally {
      setControlActionLoading(false);
    }
  }, []);

  const canPrevious = offset > 0;
  const canNext = offset + PAGE_SIZE < total;
  const empty = !loading && items.length === 0;

  return (
    <div style={pageStyle}>
      <section style={heroStyle}>
        <div style={heroContentStyle}>
          <MiniAiMark />
          <div>
            <p style={eyebrowStyle}>Read-only autonomous SOC agent</p>
            <h2 style={heroTitleStyle}>Morning SOC Briefings</h2>
            <p style={heroTextStyle}>
              Anakin summarizes scheduled investigations, critical findings, dismissals, escalations, evidence reviewed, and analyst recommendations.
            </p>
          </div>
        </div>
        <div style={heroStatusStyle}>
          <StatusBadge label={AGENT_NAME} status={agentStatus || "none"} />
          <StatusBadge label="Slack" status={latestSlackStatus || "none"} />
        </div>
      </section>

      <ControlPanel
        control={control}
        loading={controlLoading}
        actionLoading={controlActionLoading}
        message={controlMessage}
        onRunNow={handleRunNow}
        onModeChange={handleModeChange}
        onTogglePause={handleTogglePause}
      />

      <section style={summaryGridStyle} aria-label="SOC briefing summary">
        <SummaryCard label="Total Briefings" value={total || NO_DATA} detail={total ? `${items.length} visible` : ""} />
        <SummaryCard label="Latest Briefing" value={latestGeneratedAt ? formatTimestamp(latestGeneratedAt) : NO_DATA} detail={latestBriefing ? `#${latestBriefing.id}` : ""} status={latestBriefing?.content_status} />
        <SummaryCard label="Next Scheduled Run" value={control?.next_scheduled_run?.next_due_at ? formatTimestamp(control.next_scheduled_run.next_due_at) : NO_DATA} detail={control?.schedules_paused ? "Schedules paused" : modeLabel(control?.mode)} />
        <SummaryCard label={`${AGENT_NAME} Status`} value={agentStatus ? statusLabel(agentStatus) : NO_DATA} detail={control?.ai?.local_provider?.status || detail?.run?.provider_status || ""} status={agentStatus || control?.ai?.local_provider?.status} />
        <SummaryCard label="Slack Delivery Status" value={latestSlackStatus ? statusLabel(latestSlackStatus) : NO_DATA} detail={latestBriefing?.delivery?.latest_attempted_at ? formatTimestamp(latestBriefing.delivery.latest_attempted_at) : ""} status={latestSlackStatus} />
      </section>

      {empty ? (
        <section style={singleEmptyPanelStyle}>
          <EmptyState />
        </section>
      ) : (
      <div style={workspaceStyle}>
        <section style={historyPaneStyle}>
          <div style={filterPanelStyle}>
            <div>
              <h3 style={paneTitleStyle}>Briefing History</h3>
              <p style={paneSubtitleStyle}>Browse saved advisory briefings without triggering new investigations.</p>
            </div>
            <div style={filterGridStyle}>
              <input
                aria-label="Search briefings"
                value={search}
                onChange={(event) => {
                  setSearch(event.target.value);
                  setOffset(0);
                }}
                placeholder="Search summaries, schedules, errors"
                style={inputStyle}
              />
              <label style={filterLabelStyle}>
                Content
                <select
                  aria-label="Content status"
                  value={contentStatus}
                  onChange={(event) => {
                    setContentStatus(event.target.value);
                    setOffset(0);
                  }}
                  style={selectStyle}
                >
                  {CONTENT_STATUSES.map((status) => (
                    <option key={status} value={status}>{labelize(status)}</option>
                  ))}
                </select>
              </label>
              <label style={filterLabelStyle}>
                Slack
                <select
                  aria-label="Slack delivery status"
                  value={deliveryStatus}
                  onChange={(event) => {
                    setDeliveryStatus(event.target.value);
                    setOffset(0);
                  }}
                  style={selectStyle}
                >
                  {DELIVERY_STATUSES.map((status) => (
                    <option key={status} value={status}>{labelize(status)}</option>
                  ))}
                </select>
              </label>
            </div>
          </div>

          {error ? <div role="alert" style={errorPanelStyle}>{error}</div> : null}

          <div style={historyListStyle}>
            {loading ? <div style={loadingStyle}>Loading briefings...</div> : null}
            {items.map((item) => (
              <BriefingRow
                key={item.id}
                briefing={item}
                selected={item.id === selectedId}
                detail={item.id === selectedId ? detail : null}
                onSelect={setSelectedId}
              />
            ))}
          </div>
          <div style={paginationStyle}>
            <span>{total ? `${offset + 1}-${Math.min(offset + PAGE_SIZE, total)} of ${total}` : "0 of 0"}</span>
            <div style={{ display: "flex", gap: 8 }}>
              <button type="button" disabled={!canPrevious} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))} style={pagerButtonStyle}>Previous</button>
              <button type="button" disabled={!canNext} onClick={() => setOffset(offset + PAGE_SIZE)} style={pagerButtonStyle}>Next</button>
            </div>
          </div>
        </section>

        <section style={detailPaneStyle}>
          {detailLoading ? <div style={loadingStyle}>Loading briefing detail...</div> : null}
          {!detailLoading && !detail ? (
            <div style={selectBriefingStateStyle}>
              <MiniAiMark />
              <h3 style={emptyTitleStyle}>Select a briefing</h3>
              <p style={emptyTextStyle}>Open a saved briefing to read Anakin's executive summary, findings, evidence, and recommendations.</p>
            </div>
          ) : null}
          {!detailLoading && detail ? (
            <div style={detailContentStyle}>
              <header style={detailHeaderStyle}>
                <div>
                  <p style={eyebrowStyle}>Executive Summary</p>
                  <h2 style={detailTitleStyle}>Briefing #{detail.id}</h2>
                  <p style={detailSubTitleStyle}>
                    {detail.schedule?.name || "Scheduled SOC briefing"} · {formatTimestamp(detail.generated_at || detail.created_at)}
                  </p>
                </div>
                <div style={detailBadgeGroupStyle}>
                  <StatusBadge label="Content" status={detail.content_status} />
                  <StatusBadge label="Run" status={detail.run?.status} />
                  <StatusBadge label="Slack" status={detail.deliveries?.[0]?.status || "none"} />
                </div>
              </header>

              <section style={executiveSummaryStyle}>
                <p style={summaryLeadStyle}>{detail.summary || "No summary recorded."}</p>
              </section>

              {(detail.error_code || detail.error_message || detail.run?.error_code) ? (
                <div style={degradedPanelStyle}>
                  <strong>{detail.error_code || detail.run?.error_code || "degraded"}</strong>
                  <span>{detail.error_message || detail.run?.error_message || "Briefing completed in a degraded state."}</span>
                </div>
              ) : null}

              {SECTION_CONFIG.map((section) => (
                <SectionList key={section.key} title={section.label} items={detail.sections?.[section.key]} />
              ))}

              <section style={detailSectionStyle}>
                <div style={detailSectionHeaderStyle}>
                  <h3 style={detailSectionTitleStyle}>Investigation Metadata</h3>
                </div>
                <div style={metadataGridStyle}>
                  <MetaItem label="Severity" value={inferSeverity(selectedBriefing, detail)} />
                  <MetaItem label="Runtime" value={formatRuntime(detail.run?.runtime_ms)} />
                  <MetaItem label="Provider" value={detail.run?.provider_status} />
                  <MetaItem label="Model" value={detail.run?.model} />
                  <MetaItem label="Agent" value={AGENT_NAME} />
                  <MetaItem label="Window" value={detail.window?.window_end ? formatTimestamp(detail.window.window_end) : null} />
                  <MetaItem label="Service Actor" value={detail.run?.service_actor} />
                </div>
              </section>

              <section style={detailSectionStyle}>
                <div style={detailSectionHeaderStyle}>
                  <h3 style={detailSectionTitleStyle}>Slack Delivery Attempts</h3>
                  <span style={detailCountStyle}>{(detail.deliveries || []).length}</span>
                </div>
                {(detail.deliveries || []).length === 0 ? (
                  <p style={mutedTextStyle}>No Slack delivery attempt recorded.</p>
                ) : (
                  <div style={deliveryListStyle}>
                    {detail.deliveries.map((attempt) => (
                      <div key={attempt.id} style={deliveryRowStyle}>
                        <StatusBadge status={attempt.status} />
                        <span>{formatTimestamp(attempt.last_attempted_at || attempt.created_at)}</span>
                        <span>{attempt.failure_code || "no failure"}</span>
                      </div>
                    ))}
                  </div>
                )}
              </section>
            </div>
          ) : null}
        </section>
      </div>
      )}
    </div>
  );
}

const pageStyle = {
  display: "grid",
  gap: 16,
};

const heroStyle = {
  alignItems: "center",
  background: "linear-gradient(135deg, rgba(8, 47, 73, 0.72), rgba(13, 17, 23, 0.9))",
  border: "1px solid rgba(125, 211, 252, 0.22)",
  borderRadius: 8,
  display: "flex",
  gap: 18,
  justifyContent: "space-between",
  padding: 18,
};

const heroContentStyle = {
  alignItems: "center",
  display: "flex",
  gap: 14,
  minWidth: 0,
};

const heroStatusStyle = {
  display: "flex",
  flexWrap: "wrap",
  gap: 8,
  justifyContent: "flex-end",
};

const controlPanelStyle = {
  background: "rgba(13, 17, 23, 0.84)",
  border: "1px solid rgba(125, 211, 252, 0.2)",
  borderRadius: 8,
  display: "grid",
  gap: 14,
  padding: 16,
};

const controlHeaderStyle = {
  alignItems: "center",
  display: "flex",
  gap: 12,
  justifyContent: "space-between",
};

const controlTitleStyle = {
  color: "#f0f9ff",
  fontSize: "1rem",
  lineHeight: 1.2,
  margin: 0,
};

const primaryActionStyle = {
  background: "#38bdf8",
  border: "1px solid rgba(186, 230, 253, 0.6)",
  borderRadius: 8,
  color: "#06131f",
  cursor: "pointer",
  fontSize: "0.84rem",
  fontWeight: 900,
  minHeight: 38,
  padding: "9px 12px",
  whiteSpace: "nowrap",
};

const controlGridStyle = {
  display: "grid",
  gap: 10,
  gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))",
};

const controlFieldStyle = {
  color: "#8b949e",
  display: "grid",
  fontSize: "0.72rem",
  fontWeight: 800,
  gap: 5,
  textTransform: "uppercase",
};

const toggleFieldStyle = {
  alignItems: "center",
  background: "rgba(2, 6, 23, 0.38)",
  border: "1px solid rgba(148, 163, 184, 0.16)",
  borderRadius: 8,
  color: "#e6edf3",
  display: "flex",
  fontSize: "0.84rem",
  fontWeight: 800,
  gap: 8,
  minHeight: 39,
  padding: "8px 10px",
};

const controlBadgeRowStyle = {
  alignItems: "center",
  display: "flex",
  flexWrap: "wrap",
  gap: 8,
};

const controlHintStyle = {
  color: "#8b949e",
  fontSize: "0.78rem",
  fontWeight: 700,
};

const controlMessageStyle = {
  background: "rgba(14, 165, 233, 0.1)",
  border: "1px solid rgba(125, 211, 252, 0.22)",
  borderRadius: 8,
  color: "#bae6fd",
  fontSize: "0.82rem",
  fontWeight: 700,
  padding: "9px 10px",
};

const aiMarkStyle = {
  alignItems: "center",
  background: "radial-gradient(circle at 35% 30%, rgba(186, 230, 253, 0.28), rgba(14, 165, 233, 0.08) 46%, rgba(15, 23, 42, 0.9) 72%)",
  border: "1px solid rgba(125, 211, 252, 0.42)",
  borderRadius: 8,
  boxShadow: "0 14px 28px rgba(14, 165, 233, 0.14)",
  display: "flex",
  flex: "0 0 64px",
  height: 64,
  justifyContent: "center",
  position: "relative",
  width: 64,
};

const aiMarkCoreStyle = {
  alignItems: "center",
  border: "1px solid rgba(125, 211, 252, 0.55)",
  borderRadius: 999,
  color: "#e0f2fe",
  display: "flex",
  fontSize: "0.82rem",
  fontWeight: 900,
  height: 34,
  justifyContent: "center",
  letterSpacing: 0,
  width: 34,
};

const aiNodeStyle = {
  backgroundColor: "#7dd3fc",
  borderRadius: 999,
  boxShadow: "0 0 16px rgba(125, 211, 252, 0.6)",
  height: 5,
  position: "absolute",
  width: 5,
};

const eyebrowStyle = {
  color: "#7dd3fc",
  fontSize: "0.72rem",
  fontWeight: 900,
  letterSpacing: 0,
  margin: "0 0 4px",
  textTransform: "uppercase",
};

const heroTitleStyle = {
  color: "#f0f9ff",
  fontSize: "1.22rem",
  lineHeight: 1.15,
  margin: 0,
};

const heroTextStyle = {
  color: "#adbac7",
  fontSize: "0.9rem",
  lineHeight: 1.45,
  margin: "6px 0 0",
  maxWidth: 780,
};

const summaryGridStyle = {
  display: "grid",
  gap: 10,
  gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
};

const summaryCardStyle = {
  background: "rgba(13, 17, 23, 0.78)",
  border: "1px solid rgba(125, 211, 252, 0.16)",
  borderRadius: 8,
  display: "grid",
  gap: 5,
  minHeight: 78,
  padding: "12px 13px",
};

const summaryLabelStyle = {
  color: "#8b949e",
  fontSize: "0.72rem",
  fontWeight: 800,
  textTransform: "uppercase",
};

const summaryValueStyle = {
  fontSize: "0.98rem",
  lineHeight: 1.15,
};

const summaryDetailStyle = {
  fontSize: "0.76rem",
};

const workspaceStyle = {
  alignItems: "start",
  display: "grid",
  gap: 16,
  gridTemplateColumns: "minmax(320px, 0.82fr) minmax(420px, 1.18fr)",
};

const historyPaneStyle = {
  display: "grid",
  gap: 12,
  minWidth: 0,
};

const singleEmptyPanelStyle = {
  background: "rgba(13, 17, 23, 0.7)",
  border: "1px solid rgba(125, 211, 252, 0.16)",
  borderRadius: 8,
  minHeight: 360,
  padding: 16,
};

const detailPaneStyle = {
  background: "rgba(13, 17, 23, 0.7)",
  border: "1px solid rgba(125, 211, 252, 0.16)",
  borderRadius: 8,
  minHeight: 520,
  minWidth: 0,
  padding: 16,
};

const filterPanelStyle = {
  background: "rgba(13, 17, 23, 0.72)",
  border: "1px solid rgba(125, 211, 252, 0.16)",
  borderRadius: 8,
  display: "grid",
  gap: 12,
  padding: 14,
};

const paneTitleStyle = {
  color: "#f0f9ff",
  fontSize: "1rem",
  margin: 0,
};

const paneSubtitleStyle = {
  color: "#8b949e",
  fontSize: "0.8rem",
  lineHeight: 1.4,
  margin: "4px 0 0",
};

const filterGridStyle = {
  display: "grid",
  gap: 10,
  gridTemplateColumns: "minmax(180px, 1.4fr) repeat(2, minmax(120px, 0.8fr))",
};

const inputStyle = {
  background: "#0d1117",
  border: "1px solid rgba(125, 211, 252, 0.24)",
  borderRadius: 6,
  color: "#f0f9ff",
  minWidth: 0,
  padding: "10px 11px",
};

const selectStyle = {
  background: "#0d1117",
  border: "1px solid rgba(125, 211, 252, 0.24)",
  borderRadius: 6,
  color: "#f0f9ff",
  padding: "9px 10px",
};

const filterLabelStyle = {
  color: "#8b949e",
  display: "grid",
  fontSize: "0.72rem",
  fontWeight: 800,
  gap: 5,
  minWidth: 0,
};

const historyListStyle = {
  display: "grid",
  gap: 10,
};

const briefingCardStyle = {
  borderStyle: "solid",
  borderWidth: 1,
  borderRadius: 8,
  color: "#c9d1d9",
  cursor: "pointer",
  display: "grid",
  gap: 10,
  padding: 13,
  textAlign: "left",
  width: "100%",
};

const briefingCardHeaderStyle = {
  alignItems: "start",
  display: "flex",
  gap: 12,
  justifyContent: "space-between",
};

const briefingTitleStyle = {
  color: "#f0f9ff",
  fontSize: "0.96rem",
  fontWeight: 900,
  lineHeight: 1.25,
};

const briefingSubTitleStyle = {
  color: "#8b949e",
  fontSize: "0.76rem",
  lineHeight: 1.35,
  marginTop: 4,
};

const severityPillStyle = {
  borderStyle: "solid",
  borderWidth: 1,
  borderRadius: 999,
  flex: "0 0 auto",
  fontSize: "0.72rem",
  fontWeight: 900,
  padding: "5px 8px",
};

const briefingSummaryStyle = {
  color: "#adbac7",
  fontSize: "0.84rem",
  lineHeight: 1.45,
  margin: 0,
};

const briefingMetaGridStyle = {
  display: "grid",
  gap: 8,
  gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
};

const metaItemStyle = {
  background: "rgba(22, 27, 34, 0.58)",
  border: "1px solid rgba(139, 148, 158, 0.13)",
  borderRadius: 7,
  display: "grid",
  gap: 3,
  minWidth: 0,
  padding: "8px 9px",
};

const metaLabelStyle = {
  color: "#8b949e",
  fontSize: "0.68rem",
  fontWeight: 800,
  textTransform: "uppercase",
};

const metaValueStyle = {
  color: "#dbeafe",
  fontSize: "0.8rem",
  lineHeight: 1.25,
  overflowWrap: "anywhere",
};

const briefingStatusRowStyle = {
  display: "flex",
  flexWrap: "wrap",
  gap: 7,
};

const paginationStyle = {
  alignItems: "center",
  color: "#8b949e",
  display: "flex",
  fontSize: "0.82rem",
  justifyContent: "space-between",
};

const pagerButtonStyle = {
  background: "rgba(13, 17, 23, 0.82)",
  border: "1px solid rgba(125, 211, 252, 0.22)",
  borderRadius: 6,
  color: "#dbeafe",
  cursor: "pointer",
  padding: "7px 10px",
};

const errorPanelStyle = {
  border: "1px solid rgba(248, 113, 113, 0.3)",
  borderRadius: 8,
  color: "#fca5a5",
  padding: 11,
};

const loadingStyle = {
  color: "#8b949e",
  padding: 12,
};

const emptyStateStyle = {
  alignItems: "center",
  background: "linear-gradient(135deg, rgba(8, 47, 73, 0.34), rgba(13, 17, 23, 0.78))",
  border: "1px solid rgba(125, 211, 252, 0.18)",
  borderRadius: 8,
  display: "flex",
  gap: 14,
  padding: 18,
};

const selectBriefingStateStyle = {
  alignItems: "center",
  color: "#c9d1d9",
  display: "grid",
  gap: 10,
  justifyItems: "center",
  minHeight: 280,
  padding: 20,
  textAlign: "center",
};

const emptyTitleStyle = {
  color: "#f0f9ff",
  fontSize: "1rem",
  margin: 0,
};

const emptyTextStyle = {
  color: "#c9d1d9",
  fontSize: "0.88rem",
  lineHeight: 1.45,
  margin: "6px 0 0",
};

const emptyFinePrintStyle = {
  color: "#8b949e",
  fontSize: "0.78rem",
  lineHeight: 1.45,
  margin: "6px 0 0",
};

const detailContentStyle = {
  display: "grid",
  gap: 15,
};

const detailHeaderStyle = {
  alignItems: "start",
  borderBottom: "1px solid rgba(125, 211, 252, 0.16)",
  display: "flex",
  gap: 14,
  justifyContent: "space-between",
  paddingBottom: 14,
};

const detailTitleStyle = {
  color: "#f0f9ff",
  fontSize: "1.1rem",
  lineHeight: 1.2,
  margin: 0,
};

const detailSubTitleStyle = {
  color: "#8b949e",
  fontSize: "0.82rem",
  lineHeight: 1.4,
  margin: "5px 0 0",
};

const detailBadgeGroupStyle = {
  display: "flex",
  flexWrap: "wrap",
  gap: 7,
  justifyContent: "flex-end",
};

const executiveSummaryStyle = {
  background: "rgba(14, 165, 233, 0.08)",
  border: "1px solid rgba(125, 211, 252, 0.18)",
  borderRadius: 8,
  padding: 14,
};

const summaryLeadStyle = {
  color: "#dbeafe",
  fontSize: "0.94rem",
  lineHeight: 1.55,
  margin: 0,
};

const degradedPanelStyle = {
  background: "rgba(248, 113, 113, 0.08)",
  border: "1px solid rgba(248, 113, 113, 0.28)",
  borderRadius: 8,
  color: "#fca5a5",
  display: "grid",
  gap: 5,
  padding: 12,
};

const detailSectionStyle = {
  borderTop: "1px solid rgba(125, 211, 252, 0.14)",
  display: "grid",
  gap: 10,
  paddingTop: 14,
};

const detailSectionHeaderStyle = {
  alignItems: "center",
  display: "flex",
  gap: 10,
  justifyContent: "space-between",
};

const detailSectionTitleStyle = {
  color: "#f0f9ff",
  fontSize: "0.96rem",
  margin: 0,
};

const detailCountStyle = {
  background: "rgba(125, 211, 252, 0.1)",
  border: "1px solid rgba(125, 211, 252, 0.24)",
  borderRadius: 999,
  color: "#7dd3fc",
  fontSize: "0.7rem",
  fontWeight: 900,
  padding: "3px 8px",
};

const sectionListStyle = {
  color: "#c9d1d9",
  display: "grid",
  gap: 8,
  margin: 0,
  paddingLeft: 18,
};

const sectionItemStyle = {
  lineHeight: 1.5,
  paddingLeft: 2,
};

const mutedTextStyle = {
  color: "#8b949e",
  fontSize: "0.84rem",
  margin: 0,
};

const metadataGridStyle = {
  display: "grid",
  gap: 9,
  gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
};

const deliveryListStyle = {
  display: "grid",
  gap: 8,
};

const deliveryRowStyle = {
  alignItems: "center",
  border: "1px solid rgba(125, 211, 252, 0.13)",
  borderRadius: 8,
  color: "#c9d1d9",
  display: "grid",
  gap: 10,
  gridTemplateColumns: "minmax(110px, 0.8fr) minmax(130px, 1fr) minmax(90px, 0.8fr)",
  padding: 10,
};
