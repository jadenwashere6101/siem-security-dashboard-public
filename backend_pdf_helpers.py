from flask import Response
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas
from backend_reporting_helpers import format_display_value, format_pdf_timestamp


def get_pdf_severity_palette(severity):
    severity = (severity or "").lower()

    if severity == "critical":
        return {
            "background": HexColor("#7f1d1d"),
            "text": HexColor("#ffffff"),
            "border": HexColor("#b91c1c"),
        }

    if severity == "high":
        return {
            "background": HexColor("#991b1b"),
            "text": HexColor("#ffffff"),
            "border": HexColor("#dc2626"),
        }

    if severity == "medium":
        return {
            "background": HexColor("#fef3c7"),
            "text": HexColor("#92400e"),
            "border": HexColor("#f59e0b"),
        }

    return {
        "background": HexColor("#ecfccb"),
        "text": HexColor("#166534"),
        "border": HexColor("#65a30d"),
    }


def start_pdf_page(pdf, generated_at, scope):
    page_width, page_height = letter
    left_margin = 48
    top_y = page_height - 48

    pdf.setFillColor(colors.white)
    pdf.rect(0, 0, page_width, page_height, fill=1, stroke=0)

    pdf.setFillColor(HexColor("#0f172a"))
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(left_margin, top_y, "SIEM")

    pdf.setFont("Helvetica-Bold", 22)
    pdf.drawString(left_margin, top_y - 24, "INCIDENT REPORT")

    pdf.setFillColor(HexColor("#475569"))
    pdf.setFont("Helvetica", 10)
    pdf.drawString(left_margin, top_y - 42, format_pdf_timestamp(generated_at))

    pdf.setStrokeColor(HexColor("#cbd5e1"))
    pdf.setLineWidth(1)
    pdf.line(left_margin, top_y - 54, page_width - left_margin, top_y - 54)

    pdf.setFillColor(HexColor("#334155"))
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(left_margin, top_y - 72, "REPORT SCOPE")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(left_margin, top_y - 88, scope)

    return top_y - 112


def ensure_pdf_space(pdf, current_y, needed_height, generated_at, scope):
    if current_y - needed_height >= 50:
        return current_y

    pdf.showPage()
    return start_pdf_page(pdf, generated_at, scope)


def draw_pdf_wrapped_text(pdf, text, x, y, width, font_name="Helvetica", font_size=10, color=HexColor("#0f172a"), line_gap=4):
    lines = simpleSplit(text or "", font_name, font_size, width) or [""]
    pdf.setFont(font_name, font_size)
    pdf.setFillColor(color)

    current_y = y
    for line in lines:
        pdf.drawString(x, current_y, line)
        current_y -= font_size + line_gap

    return current_y


def draw_pdf_section_heading(pdf, heading, y):
    pdf.setFillColor(HexColor("#0f172a"))
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(48, y, heading)
    pdf.setStrokeColor(HexColor("#e2e8f0"))
    pdf.setLineWidth(1)
    pdf.line(48, y - 6, 564, y - 6)
    return y - 22


def draw_pdf_key_value_rows(pdf, rows, y, generated_at, scope):
    left_x = 48
    value_x = 196
    current_y = y

    for label, value in rows:
        current_y = ensure_pdf_space(pdf, current_y, 22, generated_at, scope)
        pdf.setFillColor(HexColor("#475569"))
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(left_x, current_y, label.upper())
        current_y = draw_pdf_wrapped_text(
            pdf,
            str(value),
            value_x,
            current_y,
            352,
            font_name="Helvetica",
            font_size=10,
            color=HexColor("#0f172a"),
            line_gap=3,
        )
        current_y -= 4

    return current_y


def draw_pdf_severity_badge(pdf, severity, x, y):
    palette = get_pdf_severity_palette(severity)
    label = (severity or "unknown").upper()
    width = max(60, len(label) * 7 + 18)
    height = 18

    pdf.setFillColor(palette["background"])
    pdf.setStrokeColor(palette["border"])
    pdf.roundRect(x, y - height + 4, width, height, 8, fill=1, stroke=1)
    pdf.setFillColor(palette["text"])
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(x + 9, y - 8, label)


def draw_pdf_response_logs(pdf, response_logs, y, generated_at, scope):
    current_y = draw_pdf_section_heading(pdf, "Response Log", y)

    if not response_logs:
        return draw_pdf_wrapped_text(
            pdf,
            "No response actions recorded.",
            48,
            current_y,
            516,
            color=HexColor("#475569"),
        ) - 8

    for log in response_logs:
        current_y = ensure_pdf_space(pdf, current_y, 56, generated_at, scope)
        action = (log[0] or "unknown").replace("_", " ").title()
        action = format_display_value(log[0] or "unknown")
        log_status = format_display_value(log[1] or "unknown")
        details = log[2] or "n/a"
        executed_at = format_pdf_timestamp(log[3])

        pdf.setStrokeColor(HexColor("#e2e8f0"))
        pdf.setFillColor(HexColor("#f8fafc"))
        pdf.roundRect(48, current_y - 42, 516, 38, 8, fill=1, stroke=1)

        pdf.setFillColor(HexColor("#0f172a"))
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(58, current_y - 14, action)
        pdf.setFont("Helvetica", 9)
        pdf.setFillColor(HexColor("#475569"))
        pdf.drawString(58, current_y - 28, f"{executed_at} · {log_status}")

        details_lines = simpleSplit(f"Details: {details}", "Helvetica", 9, 320)
        detail_y = current_y - 14
        for line in details_lines[:2]:
            pdf.drawString(240, detail_y, line)
            detail_y -= 12

        current_y -= 52

    return current_y


