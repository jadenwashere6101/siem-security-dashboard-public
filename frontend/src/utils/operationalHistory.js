export function getOperationalHistoryBadge(record) {
  const history = record?.operational_history;
  if (!history?.is_pre_tuning) {
    return null;
  }
  return history.label || "Pre-Tuning";
}

export function getOperationalHistoryDescription(record) {
  const history = record?.operational_history;
  if (!history?.is_pre_tuning) {
    return "";
  }
  return "Created before the pfSense tuning baseline.";
}
