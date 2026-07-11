import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  dismissDeadLetter,
  executeDeadLetterRetry,
  getDeadLetter,
  getDeadLetterMetrics,
  getDeadLetters,
  requestDeadLetterRetry,
} from "../services/deadLetterService";
import { formatTimestamp } from "../utils/displayFormatting";
import {
  MasterDetailLayout,
  MasterDetailMaster,
  MasterDetailPane,
  useMasterDetailFocus,
} from "./MasterDetailLayout";

const DEAD_LETTER_STATUSES = ["open", "retrying", "retried", "dismissed"];
const STATUS_FILTERS = ["all", ...DEAD_LETTER_STATUSES];
const SOURCE_TYPE_FILTERS = [
  "all",
  "playbook_execution",
  "notification_delivery",
  "response_action",
  "approval",
];

const OPERATIONAL_NOTICE =
  "Real workflow review: dead letters are durable failure records for operator triage. Retry request records intent only; it does not execute playbooks, run steps, or enable destructive remediation.";
const RETRY_EXECUTE_PHRASE = "RETRY";

function toCount(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}

function formatLabel(value) {
  return String(value || "unknown")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatDisplayValue(value, emptyValue = "—") {
  if (value === true) return "Yes";
  if (value === false) return "No";
  if (value === null || value === undefined || value === "") return emptyValue;
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function truncateText(value, maxLength = 48) {
  const text = String(value || "");
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength)}...`;
}

function formatRetryExecuteSuccess(newExecutionId) {
  const prefix =
    newExecutionId === undefined || newExecutionId === null
      ? "New pending execution created."
      : `New pending execution #${newExecutionId} created.`;
  return `${prefix} No steps have run. Start it with scripts/run_playbook_executor_once.py.`;
}

export function buildListFilters({ statusFilter, sourceTypeFilter, failureClassFilter }) {
  const filters = {};
  if (statusFilter !== "all") {
    filters.status = statusFilter;
  }
  if (sourceTypeFilter !== "all") {
    filters.source_type = sourceTypeFilter;
  }
  if (failureClassFilter !== "all") {
    filters.failure_class = failureClassFilter;
  }
  return filters;
}

function getStatusMetricCount(metrics, status) {
  if (!metrics || typeof metrics !== "object") {
    return 0;
  }
  if (metrics[status] !== undefined && metrics[status] !== null) {
    return toCount(metrics[status]);
  }
  return toCount(metrics.by_status?.[status]);
}

function getPayloadEntries(payload) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return [];
  }
  return Object.entries(payload).sort(([a], [b]) => a.localeCompare(b));
}

function hasLinkedContext(item) {
  if (!item || typeof item !== "object") {
    return false;
  }
  return (
    item.execution_id != null ||
    item.incident_id != null ||
    item.alert_id != null ||
    item.playbook_id != null ||
    item.action_name != null ||
    item.step_index != null
  );
}

function getStatusBadgeStyle(status) {
  if (status === "open") {
    return {
      color: "#f5d487",
      borderColor: "rgba(245, 212, 135, 0.38)",
      backgroundColor: "rgba(245, 212, 135, 0.1)",
    };
  }
  if (status === "retrying") {
    return {
      color: "#93c5fd",
      borderColor: "rgba(88, 166, 255, 0.38)",
      backgroundColor: "rgba(31, 111, 235, 0.12)",
    };
  }
  if (status === "retried") {
    return {
      color: "#7ee787",
      borderColor: "rgba(126, 231, 135, 0.35)",
      backgroundColor: "rgba(126, 231, 135, 0.1)",
    };
  }
  if (status === "dismissed") {
    return {
      color: "#c9d1d9",
      borderColor: "rgba(201, 209, 217, 0.35)",
      backgroundColor: "rgba(201, 209, 217, 0.08)",
    };
  }
  return {
    color: "#c9d1d9",
    borderColor: "rgba(201, 209, 217, 0.35)",
    backgroundColor: "rgba(201, 209, 217, 0.08)",
  };
}