def draw_pdf_mitre_section(pdf, alert_data, y, generated_at, scope):
    technique_id = alert_data.get("mitre_technique_id")
    technique_name = alert_data.get("mitre_technique_name")
    tactic = alert_data.get("mitre_tactic")

    if not technique_id and not technique_name and not tactic:
        return y

    current_y = draw_pdf_section_heading(pdf, "MITRE ATT&CK", y)

    current_y = draw_pdf_key_value_rows(
        pdf,
        [
            ("Technique ID", technique_id or "N/A"),
            ("Technique Name", technique_name or "Unknown Technique"),
            ("Tactic", tactic or "N/A"),
        ],
        current_y,
        generated_at,
        scope,
    )

    return current_y - 14


def draw_pdf_next_steps(pdf, steps, y, generated_at, scope):
    current_y = draw_pdf_section_heading(pdf, "Recommended Next Steps", y)

    for step in steps:
        wrapped_lines = simpleSplit(f"• {step}", "Helvetica", 10, 500)
        current_y = ensure_pdf_space(pdf, current_y, max(22, len(wrapped_lines) * 16), generated_at, scope)
        for line in wrapped_lines:
            pdf.setFont("Helvetica", 10)
            pdf.setFillColor(HexColor("#0f172a"))
            pdf.drawString(56, current_y, line)
            current_y -= 14
        current_y -= 4

    return current_y


def draw_pdf_summary_grid(pdf, severity_counts, total_alerts, y):
    metrics = [
        ("Total", total_alerts),
        ("Critical", severity_counts["critical"]),
        ("High", severity_counts["high"]),
        ("Medium", severity_counts["medium"]),
        ("Low", severity_counts["low"]),
    ]
    box_width = 96
    box_height = 52
    gap = 8
    start_x = 48

    pdf.setFont("Helvetica-Bold", 12)
    pdf.setFillColor(HexColor("#0f172a"))
    pdf.drawString(start_x, y, "Summary")

    current_x = start_x
    box_y = y - 18
    for label, value in metrics:
        pdf.setFillColor(HexColor("#f8fafc"))
        pdf.setStrokeColor(HexColor("#dbe4ee"))
        pdf.roundRect(current_x, box_y - box_height, box_width, box_height, 8, fill=1, stroke=1)
        pdf.setFillColor(HexColor("#64748b"))
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(current_x + 10, box_y - 16, label.upper())
        pdf.setFillColor(HexColor("#0f172a"))
        pdf.setFont("Helvetica-Bold", 16)
        pdf.drawString(current_x + 10, box_y - 36, str(value))
        current_x += box_width + gap

    return box_y - box_height - 18


def draw_pdf_alert_card(pdf, alert_title, alert_data, response_logs, y, generated_at, scope):
    current_y = ensure_pdf_space(pdf, y, 220, generated_at, scope)

    pdf.setFillColor(HexColor("#ffffff"))
    pdf.setStrokeColor(HexColor("#dbe4ee"))
    pdf.roundRect(42, current_y - 164, 528, 156, 12, fill=1, stroke=1)

    pdf.setFillColor(HexColor("#0f172a"))
    pdf.setFont("Helvetica-Bold", 15)
    title_lines = simpleSplit(alert_title, "Helvetica-Bold", 15, 360)
    title_y = current_y - 24
    for line in title_lines[:2]:
        pdf.drawString(56, title_y, line)
        title_y -= 18

    draw_pdf_severity_badge(pdf, alert_data["severity"], 450, current_y - 14)

    field_y = current_y - 62
    current_y = draw_pdf_key_value_rows(
        pdf,
        [
            ("Source IP", alert_data["source_ip"]),
            ("Status", format_display_value(alert_data["status"])),
            ("Created", format_pdf_timestamp(alert_data["timestamp"])),
            ("Message", alert_data["message"]),
        ],
        field_y,
        generated_at,
        scope,
    )

    current_y -= 4
    current_y = draw_pdf_mitre_section(pdf, alert_data, current_y, generated_at, scope)
    current_y -= 4
    current_y = draw_pdf_section_heading(pdf, "Response Summary", current_y)
    current_y = draw_pdf_key_value_rows(
        pdf,
        [
            ("Recommended Action", format_display_value(alert_data["response_action"])),
            ("Current Response Status", format_display_value(alert_data["response_status"])),
            ("Location", alert_data["location"]),
        ],
        current_y,
        generated_at,
        scope,
    )
    current_y -= 6
    current_y = draw_pdf_response_logs(pdf, response_logs, current_y, generated_at, scope)
    current_y -= 6
    current_y = draw_pdf_next_steps(pdf, alert_data["recommended_steps"], current_y, generated_at, scope)

    return current_y - 8


def build_pdf_report_response(filename, generated_at, scope, alert_sections, severity_counts=None, summary_note=None):
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    pdf.setTitle(filename)
    current_y = start_pdf_page(pdf, generated_at, scope)

    if severity_counts is not None:
        current_y = draw_pdf_summary_grid(
            pdf,
            severity_counts,
            sum(severity_counts.values()),
            current_y,
        )

    if summary_note:
        current_y = ensure_pdf_space(pdf, current_y, 42, generated_at, scope)
        current_y = draw_pdf_wrapped_text(
            pdf,
            summary_note,
            48,
            current_y,
            516,
            font_name="Helvetica",
            font_size=10,
            color=HexColor("#334155"),
        ) - 6

    for section in alert_sections:
        current_y = draw_pdf_alert_card(
            pdf,
            section["title"],
            section["alert_data"],
            section["response_logs"],
            current_y,
            generated_at,
            scope,
        )

    pdf.save()
    pdf_bytes = buffer.getvalue()
    buffer.close()

    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
