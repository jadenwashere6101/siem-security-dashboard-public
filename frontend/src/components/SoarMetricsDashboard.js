import React, { useCallback, useEffect, useRef, useState } from "react";
import { getDeadLetterMetrics } from "../services/deadLetterService";
import {
  getApprovalMetrics,
  getIncidentMetrics,
  getNotificationDeliveryMetrics,
  getPlaybookMetrics,
} from "../services/metricsService";
import { loadSoarQueueStatus } from "../services/soarQueueService";

// spec: SPEC-METRICS-001
export const REFRESH_INTERVAL_MS = 60_000;

function formatRefreshTime(date) {
  if (!date) return null;
  return (
    date.toLocaleTimeString("en-US", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      timeZone: "UTC",
      hour12: false,
    }) + " UTC"
  );
}

function SectionLoading({ label }) {
  return <div aria-label={`Loading ${label}`}>Loading…</div>;
}

function SectionError({ message, onRetry }) {
  return (
    <div role="alert">
      <span>{message || "Failed to load"}</span>
      <button onClick={onRetry} style={{ marginLeft: 8 }}>
        Retry
      </button>
    </div>
  );
}

function initSection() {
  return { data: null, loading: true, error: null };
}

export default function SoarMetricsDashboard({
  cardStyle,
  cardHeaderStyle,
  cardTitleStyle,
  cardSubtitleStyle,
  userRole,
}) {
  const [playbook, setPlaybook] = useState(initSection);
  const [deadLetter, setDeadLetter] = useState(initSection);
  const [notification, setNotification] = useState(initSection);
  const [incident, setIncident] = useState(initSection);
  const [approval, setApproval] = useState(initSection);
  const [queue, setQueue] = useState(initSection);
  const [refreshing, setRefreshing] = useState(false);
  const [lastRefreshedAt, setLastRefreshedAt] = useState(null);

  const intervalRef = useRef(null);
  const isSuperAdmin = userRole === "super_admin";

  const fetchSection = useCallback(async (fetchFn, setter) => {
    setter((prev) => ({ ...prev, loading: true, error: null }));
    try {
      const data = await fetchFn();
      setter({ data, loading: false, error: null });
    } catch (err) {
      setter((prev) => ({
        ...prev,
        loading: false,
        error: err?.message || "Failed to load",
      }));
    }
  }, []);

  const fetchAll = useCallback(async () => {
    setRefreshing(true);

    const sections = [
      [getPlaybookMetrics, setPlaybook],
      [getDeadLetterMetrics, setDeadLetter],
      [getNotificationDeliveryMetrics, setNotification],
      [getIncidentMetrics, setIncident],
      [getApprovalMetrics, setApproval],
    ];

    if (userRole === "super_admin") {
      sections.push([loadSoarQueueStatus, setQueue]);
    } else {
      setQueue((prev) => ({ ...prev, loading: false }));
    }

    const results = await Promise.allSettled(sections.map(([fn]) => fn()));

    results.forEach((result, i) => {
      const [, setter] = sections[i];
      if (result.status === "fulfilled") {
        setter({ data: result.value, loading: false, error: null });
      } else {
        setter((prev) => ({
          ...prev,
          loading: false,
          error: result.reason?.message || "Failed to load",
        }));
      }
    });

    setRefreshing(false);
    setLastRefreshedAt(new Date());
  }, [userRole]);

  useEffect(() => {
    fetchAll();
    intervalRef.current = setInterval(fetchAll, REFRESH_INTERVAL_MS);
    return () => {
      clearInterval(intervalRef.current);
    };
  }, [fetchAll]);

  const handleManualRefresh = useCallback(() => {
    setPlaybook((prev) => ({ ...prev, error: null }));
    setDeadLetter((prev) => ({ ...prev, error: null }));
    setNotification((prev) => ({ ...prev, error: null }));
    setIncident((prev) => ({ ...prev, error: null }));
    setApproval((prev) => ({ ...prev, error: null }));
    setQueue((prev) => ({ ...prev, error: null }));
    clearInterval(intervalRef.current);
    intervalRef.current = setInterval(fetchAll, REFRESH_INTERVAL_MS);
    fetchAll();
  }, [fetchAll]);

  return (
    <section style={cardStyle}>
      <header style={cardHeaderStyle}>
        <div>
          <span style={cardTitleStyle}>SOAR Metrics Dashboard</span>
          {lastRefreshedAt && (
            <span style={cardSubtitleStyle}>
              {" "}Last refreshed: {formatRefreshTime(lastRefreshedAt)}
            </span>
          )}
        </div>
        <div>
          {refreshing && <span aria-label="Refreshing">Refreshing…</span>}
          <button onClick={handleManualRefresh} disabled={refreshing}>
            Refresh now
          </button>
        </div>
      </header>

      <section aria-label="Playbook Metrics">
        <h3>Playbook Metrics</h3>
        {playbook.loading && <SectionLoading label="Playbook Metrics" />}
        {!playbook.loading && playbook.error && (
          <SectionError
            message={playbook.error}
            onRetry={() => fetchSection(getPlaybookMetrics, setPlaybook)}
          />
        )}
      </section>

      <section aria-label="Dead Letter Metrics">
        <h3>Dead Letter Metrics</h3>
        {deadLetter.loading && <SectionLoading label="Dead Letter Metrics" />}
        {!deadLetter.loading && deadLetter.error && (
          <SectionError
            message={deadLetter.error}
            onRetry={() => fetchSection(getDeadLetterMetrics, setDeadLetter)}
          />
        )}
      </section>

      <section aria-label="Notification Delivery Metrics">
        <h3>Notification Delivery Metrics</h3>
        {notification.loading && (
          <SectionLoading label="Notification Delivery Metrics" />
        )}
        {!notification.loading && notification.error && (
          <SectionError
            message={notification.error}
            onRetry={() =>
              fetchSection(getNotificationDeliveryMetrics, setNotification)
            }
          />
        )}
      </section>

      <section aria-label="Incident Metrics">
        <h3>Incident Metrics</h3>
        {incident.loading && <SectionLoading label="Incident Metrics" />}
        {!incident.loading && incident.error && (
          <SectionError
            message={incident.error}
            onRetry={() => fetchSection(getIncidentMetrics, setIncident)}
          />
        )}
      </section>

      <section aria-label="Approval Metrics">
        <h3>Approval Metrics</h3>
        {approval.loading && <SectionLoading label="Approval Metrics" />}
        {!approval.loading && approval.error && (
          <SectionError
            message={approval.error}
            onRetry={() => fetchSection(getApprovalMetrics, setApproval)}
          />
        )}
      </section>

      {isSuperAdmin && (
        <section aria-label="SOAR Queue Health">
          <h3>SOAR Queue Health</h3>
          {queue.loading && <SectionLoading label="SOAR Queue Health" />}
          {!queue.loading && queue.error && (
            <SectionError
              message={queue.error}
              onRetry={() => fetchSection(loadSoarQueueStatus, setQueue)}
            />
          )}
        </section>
      )}
    </section>
  );
}
