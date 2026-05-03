function AlertsTableHeader({ headerCellStyle }) {
  return (
    <thead>
      <tr>
        <th style={headerCellStyle}>ID</th>
        <th style={headerCellStyle}>Type</th>
        <th style={headerCellStyle}>Source</th>
        <th style={headerCellStyle}>Source IP</th>
        <th style={headerCellStyle}>Behavior</th>
        <th style={headerCellStyle}>Severity</th>
        <th style={headerCellStyle}>Message</th>
        <th style={headerCellStyle}>Created At</th>
        <th style={headerCellStyle}>Action</th>
      </tr>
    </thead>
  );
}

export default AlertsTableHeader;
