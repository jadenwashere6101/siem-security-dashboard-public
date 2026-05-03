function AlertMitreDetails({
  alert,
  mitreSectionStyle,
  expandedLabelStyle,
  mitreHeaderRowStyle,
  mitreTechniqueBadgeStyle,
  mitreTechniqueNameStyle,
  mitreTacticStyle,
}) {
  return (
    (alert.mitre_technique_id || alert.mitre_technique_name || alert.mitre_tactic) && (
      <div style={mitreSectionStyle}>
        <p style={expandedLabelStyle}>MITRE ATT&CK</p>
        <div style={mitreHeaderRowStyle}>
          {alert.mitre_technique_id && (
            <span style={mitreTechniqueBadgeStyle}>
              {alert.mitre_technique_id}
            </span>
          )}
          {alert.mitre_technique_name && (
            <span style={mitreTechniqueNameStyle}>
              {alert.mitre_technique_name}
            </span>
          )}
        </div>
        {alert.mitre_tactic && (
          <p style={mitreTacticStyle}>
            <strong>Tactic:</strong> {alert.mitre_tactic}
          </p>
        )}
      </div>
    )
  );
}

export default AlertMitreDetails;
