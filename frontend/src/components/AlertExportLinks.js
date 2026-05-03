import { buildSiemPath } from "../utils/siemPath";

function AlertExportLinks({
  alert,
  exportRowStyle,
  exportLabelStyle,
  inlineExportLinkStyle,
  exportDividerStyle,
  downloadPdfReport,
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
      <button
        type="button"
        style={{
          ...inlineExportLinkStyle,
          border: "none",
          backgroundColor: "transparent",
          padding: 0,
          cursor: "pointer",
        }}
        onClick={(e) => {
          e.stopPropagation();
          downloadPdfReport(
            buildSiemPath(`/alerts/${alert.id}/report/pdf`),
            `siem-alert-${alert.id}-report.pdf`
          );
        }}
      >
        Download PDF Report
      </button>
    </div>
  );
}

export default AlertExportLinks;
