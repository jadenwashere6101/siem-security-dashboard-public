import React, { useCallback, useEffect, useMemo, useState } from "react";
import { getSocBriefing, listSocBriefings } from "../services/socBriefingService";
import { formatTimestamp } from "../utils/displayFormatting";

const PAGE_SIZE = 10;
const CONTENT_STATUSES = ["all", "ready", "pending", "blocked", "failed", "skipped", "not_generated"];
const DELIVERY_STATUSES = ["all", "sent", "retry_scheduled", "failed", "blocked", "skipped"];
const SECTION_LABELS = {
  alerts_reviewed: "Alerts reviewed",
  dismissed_low_priority_findings: "Dismissed / low priority",
  escalations: "Escalations",
  critical_findings: "Critical findings",
  evidence: "Evidence",
  recommendations: "Recommendations",
};

function labelize(value) {
  return String(value || "unknown")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function badgeStyle(status) {
  const normalized = String(status || "none");
  if (["success", "ready", "sent"].includes(normalized)) {
    return { color: "#7ee787", borderColor: "rgba(126, 231, 135, 0.35)", backgroundColor: "rgba(126, 231, 135, 0.1)" };
  }
  if (["partial", "retry_scheduled", "pending", "not_generated"].includes(normalized)) {
    return { color: "#f5d487", borderColor: "rgba(245, 212, 135, 0.35)", backgroundColor: "rgba(245, 212, 135, 0.1)" };
  }
  if (["failed", "blocked"].includes(normalized)) {
    return { color: "#fca5a5", borderColor: "rgba(248, 113, 113, 0.35)", backgroundColor: "rgba(248, 113, 113, 0.1)" };
  }
  return { color: "#c9d1d9", borderColor: "rgba(201, 209, 217, 0.28)", backgroundColor: "rgba(201, 209, 217, 0.08)" };
}

function StatusBadge({ label, status }) {
  return (
    <span
      style={{
        ...badgeStyle(status),
        borderStyle: "solid",
        borderWidth: 1,
        borderRadius: 6,
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        fontSize: "0.72rem",
        fontWeight: 700,
        lineHeight: 1,
        padding: "5px 7px",
        whiteSpace: "nowrap",
      }}
    >
      {label ? `${label}: ` : ""}
      {labelize(status || "none")}
    </span>
  );
}

function SectionList({ title, items }) {
  const safeItems = Array.isArray(items) ? items : [];
  return (
    <section style={{ borderTop: "1px solid rgba(139, 148, 158, 0.22)", paddingTop: 14 }}>
      <h3 style={{ color: "#f0f6fc", fontSize: "0.95rem", margin: "0 0 8px" }}>{title}</h3>
      {safeItems.length === 0 ? (
        <p style={{ color: "#8b949e", margin: 0, fontSize: "0.85rem" }}>No entries recorded.</p>
      ) : (
        <ul style={{ margin: 0, paddingLeft: 18, color: "#c9d1d9", display: "grid", gap: 7 }}>
          {safeItems.map((item, index) => (
            <li key={`${title}-${index}`} style={{ lineHeight: 1.45 }}>
              {typeof item === "object" ? JSON.stringify(item) : String(item)}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function BriefingRow({ briefing, selected, onSelect }) {
  const deliveryStatus = briefing.delivery?.latest_status || "none";
  return (
    <button
      type="button"
      onClick={() => onSelect(briefing.id)}
      style={{
        width: "100%",
        textAlign: "left",
        border: selected ? "1px solid rgba(88, 166, 255, 0.58)" : "1px solid rgba(139, 148, 158, 0.22)",
        borderRadius: 8,
        background: selected ? "rgba(31, 111, 235, 0.16)" : "rgba(13, 17, 23, 0.64)",
        color: "#c9d1d9",
        padding: 12,
        cursor: "pointer",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "start" }}>
        <div>
          <div style={{ color: "#f0f6fc", fontWeight: 800 }}>Briefing #{briefing.id}</div>
          <div style={{ color: "#8b949e", fontSize: "0.78rem", marginTop: 3 }}>
            {briefing.schedule?.name || "Scheduled SOC briefing"} · {formatTimestamp(briefing.generated_at || briefing.created_at)}
          </div>
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "flex-end", gap: 6 }}>
          <StatusBadge label="Content" status={briefing.content_status} />
          <StatusBadge label="Slack" status={deliveryStatus} />
        </div>
      </div>
      <p style={{ color: "#adbac7", fontSize: "0.84rem", lineHeight: 1.4, margin: "8px 0 0" }}>
        {briefing.summary || "No summary recorded."}
      </p>
    </button>
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
      setItems(payload.items || []);
      setTotal(Number(payload.total || 0));
      if (!selectedId && payload.items?.length) {
        setSelectedId(payload.items[0].id);
      }
    } catch (err) {
      setError(err.message || "Unable to load SOC briefings.");
    } finally {
      setLoading(false);
    }
  }, [filters, selectedId]);

  useEffect(() => {
    loadList();
  }, [loadList]);

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

  const canPrevious = offset > 0;
  const canNext = offset + PAGE_SIZE < total;

  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 16, alignItems: "start" }}>
      <section style={{ display: "grid", gap: 12 }}>
        <div style={{ display: "grid", gap: 10, border: "1px solid rgba(139, 148, 158, 0.22)", borderRadius: 8, padding: 12, background: "rgba(13, 17, 23, 0.58)" }}>
          <h2 style={{ color: "#f0f6fc", fontSize: "1rem", margin: 0 }}>SOC Briefing History</h2>
          <input
            aria-label="Search briefings"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
              setOffset(0);
            }}
            placeholder="Search summaries, schedules, errors"
            style={{ background: "#0d1117", border: "1px solid rgba(139, 148, 158, 0.36)", borderRadius: 6, color: "#f0f6fc", padding: "9px 10px" }}
          />
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
            <label style={{ color: "#8b949e", display: "grid", gap: 5, fontSize: "0.76rem", fontWeight: 700 }}>
              Content
              <select aria-label="Content status" value={contentStatus} onChange={(event) => { setContentStatus(event.target.value); setOffset(0); }} style={{ background: "#0d1117", color: "#f0f6fc", border: "1px solid rgba(139, 148, 158, 0.36)", borderRadius: 6, padding: 8 }}>
                {CONTENT_STATUSES.map((status) => <option key={status} value={status}>{labelize(status)}</option>)}
              </select>
            </label>
            <label style={{ color: "#8b949e", display: "grid", gap: 5, fontSize: "0.76rem", fontWeight: 700 }}>
              Slack
              <select aria-label="Slack delivery status" value={deliveryStatus} onChange={(event) => { setDeliveryStatus(event.target.value); setOffset(0); }} style={{ background: "#0d1117", color: "#f0f6fc", border: "1px solid rgba(139, 148, 158, 0.36)", borderRadius: 6, padding: 8 }}>
                {DELIVERY_STATUSES.map((status) => <option key={status} value={status}>{labelize(status)}</option>)}
              </select>
            </label>
          </div>
        </div>
        {error && <div role="alert" style={{ color: "#fca5a5", border: "1px solid rgba(248, 113, 113, 0.28)", borderRadius: 8, padding: 10 }}>{error}</div>}
        <div style={{ display: "grid", gap: 10 }}>
          {loading ? <div style={{ color: "#8b949e" }}>Loading briefings...</div> : null}
          {!loading && items.length === 0 ? <div style={{ color: "#8b949e" }}>No saved briefings match the current filters.</div> : null}
          {items.map((item) => (
            <BriefingRow key={item.id} briefing={item} selected={item.id === selectedId} onSelect={setSelectedId} />
          ))}
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", color: "#8b949e", fontSize: "0.82rem" }}>
          <span>{total ? `${offset + 1}-${Math.min(offset + PAGE_SIZE, total)} of ${total}` : "0 of 0"}</span>
          <div style={{ display: "flex", gap: 8 }}>
            <button type="button" disabled={!canPrevious} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>Previous</button>
            <button type="button" disabled={!canNext} onClick={() => setOffset(offset + PAGE_SIZE)}>Next</button>
          </div>
        </div>
      </section>

      <section style={{ border: "1px solid rgba(139, 148, 158, 0.22)", borderRadius: 8, background: "rgba(13, 17, 23, 0.58)", padding: 16, minHeight: 420 }}>
        {detailLoading && <div style={{ color: "#8b949e" }}>Loading briefing detail...</div>}
        {!detailLoading && !detail && <div style={{ color: "#8b949e" }}>Select a saved briefing.</div>}
        {!detailLoading && detail && (
          <div style={{ display: "grid", gap: 16 }}>
            <header style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "start" }}>
              <div>
                <h2 style={{ color: "#f0f6fc", margin: 0, fontSize: "1.12rem" }}>Briefing #{detail.id}</h2>
                <p style={{ color: "#8b949e", margin: "4px 0 0", fontSize: "0.82rem" }}>
                  {detail.schedule?.name || "Scheduled SOC briefing"} · {formatTimestamp(detail.generated_at || detail.created_at)}
                </p>
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "flex-end", gap: 6 }}>
                <StatusBadge label="Content" status={detail.content_status} />
                <StatusBadge label="Run" status={detail.run?.status} />
                <StatusBadge label="Slack" status={detail.deliveries?.[0]?.status || "none"} />
              </div>
            </header>
            <p style={{ color: "#c9d1d9", lineHeight: 1.5, margin: 0 }}>{detail.summary || "No summary recorded."}</p>
            {(detail.error_code || detail.error_message || detail.run?.error_code) && (
              <div style={{ border: "1px solid rgba(248, 113, 113, 0.28)", borderRadius: 8, color: "#fca5a5", padding: 10 }}>
                {detail.error_code || detail.run?.error_code || "degraded"}: {detail.error_message || detail.run?.error_message || "Briefing completed in a degraded state."}
              </div>
            )}
            {Object.entries(SECTION_LABELS).map(([key, label]) => (
              <SectionList key={key} title={label} items={detail.sections?.[key]} />
            ))}
            <section style={{ borderTop: "1px solid rgba(139, 148, 158, 0.22)", paddingTop: 14 }}>
              <h3 style={{ color: "#f0f6fc", fontSize: "0.95rem", margin: "0 0 8px" }}>Delivery attempts</h3>
              {(detail.deliveries || []).length === 0 ? (
                <p style={{ color: "#8b949e", margin: 0 }}>No Slack delivery attempt recorded.</p>
              ) : (
                <div style={{ display: "grid", gap: 8 }}>
                  {detail.deliveries.map((attempt) => (
                    <div key={attempt.id} style={{ display: "flex", justifyContent: "space-between", gap: 10, color: "#c9d1d9", border: "1px solid rgba(139, 148, 158, 0.18)", borderRadius: 8, padding: 10 }}>
                      <StatusBadge status={attempt.status} />
                      <span>{formatTimestamp(attempt.last_attempted_at || attempt.created_at)}</span>
                      <span>{attempt.failure_code || "no failure"}</span>
                    </div>
                  ))}
                </div>
              )}
            </section>
          </div>
        )}
      </section>
    </div>
  );
}
