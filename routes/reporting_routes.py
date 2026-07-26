import csv
from datetime import datetime, timezone
from io import StringIO

from flask import Blueprint, Response, current_app, jsonify, request
from flask_login import current_user, login_required

from core.audit_helpers import log_audit_event
from core.auth import analyst_or_super_admin_required
from core.db import get_db_connection
from core.pfsense_operational_baseline import normalize_operational_scope
from helpers.pdf_helpers import build_pdf_report_response
from helpers.query_helpers import (
    build_alert_filter_scope_label,
    fetch_alert_csv_rows,
    fetch_alert_rows,
    fetch_response_logs_by_alert_id,
    normalize_ip_filter_value,
    normalize_rule_id_filter,
    validate_rule_id_filter,
)
from helpers.reporting_helpers import (
    build_alert_report_sections,
    build_report_header,
    format_csv_timestamp,
    normalize_alert_report_data,
)

reporting_bp = Blueprint("reporting", __name__)


def _parse_filtered_export_args():
    try:
        exact_source_ip = normalize_ip_filter_value(request.args.get("exact_source_ip"))
        exact_target_ip = normalize_ip_filter_value(request.args.get("exact_target_ip"))
        rule_id = normalize_rule_id_filter(request.args.get("rule_id"))
        operational_scope = normalize_operational_scope(request.args.get("operational_scope"))
    except ValueError as exc:
        return None, str(exc)

    alert_id = request.args.get("alert_id")
    if alert_id not in (None, ""):
        try:
            alert_id = int(alert_id)
        except ValueError:
            return None, "invalid alert_id"
        if alert_id < 0:
            return None, "invalid alert_id"
    else:
        alert_id = None

    return {
        "search": request.args.get("search", ""),
        "severity": request.args.get("severity", ""),
        "status": request.args.get("status", ""),
        "source": request.args.get("source", ""),
        "operational_scope": operational_scope,
        "exact_source_ip": exact_source_ip,
        "exact_target_ip": exact_target_ip,
        "alert_id": alert_id,
        "rule_id": rule_id,
    }, None


def _validate_filtered_export_args(cur, filters):
    rule_error = validate_rule_id_filter(cur, filters.get("rule_id"))
    if rule_error:
        return rule_error
    return None


