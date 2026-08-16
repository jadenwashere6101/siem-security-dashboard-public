import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { SOURCE_METADATA } from "../utils/sourceMetadata";
import {
  createNistBoundary,
  getNistExplanationRequest,
  loadNistBoundaries,
  loadNistEvidence,
  loadNistResults,
  loadNistRuns,
  nistExportUrl,
  queueNistExplanation,
  startNistAssessment,
  updateNistBoundary,
} from "../services/nistEvidenceService";
import {
  MasterDetailLayout,
  MasterDetailMaster,
  MasterDetailPane,
  useMasterDetailFocus,
} from "./MasterDetailLayout";
import { WorkspaceInitialState, WorkspaceRefreshState } from "./WorkspaceAsyncState";
import { Button, Card, Chip, Panel, SectionHeader } from "./uiPrimitives";
import "./NistEvidenceWorkspace.css";

const DISCLAIMER = "Evidence availability does not determine requirement satisfaction or compliance.";
const EVIDENCE_PAGE_SIZE = 25;
const EXPLANATION_POLL_MS = 1500;
const TERMINAL_REQUEST_STATES = new Set([
  "completed", "partial", "degraded", "failed", "timed_out", "cancelled", "expired",
]);

export const NIST_STATUS_LABELS = Object.freeze({
  mapping: Object.freeze({
    strong_siem_evidence: "Strong SIEM mapping",
    partial_siem_evidence: "Partial SIEM mapping",
  }),
  evidence: Object.freeze({
    evidence_available: "Evidence available",
    partial_evidence: "Partial evidence",
    no_evidence_found: "No evidence found",
    not_assessable_by_siem: "Outside SIEM visibility",
  }),
  confidence: Object.freeze({
    healthy: "Collection healthy",
    degraded: "Collection degraded",
    unknown: "Collection unknown",
  }),
});

const STATUS_HELP = Object.freeze({
  mapping: "How directly this requirement maps to evidence observable by this SIEM.",
  evidence: "What the deterministic collector found in the persisted assessment window.",
  confidence: "Whether collection health supports interpreting absence of evidence.",
});

const SUMMARY_LABELS = Object.freeze({
  confidence: Object.freeze({
    healthy: "healthy",
    degraded: "degraded",
    unknown: "unknown",
  }),
  evidence: Object.freeze({
    evidence_available: "available",
    partial_evidence: "partial",
    no_evidence_found: "no evidence found",
    not_assessable_by_siem: "outside SIEM visibility",
  }),
});

function formatSummaryCounts(counts, labels) {
  if (!counts || typeof counts !== "object" || Array.isArray(counts)) return "—";
  const keys = [
    ...Object.keys(labels).filter((key) => Object.prototype.hasOwnProperty.call(counts, key)),
    ...Object.keys(counts).filter((key) => !Object.prototype.hasOwnProperty.call(labels, key)).sort(),
  ];
  const entries = keys.map((key) => [key, counts[key]])
    .filter(([, count]) => Number.isFinite(Number(count)));
  if (!entries.length) return "—";
  return entries
    .map(([key, count]) => `${Number(count)} ${labels[key] || key.replaceAll("_", " ")}`)
    .join(" · ");
}

function formatDate(value) {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? String(value) : parsed.toLocaleString();
}

function newClientRequestId() {
  if (typeof window !== "undefined" && window.crypto?.randomUUID) return window.crypto.randomUUID();
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (token) => {
    const value = Math.floor(Math.random() * 16);
    return (token === "x" ? value : (value & 0x3) | 0x8).toString(16);
  });
}

function statusTone(kind, value) {
  if (kind === "mapping") return value === "strong_siem_evidence" ? "info" : "neutral";
  if (kind === "evidence") return value === "partial_evidence" ? "warning" : "neutral";
  if (kind === "confidence") return value === "degraded" ? "warning" : "neutral";
  return "neutral";
}

function StatusChip({ kind, value }) {
  return (
    <Chip tone={statusTone(kind, value)} title={STATUS_HELP[kind]}>
      {NIST_STATUS_LABELS[kind]?.[value] || String(value || "Unknown")}
    </Chip>
  );
}

