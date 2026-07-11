import AlertCorrelationSignals from "./AlertCorrelationSignals";
import AlertExportLinks from "./AlertExportLinks";
import AlertManualActions from "./AlertManualActions";
import AlertMitreDetails from "./AlertMitreDetails";
import AlertReputationDetails from "./AlertReputationDetails";
import AlertResponseLog from "./AlertResponseLog";
import AlertSourceDetails from "./AlertSourceDetails";
import { ResponseOutcomeBadge } from "./ResponseOutcome";
import ResponseStateSummary from "./ResponseStateSummary";
import LifecycleIndependenceNotice from "./LifecycleIndependenceNotice";
import TargetedAlertPanel from "./TargetedAlertPanel";
import { registryNavFromAlert } from "../utils/responseNavigation";
import {
  correlationListStyle,
  correlationPanelStyle,
  detailLabelTextStyle,
  detailSectionStyle,
  detailValueTextStyle,
  expandedSecondaryTextStyle,
  exportDividerStyle,
  exportLabelStyle,
  exportRowStyle,
  inlineExportLinkStyle,
  mitreHeaderRowStyle,
  mitreSectionStyle,
  mitreTacticStyle,
  mitreTechniqueBadgeStyle,
  mitreTechniqueNameStyle,
  signalRowStyle,
  sourceBadgeStyle,
  sourceTypeTextStyle,
  targetedAlertPanelStyle,
} from "./alertsTableStyles";

function AlertExpandedRow({
  alert,
  sourceBadge,
  correlationAlert,
  targetedAlertMeta,
  correlatedAlertTypes,
  responseLog,
  expandedCellStyle,
  expandedContentStyle,
  expandedLabelStyle,
  expandedTextStyle,
  monoCellStyle,
  canTakeAlertActions,
  downloadPdfReport,
  executeAction,
  executingActionId,
  getActionButtonStyle,
  getReputationBadgeStyle,
  onOpenResponseRegistry = null,
  onReviewIncident = null,
}) {
  return (
    <tr onClick={(e) => e.stopPropagation()}>
      <td colSpan="9" style={expandedCellStyle}>
        <div style={expandedContentStyle}>
          <p style={{ ...expandedLabelStyle, marginBottom: "10px" }}>Alert Details</p>

          <p style={{ ...expandedTextStyle, marginBottom: "6px" }}>
            <strong style={detailLabelTextStyle}>ID:</strong>{" "}
            <span style={detailValueTextStyle}>{alert.id}</span>
          </p>

          <p style={{ ...expandedTextStyle, marginBottom: "6px" }}>
            <strong style={detailLabelTextStyle}>Type:</strong>{" "}
            <span style={detailValueTextStyle}>{alert.alert_type}</span>
          </p>

          {targetedAlertMeta && (
            <TargetedAlertPanel
              targetedAlertMeta={targetedAlertMeta}
              correlationAlert={correlationAlert}
              correlatedAlertTypes={correlatedAlertTypes}
              correlationPanelStyle={correlationPanelStyle}
              targetedAlertPanelStyle={targetedAlertPanelStyle}
              expandedLabelStyle={expandedLabelStyle}
              expandedTextStyle={expandedTextStyle}
              correlationListStyle={correlationListStyle}
              monoCellStyle={monoCellStyle}
              alert={alert}
            />
          )}

          <AlertSourceDetails
            alert={alert}
            sourceBadge={sourceBadge}
            expandedTextStyle={expandedTextStyle}
            detailLabelTextStyle={detailLabelTextStyle}
            detailValueTextStyle={detailValueTextStyle}
            expandedSecondaryTextStyle={expandedSecondaryTextStyle}
            detailSectionStyle={detailSectionStyle}
            monoCellStyle={monoCellStyle}
          />

          <p style={{ ...expandedTextStyle, marginBottom: "6px" }}>
            <strong style={detailLabelTextStyle}>Severity:</strong>{" "}
            <span style={detailValueTextStyle}>{alert.severity}</span>
          </p>

          <p style={{ ...expandedTextStyle, marginBottom: "6px" }}>
            <strong style={detailLabelTextStyle}>Message:</strong>{" "}
            <span style={detailValueTextStyle}>{alert.message}</span>
          </p>

          <AlertMitreDetails
            alert={alert}
            mitreSectionStyle={mitreSectionStyle}
            expandedLabelStyle={expandedLabelStyle}
            mitreHeaderRowStyle={mitreHeaderRowStyle}
            mitreTechniqueBadgeStyle={mitreTechniqueBadgeStyle}
            mitreTechniqueNameStyle={mitreTechniqueNameStyle}
            mitreTacticStyle={mitreTacticStyle}
          />

          <AlertReputationDetails
            alert={alert}
            expandedTextStyle={expandedTextStyle}
            detailLabelTextStyle={detailLabelTextStyle}
            expandedSecondaryTextStyle={expandedSecondaryTextStyle}
            sourceBadgeStyle={sourceBadgeStyle}
            getReputationBadgeStyle={getReputationBadgeStyle}
          />

          <AlertCorrelationSignals
            alert={alert}
            detailSectionStyle={detailSectionStyle}
            signalRowStyle={signalRowStyle}
            sourceTypeTextStyle={sourceTypeTextStyle}
          />

          <p style={{ ...expandedTextStyle, marginBottom: "6px" }}>
            <strong style={detailLabelTextStyle}>Response Action:</strong>{" "}
            <span style={detailValueTextStyle}>{alert.response_action || "Not set"}</span>
          </p>
          <p style={{ ...expandedTextStyle, marginBottom: "6px" }}>
            <strong style={detailLabelTextStyle}>Response Outcome:</strong>{" "}
            <ResponseOutcomeBadge outcome={alert.response_outcome || null} />
          </p>

          <ResponseStateSummary
            alert={alert}
            onOpenRegistry={
              typeof onOpenResponseRegistry === "function"
                ? () => onOpenResponseRegistry(registryNavFromAlert(alert))
                : null
            }
          />
          <LifecycleIndependenceNotice onReviewIncident={onReviewIncident} />

          <AlertExportLinks
            alert={alert}
            exportRowStyle={exportRowStyle}
            exportLabelStyle={exportLabelStyle}
            inlineExportLinkStyle={inlineExportLinkStyle}
            exportDividerStyle={exportDividerStyle}
            downloadPdfReport={downloadPdfReport}
          />

          <AlertResponseLog logs={responseLog} />

          <AlertManualActions
            alertId={alert.id}
            sourceIp={alert.source_ip}
            executeAction={executeAction}
            executingActionId={executingActionId}
            canTakeAlertActions={canTakeAlertActions}
            getActionButtonStyle={getActionButtonStyle}
          />

          <p style={{ ...expandedTextStyle, marginBottom: "0" }}>
            <strong style={detailLabelTextStyle}>Created At:</strong>{" "}
            <span style={{ ...monoCellStyle, ...detailValueTextStyle }}>
              {alert.created_at}
            </span>
          </p>
        </div>
      </td>
    </tr>
  );
}

export default AlertExpandedRow;