@reporting_bp.route("/alerts/<int:alert_id>/report", methods=["GET"])
@login_required
def export_alert_report(alert_id):
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        alert_rows = fetch_alert_rows(cur, {"search": "", "severity": "", "status": ""})
        alert_row = next((row for row in alert_rows if row[0] == alert_id), None)

        if not alert_row:
            return jsonify({"error": "Alert not found"}), 404

        response_logs_map = fetch_response_logs_by_alert_id(cur, [alert_id])
        alert_data = normalize_alert_report_data(alert_row)
        generated_at = datetime.now(timezone.utc).isoformat()

        lines = build_report_header(generated_at, f"Single Alert (Alert ID {alert_id})")
        lines.extend(build_alert_report_sections(alert_data, response_logs_map.get(alert_id, [])))

        report_body = "\n".join(lines) + "\n"
        filename = f"incident-report-alert-{alert_id}.txt"

        log_audit_event(
            "DOWNLOAD_REPORT",
            actor_username=current_user.id,
            actor_role=current_user.role,
            target_alert_id=alert_id,
            http_method=request.method,
            request_path=request.path,
            source_ip=request.remote_addr,
            details={"report_type": "txt", "scope": "single_alert"},
        )

        return Response(
            report_body,
            mimetype="text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    except Exception as e:
        current_app.logger.error("Error in export_alert_report: %s", e)
        return jsonify({"error": "Internal server error"}), 500

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@reporting_bp.route("/alerts/<int:alert_id>/report/pdf", methods=["GET"])
@login_required
def export_alert_report_pdf(alert_id):
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        alert_rows = fetch_alert_rows(cur, {"search": "", "severity": "", "status": ""})
        alert_row = next((row for row in alert_rows if row[0] == alert_id), None)

        if not alert_row:
            return jsonify({"error": "Alert not found"}), 404

        response_logs_map = fetch_response_logs_by_alert_id(cur, [alert_id])
        alert_data = normalize_alert_report_data(alert_row)
        generated_at = datetime.now(timezone.utc).isoformat()
        scope = f"Single Alert (Alert ID {alert_id})"

        log_audit_event(
            "DOWNLOAD_REPORT",
            actor_username=current_user.id,
            actor_role=current_user.role,
            target_alert_id=alert_id,
            http_method=request.method,
            request_path=request.path,
            source_ip=request.remote_addr,
            details={"report_type": "pdf", "scope": "single_alert"},
        )

        return build_pdf_report_response(
            f"incident-report-alert-{alert_id}.pdf",
            generated_at,
            scope,
            [
                {
                    "title": f"{alert_data['alert_type'].replace('_', ' ').title()} · Alert {alert_id}",
                    "alert_data": alert_data,
                    "response_logs": response_logs_map.get(alert_id, []),
                }
            ],
        )

    except Exception as e:
        current_app.logger.error("Error in export_alert_report_pdf: %s", e)
        return jsonify({"error": "Internal server error"}), 500

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@reporting_bp.route("/alerts/report", methods=["GET"])
@login_required
def export_multi_alert_report():
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        filters, filter_error = _parse_filtered_export_args()
        if filter_error:
            return jsonify({"error": filter_error}), 400
        filter_error = _validate_filtered_export_args(cur, filters)
        if filter_error:
            return jsonify({"error": filter_error}), 400
        alert_rows = fetch_alert_rows(cur, filters)
        alert_ids = [row[0] for row in alert_rows]
        response_logs_map = fetch_response_logs_by_alert_id(cur, alert_ids)
        generated_at = datetime.now(timezone.utc).isoformat()

        severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for row in alert_rows:
            severity = (row[2] or "").lower()
            if severity in severity_counts:
                severity_counts[severity] += 1

        scope_text = build_alert_filter_scope_label(filters)

        lines = build_report_header(generated_at, scope_text)
        lines.extend([
            "SUMMARY",
            "=======",
            f"Total Alerts: {len(alert_rows)}",
            f"Critical Alerts: {severity_counts['critical']}",
            f"High Alerts: {severity_counts['high']}",
            f"Medium Alerts: {severity_counts['medium']}",
            f"Low Alerts: {severity_counts['low']}",
            "",
        ])

        if alert_rows:
            lines.append("The report includes all alerts matching the current dashboard filters at the time of export.")
        else:
            lines.append("No alerts matched the current dashboard filters at the time of export.")

        for index, row in enumerate(alert_rows, start=1):
            alert_data = normalize_alert_report_data(row)
            lines.extend([
                "",
                f"ALERT {index}",
                "-------",
            ])
            lines.extend(build_alert_report_sections(alert_data, response_logs_map.get(row[0], [])))

        report_body = "\n".join(lines) + "\n"
        filename = "incident-report-alerts.txt"

        log_audit_event(
            "DOWNLOAD_REPORT",
            actor_username=current_user.id,
            actor_role=current_user.role,
            http_method=request.method,
            request_path=request.path,
            source_ip=request.remote_addr,
            details={"report_type": "txt", "scope": "filtered_alerts"},
        )

        return Response(
            report_body,
            mimetype="text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    except Exception as e:
        current_app.logger.error("Error in export_multi_alert_report: %s", e)
        return jsonify({"error": "Internal server error"}), 500

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@reporting_bp.route("/alerts/export/csv", methods=["GET"])
@login_required
@analyst_or_super_admin_required
def export_alerts_csv():
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        filters, filter_error = _parse_filtered_export_args()
        if filter_error:
            return jsonify({"error": filter_error}), 400
        filter_error = _validate_filtered_export_args(cur, filters)
        if filter_error:
            return jsonify({"error": filter_error}), 400
        alert_rows = fetch_alert_csv_rows(cur, filters)

        string_io = StringIO()
        writer = csv.writer(string_io)
        writer.writerow(["id", "alert_type", "severity", "source_ip", "status", "created_at", "environment", "message"])

        for row in alert_rows:
            writer.writerow([
                row[0],
                row[1],
                row[2],
                str(row[3]) if row[3] is not None else "",
                row[4],
                format_csv_timestamp(row[5]),
                row[7] or "",
                row[6],
            ])

        csv_body = string_io.getvalue()
        string_io.close()
        filename = f"alerts-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.csv"

        return Response(
            csv_body,
            mimetype="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        current_app.logger.error("Error in export_alerts_csv: %s", e)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@reporting_bp.route("/alerts/report/pdf", methods=["GET"])
@login_required
def export_multi_alert_report_pdf():
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        filters, filter_error = _parse_filtered_export_args()
        if filter_error:
            return jsonify({"error": filter_error}), 400
        filter_error = _validate_filtered_export_args(cur, filters)
        if filter_error:
            return jsonify({"error": filter_error}), 400
        alert_rows = fetch_alert_rows(cur, filters)
        alert_ids = [row[0] for row in alert_rows]
        response_logs_map = fetch_response_logs_by_alert_id(cur, alert_ids)
        generated_at = datetime.now(timezone.utc).isoformat()

        severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for row in alert_rows:
            severity = (row[2] or "").lower()
            if severity in severity_counts:
                severity_counts[severity] += 1

        scope_text = build_alert_filter_scope_label(filters)

        summary_note = (
            "The report includes all alerts matching the current dashboard filters at the time of export."
            if alert_rows
            else "No alerts matched the current dashboard filters at the time of export."
        )
        alert_sections = []
        for index, row in enumerate(alert_rows, start=1):
            alert_data = normalize_alert_report_data(row)
            alert_sections.append(
                {
                    "title": f"Alert {index} · {alert_data['alert_type'].replace('_', ' ').title()}",
                    "alert_data": alert_data,
                    "response_logs": response_logs_map.get(row[0], []),
                }
            )

        log_audit_event(
            "DOWNLOAD_REPORT",
            actor_username=current_user.id,
            actor_role=current_user.role,
            http_method=request.method,
            request_path=request.path,
            source_ip=request.remote_addr,
            details={"report_type": "pdf", "scope": "filtered_alerts"},
        )

        return build_pdf_report_response(
            "incident-report-alerts.pdf",
            generated_at,
            scope_text,
            alert_sections,
            severity_counts=severity_counts,
            summary_note=summary_note,
        )

    except Exception as e:
        current_app.logger.error("Error in export_multi_alert_report_pdf: %s", e)
        return jsonify({"error": "Internal server error"}), 500

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