function BoundaryEditor({ boundary, onClose, onSaved }) {
  const firstField = useRef(null);
  const [form, setForm] = useState(() => ({
    name: boundary?.name || "",
    description: boundary?.description || "",
    selected_sources: boundary?.selected_sources || [],
    environments: (boundary?.environments || []).join(", "),
    default_window_hours: boundary?.default_window_hours || 24,
    is_active: boundary?.is_active ?? true,
  }));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    firstField.current?.focus();
    const handleKeyDown = (event) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  const toggleSource = (source) => {
    setForm((current) => ({
      ...current,
      selected_sources: current.selected_sources.includes(source)
        ? current.selected_sources.filter((item) => item !== source)
        : [...current.selected_sources, source],
    }));
  };

  const submit = async (event) => {
    event.preventDefault();
    setSaving(true);
    setError("");
    const payload = {
      ...form,
      default_window_hours: Number(form.default_window_hours),
      environments: form.environments.split(",").map((item) => item.trim()).filter(Boolean),
    };
    try {
      const saved = boundary
        ? await updateNistBoundary(boundary.id, payload)
        : await createNistBoundary(payload);
      onSaved(saved);
    } catch (err) {
      setError(err.message || "Unable to save assessment boundary.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="nist-modal-backdrop" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose();
    }}>
      <div role="dialog" aria-modal="true" aria-labelledby="nist-boundary-editor-title" className="nist-modal">
        <form onSubmit={submit}>
          <SectionHeader
            id="nist-boundary-editor-title"
            eyebrow="Declared scope"
            title={boundary ? "Edit assessment boundary" : "Create assessment boundary"}
            subtitle="Boundaries are authorized declarations; they are not automatically discovered CUI boundaries."
          />
          <div className="nist-modal__body">
            {error ? <p role="alert" className="nist-error">{error}</p> : null}
            <label className="nist-field">Name
              <input ref={firstField} required maxLength={120} value={form.name}
                onChange={(event) => setForm({ ...form, name: event.target.value })} />
            </label>
            <label className="nist-field">Description
              <textarea maxLength={1000} rows={3} value={form.description}
                onChange={(event) => setForm({ ...form, description: event.target.value })} />
            </label>
            <fieldset className="nist-fieldset">
              <legend>Canonical sources</legend>
              <div className="nist-source-grid">
                {SOURCE_METADATA.map((source) => (
                  <label key={source.source}>
                    <input type="checkbox" checked={form.selected_sources.includes(source.source)}
                      onChange={() => toggleSource(source.source)} /> {source.displayLabel}
                  </label>
                ))}
              </div>
            </fieldset>
            <label className="nist-field">Environments (comma separated)
              <input value={form.environments}
                onChange={(event) => setForm({ ...form, environments: event.target.value })} />
            </label>
            <label className="nist-field">Default window (hours)
              <input type="number" min="1" max="168" required value={form.default_window_hours}
                onChange={(event) => setForm({ ...form, default_window_hours: event.target.value })} />
            </label>
            <label className="nist-checkbox">
              <input type="checkbox" checked={form.is_active}
                onChange={(event) => setForm({ ...form, is_active: event.target.checked })} /> Active
            </label>
          </div>
          <div className="nist-modal__actions">
            <Button onClick={onClose} disabled={saving}>Cancel</Button>
            <Button type="submit" variant="primary" disabled={saving || !form.selected_sources.length}>
              {saving ? "Saving…" : "Save boundary"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

function EvidenceCard({ reference, onNavigate }) {
  const entityId = Number(reference.entity_id);
  const canNavigate = Number.isInteger(entityId) && entityId > 0 &&
    ["alert", "incident", "approval_request", "playbook_execution"].includes(reference.entity_type);
  return (
    <article className="nist-evidence-card">
      <div className="nist-row nist-row--spread">
        <strong>Reference {reference.id}</strong>
        <Chip tone="neutral">{reference.operational_classification || "unknown classification"}</Chip>
      </div>
      <p>{reference.evidence_summary || "No bounded summary available."}</p>
      <dl className="nist-definition-grid">
        <div><dt>Category / type</dt><dd>{reference.evidence_category} / {reference.evidence_type}</dd></div>
        <div><dt>Source</dt><dd>{reference.canonical_source} ({reference.source_type})</dd></div>
        <div><dt>Entity</dt><dd>{reference.entity_type} #{reference.entity_id}</dd></div>
        <div><dt>Source health</dt><dd>{reference.source_health_state}</dd></div>
        <div><dt>Occurred</dt><dd>{formatDate(reference.occurrence_timestamp)}</dd></div>
        <div><dt>Ingested</dt><dd>{formatDate(reference.ingestion_timestamp)}</dd></div>
        <div><dt>Collected</dt><dd>{formatDate(reference.collection_timestamp)}</dd></div>
        <div><dt>Query window</dt><dd>{formatDate(reference.query_window_start)} – {formatDate(reference.query_window_end)}</dd></div>
        <div><dt>Query hash</dt><dd className="nist-mono">{reference.query_hash}</dd></div>
        <div><dt>Versions</dt><dd>{reference.catalog_version} / {reference.mapping_version} / {reference.collector_version}</dd></div>
      </dl>
      {reference.is_truncated ? (
        <p className="nist-notice">Persisted evidence was truncated; {reference.omitted_count || 0} record(s) were omitted.</p>
      ) : null}
      {canNavigate ? <Button onClick={() => onNavigate(reference.entity_type, entityId)}>Open {reference.entity_type.replaceAll("_", " ")}</Button> : null}
    </article>
  );
}

function ExplanationPanel({ state }) {
  if (state.status === "idle") return null;
  if (["queued", "running"].includes(state.status)) {
    return <div role="status" className="nist-explanation"><strong>Anakin explanation</strong><p>{state.status === "queued" ? "Queued…" : "Running…"}</p></div>;
  }
  if (state.status !== "available") {
    return <div role="status" className="nist-explanation nist-explanation--unavailable"><strong>Anakin explanation</strong><p>Explanation unavailable</p></div>;
  }
  const explanation = state.result;
  return (
    <div className="nist-explanation" aria-label="Grounded Anakin explanation">
      <div className="nist-row nist-row--spread"><strong>Anakin explanation</strong><Chip tone="info">Optional · non-authoritative</Chip></div>
      <h4>Summary</h4><p>{explanation.summary}</p>
      <h4>Why this evidence matters</h4><p>{explanation.why_it_matters}</p>
      <h4>Limitations</h4><p>{explanation.limitations}</p>
      <h4>Additional evidence needed</h4>
      {explanation.additional_evidence_needed.length ? <ul>{explanation.additional_evidence_needed.map((item) => <li key={item}>{item}</li>)}</ul> : <p>None stated.</p>}
      <p className="nist-muted">Cites persisted reference IDs: {explanation.citation_ids.join(", ") || "none"}</p>
    </div>
  );
}

function NistEvidenceWorkspace({
  userRole,
  onOpenAlert,
  onOpenIncident,
  onOpenApproval,
  onOpenPlaybookExecution,
}) {
  const isSuperAdmin = userRole === "super_admin";
  const [boundaries, setBoundaries] = useState([]);
  const [selectedBoundaryId, setSelectedBoundaryId] = useState(null);
  const [runs, setRuns] = useState([]);
  const [runCursor, setRunCursor] = useState(null);
  const [selectedRunId, setSelectedRunId] = useState(null);
  const [results, setResults] = useState([]);
  const [selectedResultId, setSelectedResultId] = useState(null);
  const [evidence, setEvidence] = useState({ items: [], total: 0, offset: 0 });
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");
  const [editorBoundary, setEditorBoundary] = useState(undefined);
  const [assessmentRunning, setAssessmentRunning] = useState(false);
  const [actionError, setActionError] = useState("");
  const [explanation, setExplanation] = useState({ status: "idle", result: null });
  const selectionEpoch = useRef(0);
  const explanationPollTimer = useRef(null);
  const { detailRef, rememberTrigger } = useMasterDetailFocus(selectedResultId);

  const selectedBoundary = boundaries.find((item) => item.id === selectedBoundaryId) || null;
  const selectedRun = runs.find((item) => item.id === selectedRunId) || null;
  const selectedResult = results.find((item) => item.id === selectedResultId) || null;

  const loadBoundaries = useCallback(async ({ quiet = false, preferredId = null } = {}) => {
    quiet ? setRefreshing(true) : setLoading(true);
    setError("");
    try {
      const data = await loadNistBoundaries();
      const items = Array.isArray(data.items) ? data.items : [];
      setBoundaries(items);
      setSelectedBoundaryId((current) => {
        const candidate = preferredId || current;
        return items.some((item) => item.id === candidate) ? candidate : items[0]?.id || null;
      });
    } catch (err) {
      setError(err.message || "Unable to load NIST assessment boundaries.");
      if (!quiet) setBoundaries([]);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { loadBoundaries(); }, [loadBoundaries]);
  useEffect(() => () => {
    if (explanationPollTimer.current) window.clearTimeout(explanationPollTimer.current);
  }, []);

  const refreshRuns = useCallback(async ({ append = false } = {}) => {
    if (!selectedBoundaryId) {
      setRuns([]); setRunCursor(null); setSelectedRunId(null); return;
    }
    setDetailLoading(true); setDetailError("");
    try {
      const data = await loadNistRuns(selectedBoundaryId, { cursor: append ? runCursor : null });
      const items = Array.isArray(data.items) ? data.items : [];
      setRuns((current) => append ? [...current, ...items] : items);
      setRunCursor(data.next_cursor || null);
      if (!append) setSelectedRunId(items[0]?.id || null);
    } catch (err) {
      setDetailError(err.message || "Unable to load assessment run history.");
      if (!append) setRuns([]);
    } finally { setDetailLoading(false); }
  }, [runCursor, selectedBoundaryId]);

  useEffect(() => {
    if (explanationPollTimer.current) window.clearTimeout(explanationPollTimer.current);
    selectionEpoch.current += 1;
    setExplanation({ status: "idle", result: null });
    setResults([]); setSelectedResultId(null); setEvidence({ items: [], total: 0, offset: 0 });
    refreshRuns();
    // runCursor intentionally resets with boundary selection.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedBoundaryId]);

  useEffect(() => {
    if (explanationPollTimer.current) window.clearTimeout(explanationPollTimer.current);
    selectionEpoch.current += 1;
    setExplanation({ status: "idle", result: null });
    setSelectedResultId(null); setEvidence({ items: [], total: 0, offset: 0 });
    if (!selectedRunId) { setResults([]); return; }
    let active = true;
    setDetailLoading(true); setDetailError("");
    loadNistResults(selectedRunId).then((data) => {
      if (!active) return;
      const items = Array.isArray(data.items) ? data.items : [];
      setResults(items); setSelectedResultId(items[0]?.id || null);
    }).catch((err) => { if (active) { setResults([]); setDetailError(err.message || "Unable to load requirement results."); } })
      .finally(() => { if (active) setDetailLoading(false); });
    return () => { active = false; };
  }, [selectedRunId]);

  const fetchEvidence = useCallback(async (offset = 0) => {
    if (!selectedRunId || !selectedResult) return;
    setDetailLoading(true); setDetailError("");
    try {
      const data = await loadNistEvidence(selectedRunId, selectedResult.requirement_id, { limit: EVIDENCE_PAGE_SIZE, offset });
      setEvidence({ items: Array.isArray(data.items) ? data.items : [], total: Number(data.total || 0), offset: Number(data.offset || 0) });
    } catch (err) {
      setEvidence({ items: [], total: 0, offset });
      setDetailError(err.message || "Unable to load persisted evidence references.");
    } finally { setDetailLoading(false); }
  }, [selectedResult, selectedRunId]);

  useEffect(() => {
    if (explanationPollTimer.current) window.clearTimeout(explanationPollTimer.current);
    selectionEpoch.current += 1;
    setExplanation({ status: "idle", result: null });
    if (selectedResult) fetchEvidence(0); else setEvidence({ items: [], total: 0, offset: 0 });
  }, [fetchEvidence, selectedResult]);

  const handleRunAssessment = async () => {
    if (!selectedBoundaryId || !window.confirm("Run a new deterministic assessment for this boundary?")) return;
    setAssessmentRunning(true); setActionError("");
    try { await startNistAssessment(selectedBoundaryId); await refreshRuns(); }
    catch (err) { setActionError(err.message || "Unable to run assessment."); }
    finally { setAssessmentRunning(false); }
  };

  const pollExplanation = useCallback(async (requestId, epoch, expectedBinding) => {
    try {
      const response = await getNistExplanationRequest(requestId);
      if (epoch !== selectionEpoch.current) return;
      const status = String(response.status || "");
      if (!response.terminal && !TERMINAL_REQUEST_STATES.has(status)) {
        setExplanation({ status: status === "queued" ? "queued" : "running", result: null });
        explanationPollTimer.current = window.setTimeout(
          () => pollExplanation(requestId, epoch, expectedBinding), EXPLANATION_POLL_MS
        );
        return;
      }
      explanationPollTimer.current = null;
      const modelResult = response.result;
      const binding = modelResult?.binding;
      const bindingMatches = binding && Object.entries(expectedBinding).every(
        ([key, value]) => String(binding[key]) === String(value)
      );
      if (status === "completed" && bindingMatches && modelResult?.explanation_status === "available" && modelResult.explanation) {
        setExplanation({ status: "available", result: modelResult.explanation });
      } else {
        setExplanation({ status: "unavailable", result: null });
      }
    } catch (_) {
      if (epoch === selectionEpoch.current) setExplanation({ status: "unavailable", result: null });
    }
  }, []);

  const handleExplain = async () => {
    if (!selectedBoundary || !selectedRun || !selectedResult) return;
    const epoch = selectionEpoch.current;
    if (explanationPollTimer.current) window.clearTimeout(explanationPollTimer.current);
    setExplanation({ status: "queued", result: null }); setActionError("");
    try {
      const expectedBinding = {
        boundary_id: selectedBoundary.id,
        run_id: selectedRun.id,
        requirement_result_id: selectedResult.id,
        requirement_id: selectedResult.requirement_id,
      };
      const queued = await queueNistExplanation({
        ...expectedBinding,
        client_request_id: newClientRequestId(),
      });
      if (epoch !== selectionEpoch.current) return;
      pollExplanation(queued.request_id, epoch, expectedBinding);
    } catch (err) {
      if (epoch === selectionEpoch.current) {
        setExplanation({ status: "unavailable", result: null });
        setActionError(err.status === 404 ? "The selected persisted result is no longer available." : "Explanation unavailable");
      }
    }
  };

  const handleEntityNavigation = (entityType, entityId) => {
    if (entityType === "alert") onOpenAlert?.(entityId);
    else if (entityType === "incident") onOpenIncident?.(entityId);
    else if (entityType === "approval_request") onOpenApproval?.(entityId);
    else if (entityType === "playbook_execution") onOpenPlaybookExecution?.(entityId);
  };

  const runSummary = useMemo(() => selectedRun?.summary_counts || {}, [selectedRun]);

  return (
    <div className="nist-workspace" data-testid="nist-evidence-workspace">
      <Card tone="warning" className="nist-disclaimer" role="note"><strong>{DISCLAIMER}</strong></Card>
      <Card>
        <SectionHeader eyebrow="NIST SP 800-171 Rev. 3" title="NIST Evidence Workspace"
          subtitle="Inspect persisted deterministic assessment-support results and their provenance."
          actions={<>
            <Button onClick={() => loadBoundaries({ quiet: true })} disabled={refreshing}>Refresh</Button>
            {isSuperAdmin ? <Button onClick={() => setEditorBoundary(null)}>Create boundary</Button> : null}
            {isSuperAdmin && selectedBoundary ? <Button onClick={() => setEditorBoundary(selectedBoundary)}>Edit boundary</Button> : null}
            {isSuperAdmin && selectedBoundary ? <Button variant="primary" onClick={handleRunAssessment} disabled={assessmentRunning}>{assessmentRunning ? "Running…" : "Run assessment"}</Button> : null}
          </>} />
        <div className="nist-workspace__body">
          <WorkspaceInitialState loading={loading} error={error} loadingLabel="Loading NIST boundaries…" onRetry={loadBoundaries} />
          <WorkspaceRefreshState refreshing={refreshing} refreshError="" />
          {!loading && !error && !boundaries.length ? <div className="nist-empty">No active assessment boundaries are available.</div> : null}
          {boundaries.length ? <>
            <label className="nist-field nist-boundary-selector">Assessment boundary
              <select value={selectedBoundaryId || ""} onChange={(event) => setSelectedBoundaryId(Number(event.target.value))}>
                {boundaries.map((boundary) => <option key={boundary.id} value={boundary.id}>{boundary.name}</option>)}
              </select>
            </label>
            {selectedBoundary ? <Panel className="nist-boundary-card">
              <div className="nist-row nist-row--spread"><h3>{selectedBoundary.name}</h3><Chip tone="neutral">Declared boundary #{selectedBoundary.id}</Chip></div>
              <p>{selectedBoundary.description || "No description provided."}</p>
              <p className="nist-muted">Sources: {selectedBoundary.selected_sources.join(", ") || "none"} · Environments: {selectedBoundary.environments.join(", ") || "none"} · Default window: {selectedBoundary.default_window_hours}h</p>
              <p className="nist-muted">{selectedBoundary.scope_declaration}</p>
            </Panel> : null}
          </> : null}
          {actionError ? <p role="alert" className="nist-error">{actionError}</p> : null}
          {selectedBoundary ? <div className="nist-run-layout">
            <aside className="nist-run-history" aria-label="Assessment run history">
              <h3>Run history</h3>
              {detailLoading && !runs.length ? <p role="status">Loading runs…</p> : null}
              {!detailLoading && !runs.length ? <p className="nist-muted">No persisted assessment runs.</p> : null}
              {runs.map((run) => <button type="button" key={run.id} className={`nist-run-button${run.id === selectedRunId ? " is-selected" : ""}`} onClick={() => setSelectedRunId(run.id)}>
                <strong>Run #{run.id}</strong><span>{formatDate(run.created_at)}</span><span>{String(run.status).replaceAll("_", " ")}</span>
              </button>)}
              {runCursor ? <Button onClick={() => refreshRuns({ append: true })} disabled={detailLoading}>Load older runs</Button> : null}
            </aside>
            <main className="nist-run-content">
              {selectedRun ? <>
                <Panel>
                  <div className="nist-row nist-row--spread"><h3>Run #{selectedRun.id}</h3><Chip tone="neutral">{String(selectedRun.status).replaceAll("_", " ")}</Chip></div>
                  <dl className="nist-definition-grid">
                    <div><dt>Window</dt><dd>{formatDate(selectedRun.requested_window_start)} – {formatDate(selectedRun.requested_window_end)}</dd></div>
                    <div><dt>Framework</dt><dd>{selectedRun.framework_id} · {selectedRun.framework_version}</dd></div>
                    <div><dt>Catalog</dt><dd>{runSummary.catalog_version || selectedRun.catalog_version} · <span className="nist-mono">{selectedRun.catalog_hash}</span></dd></div>
                    <div><dt>Collector</dt><dd>{selectedRun.collector_version}</dd></div>
                    <div><dt>Requirements</dt><dd>{runSummary.requirement_count ?? results.length}</dd></div>
                    <div><dt>Confidence</dt><dd>{formatSummaryCounts(runSummary.by_collection_confidence, SUMMARY_LABELS.confidence)}</dd></div>
                    <div><dt>Evidence</dt><dd>{formatSummaryCounts(runSummary.by_evidence_status, SUMMARY_LABELS.evidence)}</dd></div>
                  </dl>
                  <div className="nist-row"><a className="nist-link-button" href={nistExportUrl(selectedRun.id, "json")}>Export JSON</a><a className="nist-link-button" href={nistExportUrl(selectedRun.id, "csv")}>Export CSV</a></div>
                </Panel>
                <MasterDetailLayout detailOpen={Boolean(selectedResult)} ariaLabel="NIST requirement results">
                  <MasterDetailMaster ariaLabel="Requirement results">
                    <div className="nist-table-scroll"><table className="nist-results-table"><thead><tr><th>Requirement</th><th>Mapping</th><th>Evidence</th><th>Confidence</th></tr></thead>
                      <tbody>{results.map((result) => <tr key={result.id} className={result.id === selectedResultId ? "is-selected" : ""}><td><button type="button" onClick={(event) => { rememberTrigger(event.currentTarget); setSelectedResultId(result.id); }}>{result.requirement_id}<span>{result.requirement_name}</span></button></td><td><StatusChip kind="mapping" value={result.mapping_strength} /></td><td><StatusChip kind="evidence" value={result.evidence_status} /></td><td><StatusChip kind="confidence" value={result.collection_confidence} /></td></tr>)}</tbody></table></div>
                  </MasterDetailMaster>
                  {selectedResult ? <MasterDetailPane ref={detailRef} ariaLabel="Requirement evidence detail">
                    <div className="nist-detail">
                      <p className="nist-eyebrow">{selectedResult.requirement_id}</p><h2>{selectedResult.requirement_name}</h2>
                      <div className="nist-status-row"><StatusChip kind="mapping" value={selectedResult.mapping_strength} /><StatusChip kind="evidence" value={selectedResult.evidence_status} /><StatusChip kind="confidence" value={selectedResult.collection_confidence} /></div>
                      <p className="nist-notice"><strong>Assessment-support only.</strong> These statuses do not determine requirement satisfaction.</p>
                      <dl className="nist-detail-list"><div><dt>Deterministic reason</dt><dd>{selectedResult.reason_code}</dd></div><div><dt>Limitation</dt><dd>{selectedResult.limitation}</dd></div><div><dt>Evidence counts</dt><dd>{selectedResult.evidence_count} persisted; {selectedResult.omitted_count} omitted by collector</dd></div></dl>
                      <Button variant="primary" onClick={handleExplain} disabled={["queued", "running"].includes(explanation.status)}>Explain this result</Button>
                      <ExplanationPanel state={explanation} />
                      <h3>Persisted evidence references</h3>
                      {detailError ? <p role="alert" className="nist-error">{detailError}</p> : null}
                      {detailLoading ? <p role="status">Loading persisted evidence…</p> : null}
                      {!detailLoading && !evidence.items.length ? <p className="nist-muted">No persisted evidence references for this result.</p> : null}
                      {evidence.items.map((reference) => <EvidenceCard key={reference.id} reference={reference} onNavigate={handleEntityNavigation} />)}
                      {evidence.total > EVIDENCE_PAGE_SIZE ? <div className="nist-row nist-row--spread"><Button disabled={evidence.offset === 0} onClick={() => fetchEvidence(Math.max(0, evidence.offset - EVIDENCE_PAGE_SIZE))}>Previous evidence</Button><span>{evidence.offset + 1}–{Math.min(evidence.total, evidence.offset + EVIDENCE_PAGE_SIZE)} of {evidence.total}</span><Button disabled={evidence.offset + EVIDENCE_PAGE_SIZE >= evidence.total} onClick={() => fetchEvidence(evidence.offset + EVIDENCE_PAGE_SIZE)}>Next evidence</Button></div> : null}
                    </div>
                  </MasterDetailPane> : null}
                </MasterDetailLayout>
              </> : <div className="nist-empty">Select a persisted assessment run to inspect its results.</div>}
            </main>
          </div> : null}
        </div>
      </Card>
      {editorBoundary !== undefined ? <BoundaryEditor boundary={editorBoundary} onClose={() => setEditorBoundary(undefined)} onSaved={(saved) => { setEditorBoundary(undefined); loadBoundaries({ quiet: true, preferredId: saved.id }); }} /> : null}
    </div>
  );
}

export default NistEvidenceWorkspace;