function DeadLettersPanel({
  cardStyle,
  cardHeaderStyle,
  cardTitleStyle,
  cardSubtitleStyle,
  filterLabelStyle,
  selectStyle,
  userRole,
  displaySettings,
}) {
  const [metrics, setMetrics] = useState(null);
  const [items, setItems] = useState([]);
  const [statusFilter, setStatusFilter] = useState("all");
  const [sourceTypeFilter, setSourceTypeFilter] = useState("all");
  const [failureClassFilter, setFailureClassFilter] = useState("all");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [selectedId, setSelectedId] = useState(null);
  const [selectedItem, setSelectedItem] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");
  const [actionPending, setActionPending] = useState("");
  const [actionError, setActionError] = useState("");
  const [actionSuccess, setActionSuccess] = useState("");
  const [dismissComment, setDismissComment] = useState("");
  const [dismissConfirmOpen, setDismissConfirmOpen] = useState(false);
  const [retryExecuteConfirmed, setRetryExecuteConfirmed] = useState(false);
  const [retryExecutePhrase, setRetryExecutePhrase] = useState("");
  const { detailRef, rememberTrigger, restoreTriggerFocus } = useMasterDetailFocus(selectedId);

  const canMutateDeadLetters = userRole === "analyst" || userRole === "super_admin";
  const canExecuteDeadLetterRetry = userRole === "super_admin";

  const failureClassOptions = useMemo(() => {
    const keys = Object.keys(metrics?.by_failure_class || {}).sort((a, b) => a.localeCompare(b));
    return ["all", ...keys];
  }, [metrics?.by_failure_class]);

  const loadMetrics = useCallback(async () => {
    const data = await getDeadLetterMetrics();
    setMetrics(data && typeof data === "object" ? data : null);
  }, []);

  const loadList = useCallback(async () => {
    const filters = buildListFilters({
      statusFilter,
      sourceTypeFilter,
      failureClassFilter,
    });
    const data = await getDeadLetters(filters);
    setItems(Array.isArray(data?.items) ? data.items : []);
  }, [failureClassFilter, sourceTypeFilter, statusFilter]);

  const loadPanel = useCallback(
    async ({ quiet = false } = {}) => {
      try {
        if (quiet) {
          setRefreshing(true);
        } else {
          setLoading(true);
        }
        setError("");
        await Promise.all([loadMetrics(), loadList()]);
      } catch (err) {
        setError(err.message || "Unable to load dead letters.");
        if (!quiet) {
          setMetrics(null);
          setItems([]);
        }
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [loadList, loadMetrics]
  );

  const handleSelectRow = useCallback(async (deadLetterId, trigger) => {
    rememberTrigger(trigger);
    setSelectedId(deadLetterId);
    setDetailError("");
    setActionError("");
    setActionSuccess("");
    setDismissConfirmOpen(false);
    setDismissComment("");
    setRetryExecuteConfirmed(false);
    setRetryExecutePhrase("");
    setDetailLoading(true);
    setSelectedItem(null);
    try {
      const detail = await getDeadLetter(deadLetterId);
      setSelectedItem(detail && typeof detail === "object" ? detail : null);
    } catch (err) {
      setSelectedItem(null);
      setDetailError(err.message || "Unable to load dead letter detail.");
    } finally {
      setDetailLoading(false);
    }
  }, [rememberTrigger]);

  const handleCloseDetail = useCallback(() => {
    restoreTriggerFocus();
    setSelectedId(null);
    setSelectedItem(null);
    setDetailError("");
    setDetailLoading(false);
    setActionError("");
    setActionSuccess("");
    setDismissConfirmOpen(false);
    setDismissComment("");
    setRetryExecuteConfirmed(false);
    setRetryExecutePhrase("");
  }, [restoreTriggerFocus]);

  const handleDismissStart = useCallback(() => {
    setActionError("");
    setActionSuccess("");
    setDismissConfirmOpen(true);
  }, []);

  const handleDismissCancel = useCallback(() => {
    if (actionPending) return;
    setDismissConfirmOpen(false);
    setDismissComment("");
    setActionError("");
  }, [actionPending]);

  const handleDismissConfirm = useCallback(async () => {
    if (!selectedId || actionPending) return;
    setActionPending("dismiss");
    setActionError("");
    setActionSuccess("");
    try {
      const updated = await dismissDeadLetter(selectedId, { comment: dismissComment });
      const nextItem = updated && typeof updated === "object" ? updated : selectedItem;
      setSelectedItem(nextItem);
      setItems((currentItems) =>
        currentItems.map((item) => (item.id === selectedId ? { ...item, ...nextItem } : item))
      );
      setDismissConfirmOpen(false);
      setDismissComment("");
      setRetryExecuteConfirmed(false);
      setRetryExecutePhrase("");
      setActionSuccess("Dead letter dismissed.");
      await loadPanel({ quiet: true });
    } catch (err) {
      setActionError(err.message || "Unable to dismiss dead letter.");
    } finally {
      setActionPending("");
    }
  }, [actionPending, dismissComment, loadPanel, selectedId, selectedItem]);

  const handleRetryRequest = useCallback(async () => {
    if (!selectedId || actionPending) return;
    setActionPending("retry-request");
    setActionError("");
    setActionSuccess("");
    try {
      const updated = await requestDeadLetterRetry(selectedId);
      const nextItem = updated && typeof updated === "object" ? updated : selectedItem;
      setSelectedItem(nextItem);
      setItems((currentItems) =>
        currentItems.map((item) => (item.id === selectedId ? { ...item, ...nextItem } : item))
      );
      setDismissConfirmOpen(false);
      setRetryExecuteConfirmed(false);
      setRetryExecutePhrase("");
      setActionSuccess("Retry request recorded. No playbook steps were executed.");
      await loadPanel({ quiet: true });
    } catch (err) {
      setActionError(err.message || "Unable to request dead letter retry.");
    } finally {
      setActionPending("");
    }
  }, [actionPending, loadPanel, selectedId, selectedItem]);

  const handleRetryExecute = useCallback(async () => {
    if (!selectedId || actionPending) return;
    setActionPending("retry-execute");
    setActionError("");
    setActionSuccess("");
    try {
      const result = await executeDeadLetterRetry(selectedId);
      const updated = result?.dead_letter && typeof result.dead_letter === "object"
        ? result.dead_letter
        : { ...(selectedItem || {}), status: "retried" };
      setSelectedItem(updated);
      setItems((currentItems) =>
        currentItems.map((item) => (item.id === selectedId ? { ...item, ...updated } : item))
      );
      setRetryExecuteConfirmed(false);
      setRetryExecutePhrase("");
      setDismissConfirmOpen(false);
      setActionSuccess(formatRetryExecuteSuccess(result?.new_execution_id));
      await loadPanel({ quiet: true });
      try {
        const refreshedDetail = await getDeadLetter(selectedId);
        if (refreshedDetail && typeof refreshedDetail === "object") {
          setSelectedItem(refreshedDetail);
        }
      } catch (_err) {
        // Keep the successful local transition visible if the detail refresh is unavailable.
      }
    } catch (err) {
      setActionError(err.message || "Unable to execute dead letter retry.");
    } finally {
      setActionPending("");
    }
  }, [actionPending, loadPanel, selectedId, selectedItem]);

  useEffect(() => {
    loadPanel();
  }, [loadPanel]);

  useEffect(() => {
    if (!failureClassOptions.includes(failureClassFilter)) {
      setFailureClassFilter("all");
    }
  }, [failureClassFilter, failureClassOptions]);

  const filterSummary = useMemo(() => {
    const parts = [];
    if (statusFilter !== "all") parts.push(`status=${statusFilter}`);
    if (sourceTypeFilter !== "all") parts.push(`source_type=${sourceTypeFilter}`);
    if (failureClassFilter !== "all") parts.push(`failure_class=${failureClassFilter}`);
    return parts.length ? parts.join(", ") : "no filters applied";
  }, [failureClassFilter, sourceTypeFilter, statusFilter]);

  return (
    <section style={cardStyle}>
      <PanelHeader
        cardHeaderStyle={cardHeaderStyle}
        cardTitleStyle={cardTitleStyle}
        cardSubtitleStyle={cardSubtitleStyle}
        filterLabelStyle={filterLabelStyle}
        selectStyle={selectStyle}
        statusFilter={statusFilter}
        sourceTypeFilter={sourceTypeFilter}
        failureClassFilter={failureClassFilter}
        failureClassOptions={failureClassOptions}
        onStatusFilterChange={setStatusFilter}
        onSourceTypeFilterChange={setSourceTypeFilter}
        onFailureClassFilterChange={setFailureClassFilter}
        loading={loading}
        refreshing={refreshing}
        onRefresh={() => loadPanel({ quiet: true })}
      />

      <PanelBody
        metrics={metrics}
        items={items}
        loading={loading}
        refreshing={refreshing}
        error={error}
        filterSummary={filterSummary}
        selectedId={selectedId}
        selectedItem={selectedItem}
        detailLoading={detailLoading}
        detailError={detailError}
        canMutateDeadLetters={canMutateDeadLetters}
        actionPending={actionPending}
        actionError={actionError}
        actionSuccess={actionSuccess}
        dismissComment={dismissComment}
        dismissConfirmOpen={dismissConfirmOpen}
        retryExecuteConfirmed={retryExecuteConfirmed}
        retryExecutePhrase={retryExecutePhrase}
        canExecuteDeadLetterRetry={canExecuteDeadLetterRetry}
        onDismissStart={handleDismissStart}
        onDismissCancel={handleDismissCancel}
        onDismissConfirm={handleDismissConfirm}
        onDismissCommentChange={setDismissComment}
        onRetryRequest={handleRetryRequest}
        onRetryExecute={handleRetryExecute}
        onRetryExecuteConfirmedChange={setRetryExecuteConfirmed}
        onRetryExecutePhraseChange={setRetryExecutePhrase}
        onRetryLoad={() => loadPanel()}
        onSelectRow={handleSelectRow}
        onCloseDetail={handleCloseDetail}
        detailRef={detailRef}
        displaySettings={displaySettings}
      />
    </section>
  );
}

function PanelHeader({
  cardHeaderStyle,
  cardTitleStyle,
  cardSubtitleStyle,
  filterLabelStyle,
  selectStyle,
  statusFilter,
  sourceTypeFilter,
  failureClassFilter,
  failureClassOptions,
  onStatusFilterChange,
  onSourceTypeFilterChange,
  onFailureClassFilterChange,
  loading,
  refreshing,
  onRefresh,
}) {
  return (
    <div style={cardHeaderStyle}>
      <PanelTitle cardTitleStyle={cardTitleStyle} cardSubtitleStyle={cardSubtitleStyle} />
      <div style={controlsStyle}>
        <label style={filterWrapperStyle}>
          <span style={filterLabelStyle}>Status</span>
          <select
            value={statusFilter}
            onChange={(event) => onStatusFilterChange(event.target.value)}
            style={selectStyle}
            aria-label="Filter dead letters by status"
          >
            {STATUS_FILTERS.map((status) => (
              <option key={status} value={status}>
                {status === "all" ? "All statuses" : formatLabel(status)}
              </option>
            ))}
          </select>
        </label>
        <label style={filterWrapperStyle}>
          <span style={filterLabelStyle}>Source Type</span>
          <select
            value={sourceTypeFilter}
            onChange={(event) => onSourceTypeFilterChange(event.target.value)}
            style={selectStyle}
            aria-label="Filter dead letters by source type"
          >
            {SOURCE_TYPE_FILTERS.map((sourceType) => (
              <option key={sourceType} value={sourceType}>
                {sourceType === "all" ? "All source types" : formatLabel(sourceType)}
              </option>
            ))}
          </select>
        </label>
        <label style={filterWrapperStyle}>
          <span style={filterLabelStyle}>Failure Class</span>
          <select
            value={failureClassFilter}
            onChange={(event) => onFailureClassFilterChange(event.target.value)}
            style={selectStyle}
            aria-label="Filter dead letters by failure class"
          >
            {failureClassOptions.map((failureClass) => (
              <option key={failureClass} value={failureClass}>
                {failureClass === "all" ? "All failure classes" : failureClass}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          onClick={onRefresh}
          disabled={loading || refreshing}
          style={{
            ...refreshButtonStyle,
            opacity: loading || refreshing ? 0.65 : 1,
            cursor: loading || refreshing ? "default" : "pointer",
          }}
        >
          {refreshing ? "Refreshing..." : "Refresh"}
        </button>
      </div>
    </div>
  );
}

function PanelTitle({ cardTitleStyle, cardSubtitleStyle }) {
  return (
    <div>
      <p style={sectionLabelStyle}>SOAR Operations</p>
      <h2 style={cardTitleStyle}>Dead Letter Queue</h2>
      {/* spec: SPEC-UI-004 - dead-letter wording presents real retry workflows without implying remediation is enabled. */}
      <p style={cardSubtitleStyle}>
        Real operational review of failed playbook, notification, and response work. Retry visibility does not enable destructive remediation.
      </p>
    </div>
  );
}

function PanelBody({
  metrics,
  items,
  loading,
  refreshing,
  error,
  filterSummary,
  selectedId,
  selectedItem,
  detailLoading,
  detailError,
  canMutateDeadLetters,
  actionPending,
  actionError,
  actionSuccess,
  dismissComment,
  dismissConfirmOpen,
  retryExecuteConfirmed,
  retryExecutePhrase,
  canExecuteDeadLetterRetry,
  onDismissStart,
  onDismissCancel,
  onDismissConfirm,
  onDismissCommentChange,
  onRetryRequest,
  onRetryExecute,
  onRetryExecuteConfirmedChange,
  onRetryExecutePhraseChange,
  onRetryLoad,
  onSelectRow,
  onCloseDetail,
  detailRef,
  displaySettings,
}) {
  return (
    <div style={panelContentStyle}>
      <div style={operationalNoticeStyle} role="note">
        {OPERATIONAL_NOTICE}
      </div>

      {refreshing ? <p style={refreshTextStyle}>Refreshing dead letters...</p> : null}

      <MetricsRow metrics={metrics} />

      {metrics?.oldest_active_at ? (
        <p style={oldestActiveStyle}>
          Oldest active dead letter: {formatTimestamp(metrics.oldest_active_at, displaySettings, "—")}
        </p>
      ) : null}

      {error ? <ErrorBanner error={error} onRetry={onRetryLoad} /> : null}

      {loading ? <p style={emptyTextStyle}>Loading dead letters...</p> : null}

      {!loading && (!error || selectedId !== null) ? (
        <MasterDetailLayout
          detailOpen={selectedId !== null}
          ariaLabel="Dead letter list and selected dead letter detail"
        >
          <MasterDetailMaster ariaLabel="Dead letters">
          {items.length === 0 ? (
            <p style={emptyTextStyle}>No dead letters found ({filterSummary}).</p>
          ) : (
            <div style={tableSectionStyle}>
            <DeadLetterTable
              items={items}
              selectedId={selectedId}
              onSelectRow={onSelectRow}
              displaySettings={displaySettings}
            />
            </div>
          )}
          </MasterDetailMaster>

          <MasterDetailPane ref={detailRef} ariaLabel="Selected dead letter detail">
          <div style={detailPanelStyle}>
            <div style={detailHeaderStyle}>
              <h3 style={detailTitleStyle}>Dead Letter Detail</h3>
              {selectedId !== null ? (
                <button type="button" style={detailCloseButtonStyle} onClick={onCloseDetail}>
                  Close
                </button>
              ) : null}
            </div>
            {selectedId === null ? (
              <p style={emptyTextStyle}>Select a dead letter row to review full context.</p>
            ) : detailLoading ? (
              <p style={emptyTextStyle}>Loading dead letter detail...</p>
            ) : detailError ? (
              <DetailError error={detailError} />
            ) : selectedItem ? (
              <DeadLetterDetail
                item={selectedItem}
                canMutateDeadLetters={canMutateDeadLetters}
                actionPending={actionPending}
                actionError={actionError}
                actionSuccess={actionSuccess}
                dismissComment={dismissComment}
                dismissConfirmOpen={dismissConfirmOpen}
                retryExecuteConfirmed={retryExecuteConfirmed}
                retryExecutePhrase={retryExecutePhrase}
                canExecuteDeadLetterRetry={canExecuteDeadLetterRetry}
                onDismissStart={onDismissStart}
                onDismissCancel={onDismissCancel}
                onDismissConfirm={onDismissConfirm}
                onDismissCommentChange={onDismissCommentChange}
                onRetryRequest={onRetryRequest}
                onRetryExecute={onRetryExecute}
                onRetryExecuteConfirmedChange={onRetryExecuteConfirmedChange}
                onRetryExecutePhraseChange={onRetryExecutePhraseChange}
                displaySettings={displaySettings}
              />
            ) : (
              <p style={emptyTextStyle}>No detail available for this dead letter.</p>
            )}
          </div>
          </MasterDetailPane>
        </MasterDetailLayout>
      ) : null}
    </div>
  );
}

function MetricsRow({ metrics }) {
  return (
    <div style={metricsGridStyle}>
      {DEAD_LETTER_STATUSES.map((status) => (
        <MetricCard
          key={status}
          label={formatLabel(status)}
          value={getStatusMetricCount(metrics, status)}
          badgeStyle={getStatusBadgeStyle(status)}
        />
      ))}
    </div>
  );
}

function ErrorBanner({ error, onRetry }) {
  return (
    <div style={errorStateStyle}>
      <span>Error: {error}</span>
      <button type="button" style={retryButtonStyle} onClick={onRetry}>
        Retry
      </button>
    </div>
  );
}

function DetailError({ error }) {
  return <div style={detailErrorStyle}>{error}</div>;
}

function MetricCard({ label, value, badgeStyle }) {
  return (
    <div style={metricCardStyle}>
      <span style={{ ...statusBadgeStyle, ...badgeStyle }}>{label}</span>
      <strong style={metricValueStyle}>{value}</strong>
    </div>
  );
}

function DeadLetterTable({ items, selectedId, onSelectRow, displaySettings }) {
  return (
    <div style={tableWrapperStyle}>
      <table style={tableStyle}>
        <thead>
          <tr>
            <th style={headerCellStyle}>ID</th>
            <th style={headerCellStyle}>Status</th>
            <th style={headerCellStyle}>Source Type</th>
            <th style={headerCellStyle}>Source ID</th>
            <th style={headerCellStyle}>Failure Class</th>
            <th style={headerCellStyle}>Retry Count</th>
            <th style={headerCellStyle}>Created</th>
            <th style={headerCellStyle}>View</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr
              key={item.id}
              aria-selected={selectedId === item.id}
              style={{
                ...rowStyle,
                ...(selectedId === item.id ? selectedRowStyle : null),
              }}
            >
              <td style={{ ...bodyCellStyle, ...monoCellStyle }}>{item.id}</td>
              <td style={bodyCellStyle}>
                <span style={{ ...statusBadgeStyle, ...getStatusBadgeStyle(item.status) }}>
                  {formatLabel(item.status)}
                </span>
              </td>
              <td style={bodyCellStyle}>{formatLabel(item.source_type)}</td>
              <td style={{ ...bodyCellStyle, ...monoCellStyle }}>{item.source_id}</td>
              <td style={bodyCellStyle} title={item.failure_class || ""}>
                {truncateText(item.failure_class, 40)}
              </td>
              <td style={{ ...bodyCellStyle, ...monoCellStyle }}>{item.retry_count ?? 0}</td>
              <td style={{ ...bodyCellStyle, ...timeCellStyle }} title={item.created_at || ""}>
                {formatTimestamp(item.created_at, displaySettings, "—")}
              </td>
              <td style={bodyCellStyle}>
                <button
                  type="button"
                  style={{
                    ...viewButtonStyle,
                    ...(selectedId === item.id ? selectedViewButtonStyle : null),
                  }}
                  onClick={(event) => onSelectRow(item.id, event.currentTarget)}
                  title={`View dead letter ${item.id}`}
                >
                  View
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DeadLetterDetail({
  item,
  canMutateDeadLetters,
  actionPending,
  actionError,
  actionSuccess,
  dismissComment,
  dismissConfirmOpen,
  retryExecuteConfirmed,
  retryExecutePhrase,
  canExecuteDeadLetterRetry,
  onDismissStart,
  onDismissCancel,
  onDismissConfirm,
  onDismissCommentChange,
  onRetryRequest,
  onRetryExecute,
  onRetryExecuteConfirmedChange,
  onRetryExecutePhraseChange,
  displaySettings,
}) {
  const payloadEntries = getPayloadEntries(item.payload_json);

  return (
    <>
      <p style={detailHeadingStyle}>Dead Letter #{item.id}</p>
      <DetailSummaryGrid item={item} displaySettings={displaySettings} />
      <div style={detailSectionStyle}>
        <div style={detailSectionTitleStyle}>Error Message</div>
        <p style={detailParagraphStyle}>{item.error_message || "—"}</p>
      </div>
      <div style={detailSectionStyle}>
        <PayloadSection payloadEntries={payloadEntries} />
      </div>
      {hasLinkedContext(item) ? <LinkedContextSection item={item} /> : null}
      {item.dismiss_reason || item.dismissed_at ? (
        <div style={detailSectionStyle}>
          <DismissalSection item={item} displaySettings={displaySettings} />
        </div>
      ) : null}
      {item.retry_requested_at ? (
        <RetryRequestSection item={item} displaySettings={displaySettings} />
      ) : null}
      <DeadLetterActions
        item={item}
        canMutateDeadLetters={canMutateDeadLetters}
        actionPending={actionPending}
        actionError={actionError}
        actionSuccess={actionSuccess}
        dismissComment={dismissComment}
        dismissConfirmOpen={dismissConfirmOpen}
        retryExecuteConfirmed={retryExecuteConfirmed}
        retryExecutePhrase={retryExecutePhrase}
        canExecuteDeadLetterRetry={canExecuteDeadLetterRetry}
        onDismissStart={onDismissStart}
        onDismissCancel={onDismissCancel}
        onDismissConfirm={onDismissConfirm}
        onDismissCommentChange={onDismissCommentChange}
        onRetryRequest={onRetryRequest}
        onRetryExecute={onRetryExecute}
        onRetryExecuteConfirmedChange={onRetryExecuteConfirmedChange}
        onRetryExecutePhraseChange={onRetryExecutePhraseChange}
      />
    </>
  );
}

function DeadLetterActions({
  item,
  canMutateDeadLetters,
  actionPending,
  actionError,
  actionSuccess,
  dismissComment,
  dismissConfirmOpen,
  retryExecuteConfirmed,
  retryExecutePhrase,
  canExecuteDeadLetterRetry,
  onDismissStart,
  onDismissCancel,
  onDismissConfirm,
  onDismissCommentChange,
  onRetryRequest,
  onRetryExecute,
  onRetryExecuteConfirmedChange,
  onRetryExecutePhraseChange,
}) {
  if (!canMutateDeadLetters) {
    return null;
  }

  const canDismiss = item.status === "open" || item.status === "retrying";
  const canRetryRequest = item.status === "open" && item.retryable === true;
  const canRetryExecute =
    canExecuteDeadLetterRetry &&
    item.status === "retrying" &&
    item.source_type === "playbook_execution" &&
    item.retryable === true;
  if (!canDismiss && !canRetryRequest && !canRetryExecute && !actionError && !actionSuccess) {
    return null;
  }

  const busy = Boolean(actionPending);
  const retryExecuteReady =
    retryExecuteConfirmed && retryExecutePhrase.trim().toUpperCase() === RETRY_EXECUTE_PHRASE;

  return (
    <div style={detailSectionStyle}>
      <div style={detailSectionTitleStyle}>Review Actions</div>
      <p style={actionHelpTextStyle}>
        Retry request records operator intent only. It does not execute playbooks or run
        steps.
      </p>
      {actionSuccess ? (
        <div style={actionSuccessStyle} role="status" aria-live="polite">
          {actionSuccess}
        </div>
      ) : null}
      {actionError ? (
        <div style={detailErrorStyle} role="alert">
          {actionError}
        </div>
      ) : null}
      <div style={actionButtonRowStyle}>
        {canDismiss ? (
          <button
            type="button"
            style={secondaryActionButtonStyle}
            onClick={onDismissStart}
            disabled={busy}
          >
            {actionPending === "dismiss" ? "Dismissing..." : "Dismiss"}
          </button>
        ) : null}
        {canRetryRequest ? (
          <button
            type="button"
            style={primaryActionButtonStyle}
            onClick={onRetryRequest}
            disabled={busy}
          >
            {actionPending === "retry-request" ? "Requesting..." : "Retry Request"}
          </button>
        ) : null}
      </div>
      {dismissConfirmOpen && canDismiss ? (
        <div style={dismissFormStyle}>
          <label style={dismissLabelStyle}>
            <span style={detailLabelStyle}>Comment or reason (optional)</span>
            <textarea
              value={dismissComment}
              onChange={(event) => onDismissCommentChange(event.target.value)}
              rows={3}
              style={dismissTextareaStyle}
              disabled={busy}
              aria-label="Dismiss comment or reason"
              autoFocus
            />
          </label>
          <div style={actionButtonRowStyle}>
            <button
              type="button"
              style={dangerActionButtonStyle}
              onClick={onDismissConfirm}
              disabled={busy}
            >
              {actionPending === "dismiss" ? "Dismissing..." : "Confirm Dismiss"}
            </button>
            <button
              type="button"
              style={secondaryActionButtonStyle}
              onClick={onDismissCancel}
              disabled={busy}
              aria-label="Cancel dismiss confirmation"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : null}
      {canRetryExecute ? (
        <div style={retryExecutePanelStyle}>
          <div style={detailSectionTitleStyle}>Retry Execute</div>
          <p style={actionHelpTextStyle}>
            This creates a new pending playbook execution only. It does not run steps
            immediately. The new execution must be picked up by the manual executor.
          </p>
          <label style={checkboxLabelStyle}>
            <input
              type="checkbox"
              checked={retryExecuteConfirmed}
              onChange={(event) => onRetryExecuteConfirmedChange(event.target.checked)}
              disabled={busy}
            />
            <span>I understand retry-execute creates pending work only and does not run steps.</span>
          </label>
          <label style={dismissLabelStyle}>
            <span style={detailLabelStyle}>Type RETRY to confirm</span>
            <input
              type="text"
              value={retryExecutePhrase}
              onChange={(event) => onRetryExecutePhraseChange(event.target.value)}
              disabled={busy}
              style={confirmInputStyle}
              aria-label="Retry execute confirmation phrase"
              autoFocus={retryExecuteConfirmed}
            />
          </label>
          <button
            type="button"
            style={dangerActionButtonStyle}
            onClick={onRetryExecute}
            disabled={busy || !retryExecuteReady}
          >
            {actionPending === "retry-execute" ? "Creating Pending Execution..." : "Retry Execute"}
          </button>
        </div>
      ) : null}
    </div>
  );
}

function DetailSummaryGrid({ item, displaySettings }) {
  return (
    <div style={detailGridStyle}>
      <DetailField label="Status" value={formatLabel(item.status)} />
      <DetailField label="Source Type" value={formatLabel(item.source_type)} />
      <DetailField label="Source ID" value={item.source_id} mono />
      <DetailField label="Failure Class" value={item.failure_class || "—"} />
      <DetailField label="Retry Count" value={item.retry_count ?? 0} mono />
      <DetailField label="Retryable" value={item.retryable} />
      <DetailField label="Created" value={formatTimestamp(item.created_at, displaySettings, "—")} />
      <DetailField
        label="First Failed"
        value={formatTimestamp(item.first_failed_at, displaySettings, "—")}
      />
      <DetailField
        label="Last Failed"
        value={formatTimestamp(item.last_failed_at, displaySettings, "—")}
      />
    </div>
  );
}

function PayloadSection({ payloadEntries }) {
  return (
    <>
      <div style={detailSectionTitleStyle}>Payload (redacted)</div>
      {payloadEntries.length === 0 ? (
        <p style={emptyTextStyle}>No payload fields recorded.</p>
      ) : (
        <dl style={payloadListStyle}>
          {payloadEntries.map(([key, value]) => (
            <PayloadRow key={key} fieldKey={key} value={value} />
          ))}
        </dl>
      )}
    </>
  );
}

function PayloadRow({ fieldKey, value }) {
  return (
    <div style={payloadRowStyle}>
      <dt style={payloadKeyStyle}>{fieldKey}</dt>
      <dd style={payloadValueStyle}>{formatDisplayValue(value)}</dd>
    </div>
  );
}

function LinkedContextSection({ item }) {
  return (
    <div style={detailSectionStyle}>
      <div style={detailSectionTitleStyle}>Linked Context</div>
      <div style={detailGridStyle}>
        {item.execution_id != null ? (
          <DetailField
            label="Execution"
            value={`#${item.execution_id} — View in SOAR Playbooks`}
            wrap
          />
        ) : null}
        {item.incident_id != null ? (
          <DetailField
            label="Incident"
            value={`#${item.incident_id} — View in SOAR Incidents`}
            wrap
          />
        ) : null}
        {item.alert_id != null ? (
          <DetailField label="Alert" value={`#${item.alert_id}`} mono />
        ) : null}
        {item.playbook_id ? (
          <DetailField label="Playbook" value={item.playbook_id} mono wrap />
        ) : null}
        {item.step_index != null || item.action_name ? (
          <DetailField
            label="Step"
            value={
              item.step_index != null && item.action_name
                ? `index ${item.step_index}, action ${item.action_name}`
                : item.step_index != null
                  ? `index ${item.step_index}`
                  : item.action_name
            }
            wrap
          />
        ) : null}
      </div>
    </div>
  );
}

function DismissalSection({ item, displaySettings }) {
  return (
    <>
      <div style={detailSectionTitleStyle}>Dismissal</div>
      <div style={detailGridStyle}>
        <DetailField label="Dismiss Reason" value={item.dismiss_reason || "—"} wrap />
        <DetailField
          label="Dismissed At"
          value={formatTimestamp(item.dismissed_at, displaySettings, "—")}
        />
      </div>
    </>
  );
}

function RetryRequestSection({ item, displaySettings }) {
  return (
    <div style={detailSectionStyle}>
      <div style={detailSectionTitleStyle}>Retry Request</div>
      <DetailField
        label="Retry Requested At"
        value={formatTimestamp(item.retry_requested_at, displaySettings, "—")}
      />
    </div>
  );
}

function DetailField({ label, value, mono = false, wrap = false }) {
  return (
    <div style={detailFieldStyle}>
      <span style={detailLabelStyle}>{label}</span>
      <span
        style={{
          ...detailValueStyle,
          ...(mono ? detailMonoValueStyle : null),
          ...(wrap ? detailWrappedValueStyle : null),
        }}
      >
        {formatDisplayValue(value)}
      </span>
    </div>
  );
}

export default DeadLettersPanel;

const sectionLabelStyle = {
  margin: "0 0 4px",
  color: "#8b949e",
  fontSize: "11px",
  fontWeight: "700",
  letterSpacing: "0.08em",
  textTransform: "uppercase",
};

const panelContentStyle = {
  padding: "16px 20px 20px",
};

const operationalNoticeStyle = {
  marginBottom: "14px",
  padding: "10px 12px",
  borderRadius: "8px",
  border: "1px solid rgba(88, 166, 255, 0.25)",
  backgroundColor: "rgba(31, 111, 235, 0.08)",
  color: "#93c5fd",
  fontSize: "13px",
  lineHeight: 1.5,
};

const refreshTextStyle = {
  margin: "0 0 10px",
  color: "#8b949e",
  fontSize: "12px",
};

const controlsStyle = {
  display: "flex",
  flexWrap: "wrap",
  gap: "12px",
  alignItems: "flex-end",
};

const filterWrapperStyle = {
  display: "flex",
  flexDirection: "column",
  gap: "4px",
};

const refreshButtonStyle = {
  minHeight: "36px",
  padding: "8px 14px",
  borderRadius: "8px",
  border: "1px solid #30363d",
  backgroundColor: "#161b22",
  color: "#e6edf3",
  fontSize: "13px",
  fontWeight: "600",
};

const metricsGridStyle = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
  gap: "10px",
  marginBottom: "12px",
};

const metricCardStyle = {
  display: "flex",
  flexDirection: "column",
  gap: "8px",
  padding: "12px",
  borderRadius: "10px",
  border: "1px solid #30363d",
  backgroundColor: "#0d1117",
};

const metricValueStyle = {
  color: "#e6edf3",
  fontSize: "22px",
  fontWeight: "700",
};

const statusBadgeStyle = {
  display: "inline-flex",
  alignItems: "center",
  width: "fit-content",
  padding: "3px 8px",
  borderRadius: "999px",
  border: "1px solid transparent",
  fontSize: "11px",
  fontWeight: "700",
  letterSpacing: "0.04em",
  textTransform: "uppercase",
};

const oldestActiveStyle = {
  margin: "0 0 14px",
  color: "#8b949e",
  fontSize: "12px",
};

const errorStateStyle = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: "12px",
  marginBottom: "12px",
  padding: "10px 12px",
  borderRadius: "8px",
  border: "1px solid rgba(248, 113, 113, 0.35)",
  backgroundColor: "rgba(248, 113, 113, 0.08)",
  color: "#fca5a5",
  fontSize: "13px",
};

const retryButtonStyle = {
  minHeight: "30px",
  padding: "6px 10px",
  borderRadius: "8px",
  border: "1px solid rgba(248, 113, 113, 0.45)",
  backgroundColor: "rgba(248, 113, 113, 0.12)",
  color: "#fecaca",
  fontSize: "12px",
  fontWeight: "700",
  cursor: "pointer",
};

const emptyTextStyle = {
  margin: 0,
  color: "#8b949e",
  fontSize: "13px",
  lineHeight: 1.5,
};

const tableSectionStyle = {
  marginBottom: "16px",
};

const tableWrapperStyle = {
  overflowX: "auto",
  border: "1px solid #30363d",
  borderRadius: "10px",
};

const tableStyle = {
  width: "100%",
  borderCollapse: "collapse",
  fontSize: "13px",
};

const headerCellStyle = {
  textAlign: "left",
  padding: "10px 12px",
  color: "#8b949e",
  fontSize: "11px",
  fontWeight: "700",
  letterSpacing: "0.06em",
  textTransform: "uppercase",
  borderBottom: "1px solid #30363d",
  backgroundColor: "#161b22",
};

const rowStyle = {
  borderBottom: "1px solid #21262d",
};

const selectedRowStyle = {
  backgroundColor: "rgba(31, 111, 235, 0.08)",
};

const bodyCellStyle = {
  padding: "10px 12px",
  color: "#e6edf3",
  verticalAlign: "top",
};

const monoCellStyle = {
  fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
  fontSize: "12px",
};

const timeCellStyle = {
  whiteSpace: "nowrap",
  color: "#c9d1d9",
};

const viewButtonStyle = {
  minHeight: "30px",
  padding: "6px 10px",
  borderRadius: "8px",
  border: "1px solid rgba(88, 166, 255, 0.35)",
  backgroundColor: "rgba(31, 111, 235, 0.14)",
  color: "#93c5fd",
  fontSize: "12px",
  fontWeight: "700",
  cursor: "pointer",
};

const selectedViewButtonStyle = {
  borderColor: "rgba(147, 197, 253, 0.75)",
  backgroundColor: "rgba(31, 111, 235, 0.24)",
};

const detailPanelStyle = {
  marginTop: "4px",
  border: "1px solid #30363d",
  borderRadius: "10px",
  backgroundColor: "#0d1117",
  padding: "14px",
};

const detailHeaderStyle = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  marginBottom: "12px",
};

const detailTitleStyle = {
  margin: 0,
  color: "#e6edf3",
  fontSize: "14px",
  fontWeight: "700",
};

const detailCloseButtonStyle = {
  minHeight: "30px",
  padding: "6px 10px",
  borderRadius: "8px",
  border: "1px solid #30363d",
  backgroundColor: "#161b22",
  color: "#c9d1d9",
  fontSize: "12px",
  fontWeight: "700",
  cursor: "pointer",
};

const detailHeadingStyle = {
  margin: "0 0 12px",
  color: "#e6edf3",
  fontSize: "15px",
  fontWeight: "700",
};

const detailGridStyle = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
  gap: "12px",
};

const detailSectionStyle = {
  marginTop: "14px",
  paddingTop: "14px",
  borderTop: "1px solid #30363d",
};

const detailSectionTitleStyle = {
  marginBottom: "8px",
  color: "#8b949e",
  fontSize: "12px",
  fontWeight: "700",
  letterSpacing: "0.08em",
  textTransform: "uppercase",
};

const detailParagraphStyle = {
  margin: 0,
  color: "#e6edf3",
  fontSize: "13px",
  lineHeight: 1.5,
  whiteSpace: "pre-wrap",
  wordBreak: "break-word",
};

const payloadListStyle = {
  margin: 0,
  display: "flex",
  flexDirection: "column",
  gap: "8px",
};

const payloadRowStyle = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
  gap: "10px",
  alignItems: "start",
};

const payloadKeyStyle = {
  margin: 0,
  color: "#8b949e",
  fontSize: "12px",
  fontWeight: "700",
};

const payloadValueStyle = {
  margin: 0,
  color: "#e6edf3",
  fontSize: "13px",
  fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
  wordBreak: "break-word",
};

const detailFieldStyle = {
  display: "flex",
  flexDirection: "column",
  gap: "4px",
};

const detailLabelStyle = {
  color: "#8b949e",
  fontSize: "11px",
  fontWeight: "700",
  letterSpacing: "0.06em",
  textTransform: "uppercase",
};

const detailValueStyle = {
  color: "#e6edf3",
  fontSize: "13px",
  lineHeight: 1.4,
};

const detailMonoValueStyle = {
  fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
  fontSize: "12px",
};

const detailWrappedValueStyle = {
  whiteSpace: "pre-wrap",
  wordBreak: "break-word",
};

const detailErrorStyle = {
  padding: "10px 12px",
  borderRadius: "8px",
  border: "1px solid rgba(248, 113, 113, 0.35)",
  backgroundColor: "rgba(248, 113, 113, 0.08)",
  color: "#fca5a5",
  fontSize: "13px",
};

const actionHelpTextStyle = {
  margin: "0 0 10px",
  color: "#8b949e",
  fontSize: "13px",
  lineHeight: 1.5,
};

const actionSuccessStyle = {
  marginBottom: "10px",
  padding: "10px 12px",
  borderRadius: "8px",
  border: "1px solid rgba(126, 231, 135, 0.35)",
  backgroundColor: "rgba(126, 231, 135, 0.08)",
  color: "#7ee787",
  fontSize: "13px",
};

const actionButtonRowStyle = {
  display: "flex",
  flexWrap: "wrap",
  gap: "8px",
  alignItems: "center",
};

const primaryActionButtonStyle = {
  minHeight: "32px",
  padding: "7px 12px",
  borderRadius: "8px",
  border: "1px solid rgba(88, 166, 255, 0.45)",
  backgroundColor: "rgba(31, 111, 235, 0.18)",
  color: "#93c5fd",
  fontSize: "12px",
  fontWeight: "700",
  cursor: "pointer",
};

const secondaryActionButtonStyle = {
  minHeight: "32px",
  padding: "7px 12px",
  borderRadius: "8px",
  border: "1px solid #30363d",
  backgroundColor: "#161b22",
  color: "#c9d1d9",
  fontSize: "12px",
  fontWeight: "700",
  cursor: "pointer",
};

const dangerActionButtonStyle = {
  minHeight: "32px",
  padding: "7px 12px",
  borderRadius: "8px",
  border: "1px solid rgba(248, 113, 113, 0.45)",
  backgroundColor: "rgba(248, 113, 113, 0.12)",
  color: "#fecaca",
  fontSize: "12px",
  fontWeight: "700",
  cursor: "pointer",
};

const dismissFormStyle = {
  marginTop: "12px",
  display: "flex",
  flexDirection: "column",
  gap: "10px",
};

const dismissLabelStyle = {
  display: "flex",
  flexDirection: "column",
  gap: "6px",
};

const dismissTextareaStyle = {
  minHeight: "72px",
  resize: "vertical",
  borderRadius: "8px",
  border: "1px solid #30363d",
  backgroundColor: "#0d1117",
  color: "#e6edf3",
  padding: "8px 10px",
  fontSize: "13px",
  lineHeight: 1.4,
};

const retryExecutePanelStyle = {
  marginTop: "14px",
  padding: "12px",
  borderRadius: "8px",
  border: "1px solid rgba(248, 113, 113, 0.3)",
  backgroundColor: "rgba(248, 113, 113, 0.06)",
  display: "flex",
  flexDirection: "column",
  gap: "10px",
};

const checkboxLabelStyle = {
  display: "flex",
  gap: "8px",
  alignItems: "flex-start",
  color: "#e6edf3",
  fontSize: "13px",
  lineHeight: 1.4,
};

const confirmInputStyle = {
  minHeight: "34px",
  borderRadius: "8px",
  border: "1px solid #30363d",
  backgroundColor: "#0d1117",
  color: "#e6edf3",
  padding: "7px 10px",
  fontSize: "13px",
  maxWidth: "180px",
};
