function AlertsEmptyState({ emptyStateStyle, emptyStateTextStyle }) {
  return (
    <div style={emptyStateStyle}>
      <p style={emptyStateTextStyle}>
        No alerts found for the selected filters.
      </p>
    </div>
  );
}

export default AlertsEmptyState;
