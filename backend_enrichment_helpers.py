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
