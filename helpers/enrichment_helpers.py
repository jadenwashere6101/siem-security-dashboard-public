MITRE_ATTACK_MAPPINGS = {
    "failed_login_threshold": {
        "mitre_technique_id": "T1110",
        "mitre_technique_name": "Brute Force",
        "mitre_tactic": "Credential Access",
    },
    "port_scan_threshold": {
        "mitre_technique_id": "T1046",
        "mitre_technique_name": "Network Service Discovery",
        "mitre_tactic": "Discovery",
    },
    "suspicious_ip_reputation": {
        "mitre_technique_id": "T1595",
        "mitre_technique_name": "Active Scanning",
        "mitre_tactic": "Reconnaissance",
    },
    "password_spraying_threshold": {
        "mitre_technique_id": "T1110.003",
        "mitre_technique_name": "Password Spraying",
        "mitre_tactic": "Credential Access",
    },
    "successful_login_after_spray": {
        "mitre_technique_id": "T1110.003",
        "mitre_technique_name": "Password Spraying",
        "mitre_tactic": "Credential Access",
    },
}


def enrich_alert_with_mitre(alert_dict):
    alert_type = alert_dict.get("alert_type")
    mitre_data = MITRE_ATTACK_MAPPINGS.get(alert_type, {})

    alert_dict["mitre_technique_id"] = mitre_data.get("mitre_technique_id")
    alert_dict["mitre_technique_name"] = mitre_data.get("mitre_technique_name")
    alert_dict["mitre_tactic"] = mitre_data.get("mitre_tactic")

    return alert_dict


def enrich_alert_with_correlation_context(alert_dict):
    if alert_dict.get("alert_type") != "correlated_activity":
        return alert_dict

    message = str(alert_dict.get("message") or "")
    marker = "involving:"
    marker_index = message.lower().find(marker)

    correlated_alert_types = []
    if marker_index != -1:
        correlated_alert_types = [
            item.strip()
            for item in message[marker_index + len(marker):].split(",")
            if item.strip()
        ]

    alert_dict["is_correlation_alert"] = True
    alert_dict["correlated_alert_types"] = correlated_alert_types
    alert_dict["correlated_alert_count"] = len(correlated_alert_types)

    return alert_dict
