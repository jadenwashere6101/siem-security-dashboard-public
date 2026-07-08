function AlertsTableHeader({ headerCellStyle, visibleColumns }) {
  return (
    <thead>
      <tr>
        <th style={headerCellStyle}>ID</th>
        {visibleColumns.type && <th style={headerCellStyle}>Type</th>}
        {visibleColumns.source && <th style={headerCellStyle}>Source</th>}
        {visibleColumns.sourceIp && <th style={headerCellStyle}>Source IP</th>}
        {visibleColumns.behavior && <th style={headerCellStyle}>Behavior</th>}
        {visibleColumns.severity && <th style={headerCellStyle}>Severity</th>}
        {visibleColumns.message && <th style={headerCellStyle}>Message</th>}
        {visibleColumns.createdAt && <th style={headerCellStyle}>Created At</th>}
        {visibleColumns.action && <th style={headerCellStyle}>Action</th>}
      </tr>
    </thead>
  );
}

export default AlertsTableHeader;
