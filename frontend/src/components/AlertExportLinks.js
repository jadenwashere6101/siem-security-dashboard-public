import { buildSiemPath } from "../utils/siemPath";

function AlertExportLinks({
  alert,
  exportRowStyle,
  exportLabelStyle,
  inlineExportLinkStyle,
  exportDividerStyle,
}) {
  return (
    <div style={exportRowStyle}>
      <span style={exportLabelStyle}>Export:</span>
      <a
        href={buildSiemPath(`/alerts/${alert.id}/report`)}
        style={inlineExportLinkStyle}
        onClick={(e) => e.stopPropagation()}
      >
        Download Incident Report (TXT)
      </a>
      <span style={exportDividerStyle}>|</span>
      <a
        href={buildSiemPath(`/alerts/${alert.id}/report/pdf`)}
        style={{
          ...inlineExportLinkStyle,
        }}
        onClick={(e) => e.stopPropagation()}
      >
        Download PDF Report
      </a>
    </div>
  );
}

export default AlertExportLinks;
