export const filterAlerts = (
  alerts,
  { searchTerm, severityFilter, statusFilter, sourceFilter }
) => {
  return alerts.filter((alert) => {
    const matchesSearch =
      !searchTerm ||
      alert.source_ip?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      alert.message?.toLowerCase().includes(searchTerm.toLowerCase());

    const matchesSeverity =
      !severityFilter || severityFilter === "all" || alert.severity === severityFilter;

    const matchesStatus =
      !statusFilter || statusFilter === "all" || alert.status === statusFilter;

    const matchesSource =
      !sourceFilter || sourceFilter === "all" || (alert.source || "legacy") === sourceFilter;

    return matchesSearch && matchesSeverity && matchesStatus && matchesSource;
  });
};

export const sortAlerts = (filteredAlerts, sortOption) => {
  return [...filteredAlerts].sort((a, b) => {
    if (sortOption === "newest") {
      return new Date(b.created_at) - new Date(a.created_at);
    }

    if (sortOption === "oldest") {
      return new Date(a.created_at) - new Date(b.created_at);
    }

    if (sortOption === "severity") {
      const order = { critical: 4, high: 3, medium: 2, low: 1 };
      return (order[b.severity] || 0) - (order[a.severity] || 0);
    }

    return 0;
  });
};

export const buildAlertMetrics = (filteredAlerts) => {
  const highCount = filteredAlerts.filter((alert) => alert.severity === "high").length;
  const mediumCount = filteredAlerts.filter((alert) => alert.severity === "medium").length;
  const lowCount = filteredAlerts.filter((alert) => alert.severity === "low").length;
  const uniqueIPs = new Set(filteredAlerts.map((alert) => alert.source_ip)).size;

  return {
    totalAlerts: filteredAlerts.length,
    highCount,
    mediumCount,
    lowCount,
    uniqueIPs,
  };
};

export const buildTopIPChartData = (filteredAlerts) => {
  const counts = {};

  filteredAlerts.forEach((alert) => {
    counts[alert.source_ip] = (counts[alert.source_ip] || 0) + 1;
  });

  return Object.entries(counts)
    .map(([ip, count]) => ({
      name: ip,
      value: count,
    }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 5);
};

export const buildAlertTimelineData = (filteredAlerts) => {
  const bucketCounts = new Map();
  const dayKeys = new Set();

  filteredAlerts.forEach((alert) => {
    if (!alert?.created_at) return;

    const createdAt = new Date(alert.created_at);
    if (Number.isNaN(createdAt.getTime())) return;

    const bucketStart = Date.UTC(
      createdAt.getUTCFullYear(),
      createdAt.getUTCMonth(),
      createdAt.getUTCDate(),
      createdAt.getUTCHours()
    );

    const dayKey = `${createdAt.getUTCFullYear()}-${createdAt.getUTCMonth()}-${createdAt.getUTCDate()}`;
    dayKeys.add(dayKey);
    bucketCounts.set(bucketStart, (bucketCounts.get(bucketStart) || 0) + 1);
  });

  const showDateInLabel = dayKeys.size > 1;

  return Array.from(bucketCounts.entries())
    .sort((a, b) => a[0] - b[0])
    .map(([bucketStart, count]) => {
      const bucketDate = new Date(bucketStart);
      const month = String(bucketDate.getUTCMonth() + 1).padStart(2, "0");
      const day = String(bucketDate.getUTCDate()).padStart(2, "0");
      const hour = String(bucketDate.getUTCHours()).padStart(2, "0");

      return {
        time: showDateInLabel
          ? `${month}/${day} ${hour}:00 UTC`
          : `${hour}:00 UTC`,
        count,
        bucketStart,
      };
    });
};
