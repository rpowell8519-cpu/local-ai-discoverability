from __future__ import annotations

import io
from collections.abc import Mapping, Sequence
from typing import Any

import reportlab
from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

from src.poc_audit_payload import validate_poc_audit_payload


PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN = 42
CONTENT_WIDTH = PAGE_WIDTH - (2 * MARGIN)
MIN_FONT_SIZE = 8

NAVY = HexColor("#15233B")
BLUE = HexColor("#2D5BFF")
TEAL = HexColor("#16A6A1")
GOLD = HexColor("#E7A83E")
INK = HexColor("#1F2937")
MID = HexColor("#5B6472")
PALE = HexColor("#F3F6FA")
LINE = HexColor("#D9E0E8")
WHITE = colors.white
RED = HexColor("#C54848")

FONT = "PocVera"
FONT_BOLD = "PocVeraBold"


class PdfRenderError(ValueError):
    """Raised when a frozen payload cannot produce the v1 report."""


def _register_fonts() -> None:
    if FONT in pdfmetrics.getRegisteredFontNames():
        return
    font_directory = (
        __import__("pathlib").Path(reportlab.__file__).parent / "fonts"
    )
    pdfmetrics.registerFont(
        TTFont(FONT, str(font_directory / "Vera.ttf"))
    )
    pdfmetrics.registerFont(
        TTFont(FONT_BOLD, str(font_directory / "VeraBd.ttf"))
    )


def _text(value: Any) -> str:
    return str(value if value is not None else "").strip()


def _number(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise PdfRenderError(f"Expected an integer, received {value!r}") from exc


def _require(mapping: Mapping[str, Any], key: str, path: str) -> Any:
    value = mapping.get(key)
    if value is None or value == "" or value == []:
        raise PdfRenderError(f"Missing report field: {path}.{key}")
    return value


def _validate_report_contract(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    validate_poc_audit_payload(payload)
    report = payload.get("report")
    if not isinstance(report, Mapping):
        raise PdfRenderError("The payload has no frozen report section")

    required_sections = (
        "executive_summary",
        "visibility",
        "recommendation_market",
        "provider_comparison",
        "diagnostic_cohort",
        "evidence_matrix",
        "strengths",
        "priority_gaps",
        "priority_actions",
        "roadmap",
        "methodology",
    )
    for section in required_sections:
        _require(report, section, "report")

    visibility = report["visibility"]
    for key in (
        "responses_complete",
        "responses_expected",
        "mentions",
        "recommendations",
        "business_sor_pct",
        "providers",
        "intents",
        "verification_statement",
    ):
        _require(visibility, key, "report.visibility")

    if len(report["diagnostic_cohort"]) != 3:
        raise PdfRenderError("Exactly three diagnostic cohort members are required")
    if not 3 <= len(report["priority_actions"]) <= 5:
        raise PdfRenderError("The report requires three to five priority actions")
    if len(report["evidence_matrix"].get("dimensions", [])) not in range(6, 9):
        raise PdfRenderError("The evidence matrix requires six to eight dimensions")

    _validate_cross_evidence(payload, report)

    return report


def _validate_cross_evidence(
    payload: Mapping[str, Any], report: Mapping[str, Any]
) -> None:
    """Reject report-facing claims that do not reconcile to frozen evidence."""

    errors: list[str] = []
    baseline = payload["baseline_validation"]
    responses = baseline["responses"]
    visibility = report["visibility"]
    if visibility["responses_expected"] != baseline["expected_responses"]:
        errors.append("visibility expected-response count")
    if visibility["responses_complete"] != baseline["complete_raw_responses"]:
        errors.append("visibility complete-response count")
    if visibility["mentions"] != sum(
        bool(item["parser_reconciliation"].get("persisted_target_mentioned"))
        for item in responses
    ):
        errors.append("visibility target-mention count")
    if visibility["recommendations"] != sum(
        bool(item["parser_reconciliation"].get("persisted_target_recommended"))
        for item in responses
    ):
        errors.append("visibility target-recommendation count")

    methodology = report["methodology"]
    method_source = payload["methodology"]
    if methodology["prompt_count"] != method_source["prompt_count"]:
        errors.append("methodology prompt count")
    if methodology["repetitions"] != method_source["repetitions"]:
        errors.append("methodology repetition count")
    if methodology["expected_responses"] != len(responses):
        errors.append("methodology response count")
    if len(method_source.get("queries", [])) != (
        methodology["prompt_count"] * methodology["repetitions"]
    ):
        errors.append("frozen query count")

    frozen_market = payload["recommendation_market"]
    slots = frozen_market["slot_evidence"]
    business_slots = sum(item["slot_disposition"] == "business" for item in slots)
    non_business_slots = sum(item["slot_disposition"] == "non_business" for item in slots)
    market_report = report["recommendation_market"]
    expected_market = (len(slots), business_slots, non_business_slots)
    reported_market = (
        market_report["original_slots"], market_report["business_slots"],
        market_report["excluded_slots"],
    )
    if reported_market != expected_market:
        errors.append("recommendation-market slot counts")
    frozen_rows = {
        str(item.get("google_place_id") or item["business_name"]): item
        for item in frozen_market["canonical_businesses"]
    }
    for item in market_report["businesses"]:
        key = str(item.get("google_place_id") or item["business_name"])
        source = frozen_rows.get(key)
        if not source or int(item["recommendations"]) != int(source["recommendations"]):
            errors.append(f"market row {key}")
            continue
        if abs(float(item["business_sor_pct"]) - float(source["share_of_recommendation"]) * 100) > 0.0001:
            errors.append(f"market SOR {key}")

    for member in report["diagnostic_cohort"]:
        key = str(member["google_place_id"])
        source = frozen_rows.get(key)
        if not source:
            errors.append(f"cohort member {key}")
        elif int(member["recommendations"]) != int(source["recommendations"]):
            errors.append(f"cohort recommendations {key}")

    audits = payload["website_evidence"].get("audits", [])
    if len(audits) != 4 or not all(item.get("pages") for item in audits):
        errors.append("website audit/page evidence")
    review_sets = payload["review_evidence"].get("review_sets", [])
    if len(review_sets) != 4:
        errors.append("review evidence sets")
    for item in review_sets:
        if item["status"] == "complete" and item["record_count"] != len(item["records"]):
            errors.append(f"review set {item['business_name']}")
        if item["status"] == "exception" and not item.get("exception"):
            errors.append(f"review exception {item['business_name']}")

    decisions = payload["diagnostic"].get("analyst_decisions", {})
    if not decisions.get("version") or decisions.get("status") != "operator_approved":
        errors.append("approved analyst decisions")
    full_ids = {item["action_id"] for item in report.get("full_action_plan", [])}
    priority_ids = {item["action_id"] for item in report["priority_actions"]}
    if not priority_ids or not priority_ids.issubset(full_ids):
        errors.append("priority/full action-plan relationship")
    registry = payload["diagnostic"].get("evidence_registry", {})
    referenced = {
        ref
        for section in ("strengths", "gaps", "actions", "provider_hypotheses")
        for item in decisions.get(section, [])
        for ref in item.get("evidence_refs", [])
    }
    missing_refs = sorted(referenced - set(registry))
    if missing_refs:
        errors.append("unresolved evidence references: " + ", ".join(missing_refs))
    audit_ids = {str(item.get("id")) for item in audits}
    review_ids = {str(item.get("google_place_id")) for item in review_sets}
    for ref, descriptor in registry.items():
        if ref.startswith("website:") and str(descriptor.get("source")) not in audit_ids:
            errors.append(f"website evidence reference {ref}")
        if ref.startswith("reviews:") and descriptor.get("google_place_id") and str(descriptor["google_place_id"]) not in review_ids:
            errors.append(f"review evidence reference {ref}")
        if ref.startswith("market:") and descriptor.get("google_place_id") and str(descriptor["google_place_id"]) not in frozen_rows:
            errors.append(f"market evidence reference {ref}")
    matrix = report["evidence_matrix"]
    if set(matrix.get("businesses", [])) != set(matrix.get("business_place_ids", {})):
        errors.append("evidence-matrix business identity mapping")
    matrix_refs = {
        ref for item in matrix.get("dimensions", []) for ref in item.get("evidence_refs", [])
    }
    if matrix_refs - set(registry):
        errors.append("evidence-matrix source references")

    if errors:
        raise PdfRenderError(
            "Report evidence does not reconcile: " + ", ".join(errors)
        )


def _split_long_token(token: str, font: str, size: float, width: float) -> list[str]:
    if pdfmetrics.stringWidth(token, font, size) <= width:
        return [token]
    chunks: list[str] = []
    current = ""
    for character in token:
        candidate = current + character
        if current and pdfmetrics.stringWidth(candidate, font, size) > width:
            chunks.append(current)
            current = character
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def _wrap(text_value: Any, font: str, size: float, width: float) -> list[str]:
    paragraphs = _text(text_value).splitlines() or [""]
    output: list[str] = []
    for paragraph in paragraphs:
        words: list[str] = []
        for token in paragraph.split():
            words.extend(_split_long_token(token, font, size, width))
        if not words:
            output.append("")
            continue
        line = words[0]
        for word in words[1:]:
            candidate = f"{line} {word}"
            if pdfmetrics.stringWidth(candidate, font, size) <= width:
                line = candidate
            else:
                output.append(line)
                line = word
        output.append(line)
    return output


def _paragraph(
    canvas: Canvas,
    value: Any,
    x: float,
    y: float,
    width: float,
    *,
    font: str = FONT,
    size: float = 9.5,
    color=INK,
    leading: float | None = None,
    max_lines: int | None = None,
) -> float:
    if size < MIN_FONT_SIZE:
        raise PdfRenderError("Report text cannot be smaller than 8pt")
    lines = _wrap(value, font, size, width)
    if max_lines is not None and len(lines) > max_lines:
        raise PdfRenderError(f"Text does not fit safely: {_text(value)[:80]}")
    line_height = leading or size * 1.35
    canvas.setFont(font, size)
    canvas.setFillColor(color)
    text_object = canvas.beginText(x, y)
    text_object.setLeading(line_height)
    for line in lines:
        text_object.textLine(line)
    canvas.drawText(text_object)
    return y - (len(lines) * line_height)


def _label(canvas: Canvas, label: str, x: float, y: float, kind: str) -> None:
    palette = {
        "measured": (BLUE, WHITE),
        "observed": (TEAL, WHITE),
        "action": (GOLD, NAVY),
    }
    background, foreground = palette[kind]
    width = pdfmetrics.stringWidth(label.upper(), FONT_BOLD, 8) + 16
    canvas.setFillColor(background)
    canvas.roundRect(x, y - 11, width, 16, 5, fill=1, stroke=0)
    canvas.setFont(FONT_BOLD, 8)
    canvas.setFillColor(foreground)
    canvas.drawString(x + 8, y - 7, label.upper())


def _page_title(canvas: Canvas, title: str, subtitle: str | None = None) -> float:
    y = _paragraph(
        canvas,
        title,
        MARGIN,
        PAGE_HEIGHT - 72,
        CONTENT_WIDTH,
        font=FONT_BOLD,
        size=23,
        color=NAVY,
        leading=28,
        max_lines=2,
    )
    y -= 4
    if subtitle:
        y = _paragraph(canvas, subtitle, MARGIN, y, CONTENT_WIDTH, size=9, color=MID)
    canvas.setStrokeColor(LINE)
    canvas.line(MARGIN, y - 5, PAGE_WIDTH - MARGIN, y - 5)
    return y - 24


def _footer(canvas: Canvas, page: int, client_name: str, audit_date: str) -> None:
    canvas.setStrokeColor(LINE)
    canvas.line(MARGIN, 30, PAGE_WIDTH - MARGIN, 30)
    canvas.setFont(FONT, 8)
    canvas.setFillColor(MID)
    canvas.drawString(MARGIN, 17, f"{client_name} | POC AI visibility audit | {audit_date}")
    canvas.drawRightString(PAGE_WIDTH - MARGIN, 17, f"{page} / 12")


def _new_page(canvas: Canvas, page: int, client_name: str, audit_date: str) -> None:
    if page > 1:
        _footer(canvas, page - 1, client_name, audit_date)
    canvas.showPage()


def _card(
    canvas: Canvas,
    x: float,
    y: float,
    width: float,
    height: float,
    *,
    fill=WHITE,
    border=LINE,
) -> None:
    canvas.setFillColor(fill)
    canvas.setStrokeColor(border)
    canvas.roundRect(x, y - height, width, height, 8, fill=1, stroke=1)


def _evidence_labels(refs: Sequence[str]) -> str:
    labels = []
    for ref in refs:
        prefix = ref.split(":", 1)[0]
        label = {
            "website": "frozen website audit",
            "reviews": "frozen review evidence",
            "diagnostic": "diagnostic comparison",
            "market": "recommendation-market measurement",
            "gap": "approved gap analysis",
        }.get(prefix, "frozen audit evidence")
        if label not in labels:
            labels.append(label)
    return ", ".join(labels)


def _draw_cover(canvas: Canvas, payload: Mapping[str, Any], report: Mapping[str, Any]) -> None:
    audit = payload["audit"]
    client = _text(audit["target_business_name"])
    canvas.setFillColor(NAVY)
    canvas.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, fill=1, stroke=0)
    canvas.setFillColor(BLUE)
    canvas.rect(0, PAGE_HEIGHT - 20, PAGE_WIDTH, 20, fill=1, stroke=0)
    canvas.setFont(FONT_BOLD, 11)
    canvas.setFillColor(TEAL)
    canvas.drawString(MARGIN, PAGE_HEIGHT - 98, "POC AUDIT V1")
    y = _paragraph(
        canvas,
        "AI Visibility & Discoverability Audit",
        MARGIN,
        PAGE_HEIGHT - 150,
        CONTENT_WIDTH - 20,
        font=FONT_BOLD,
        size=31,
        color=WHITE,
        leading=37,
        max_lines=2,
    )
    y = _paragraph(canvas, client, MARGIN, y - 30, CONTENT_WIDTH, font=FONT_BOLD, size=22, color=WHITE)
    context = report["client_context"]
    canvas.setFont(FONT, 11)
    canvas.setFillColor(HexColor("#D7E1F0"))
    canvas.drawString(
        MARGIN,
        y - 18,
        f"{_text(_require(context, 'category', 'report.client_context'))} | "
        f"{_text(_require(context, 'location', 'report.client_context'))}",
    )
    _card(canvas, MARGIN, 165, CONTENT_WIDTH, 112, fill=HexColor("#20304B"), border=HexColor("#334663"))
    _label(canvas, "Measured result", MARGIN + 18, 145, "measured")
    canvas.setFont(FONT_BOLD, 28)
    canvas.setFillColor(WHITE)
    complete = report["visibility"]["responses_complete"]
    canvas.drawString(MARGIN + 18, 105, f"{complete} model responses")
    canvas.setFont(FONT, 10)
    canvas.setFillColor(HexColor("#D7E1F0"))
    canvas.drawString(MARGIN + 18, 82, "OpenAI | Claude | Gemini | Independently verified")
    canvas.setFont(FONT, 9)
    canvas.setFillColor(HexColor("#AFC0D6"))
    canvas.drawString(MARGIN, 38, f"Audit date: {_text(audit['audit_date'])}")


def _draw_executive(canvas: Canvas, report: Mapping[str, Any], client: str) -> None:
    summary = report["executive_summary"]
    y = _page_title(canvas, "The finding in one minute")
    _label(canvas, "Measured result", MARGIN, y, "measured")
    _card(canvas, MARGIN, y - 20, 172, 118, fill=NAVY, border=NAVY)
    canvas.setFillColor(WHITE)
    canvas.setFont(FONT_BOLD, 40)
    visibility = report["visibility"]
    observed = max(int(visibility["mentions"]), int(visibility["recommendations"]))
    canvas.drawString(MARGIN + 16, y - 70, f"{observed} of {visibility['responses_complete']}")
    _paragraph(canvas, f"responses mentioned or recommended {client}", MARGIN + 16, y - 92, 140, size=8.5, color=WHITE, max_lines=3)
    _card(canvas, MARGIN + 188, y - 20, CONTENT_WIDTH - 188, 118, fill=PALE)
    _paragraph(canvas, summary["headline"], MARGIN + 204, y - 46, CONTENT_WIDTH - 220, font=FONT_BOLD, size=14, color=NAVY, max_lines=3)
    _paragraph(canvas, summary["summary"], MARGIN + 204, y - 98, CONTENT_WIDTH - 220, size=8.5, color=MID, max_lines=4)
    y -= 160
    _label(canvas, "Observed evidence", MARGIN, y, "observed")
    strengths = summary["strengths"]
    card_width = (CONTENT_WIDTH - 24) / 3
    for index, strength in enumerate(strengths[:3]):
        x = MARGIN + index * (card_width + 12)
        _card(canvas, x, y - 20, card_width, 116)
        _paragraph(canvas, strength["title"], x + 12, y - 42, card_width - 24, font=FONT_BOLD, size=10, color=NAVY, max_lines=2)
        _paragraph(canvas, strength["body"], x + 12, y - 73, card_width - 24, size=8.2, color=MID, max_lines=4)
    y -= 160
    _label(canvas, "Recommended action", MARGIN, y, "action")
    _paragraph(canvas, summary["action_statement"], MARGIN, y - 27, CONTENT_WIDTH, font=FONT_BOLD, size=12, color=NAVY, max_lines=3)
    _paragraph(canvas, summary["non_causality"], MARGIN, y - 76, CONTENT_WIDTH, size=8.5, color=MID, max_lines=3)


def _draw_visibility(canvas: Canvas, report: Mapping[str, Any], client: str) -> None:
    data = report["visibility"]
    y = _page_title(canvas, f"{client}'s AI visibility baseline", "Measured across every provider, intent and repetition in the frozen benchmark.")
    _label(canvas, "Measured result", MARGIN, y, "measured")
    _card(canvas, MARGIN, y - 20, 190, 150, fill=NAVY, border=NAVY)
    canvas.setFont(FONT_BOLD, 50)
    canvas.setFillColor(WHITE)
    canvas.drawString(MARGIN + 18, y - 84, f"{float(data['business_sor_pct']):.2f}%")
    _paragraph(canvas, "Business Share of Recommendation", MARGIN + 18, y - 108, 154, size=9, color=WHITE, max_lines=2)
    _paragraph(canvas, f"{data['mentions']} mentions | {data['recommendations']} recommendations", MARGIN + 18, y - 143, 154, size=8, color=HexColor("#CAD6E7"), max_lines=2)
    x = MARGIN + 208
    provider_width = (CONTENT_WIDTH - 208) / 3
    for provider in data["providers"]:
        _card(canvas, x, y - 20, provider_width - 8, 150, fill=PALE)
        _paragraph(canvas, provider["name"], x + 10, y - 42, provider_width - 28, font=FONT_BOLD, size=9, color=NAVY, max_lines=2)
        _paragraph(canvas, f"{provider['complete']}/{provider['expected']} complete", x + 10, y - 79, provider_width - 28, size=8, color=MID, max_lines=2)
        canvas.setFont(FONT_BOLD, 18)
        canvas.setFillColor(BLUE)
        canvas.drawString(x + 10, y - 116, str(provider.get("recommendations", data["recommendations"])))
        canvas.setFont(FONT, 8)
        canvas.setFillColor(MID)
        canvas.drawString(x + 10, y - 133, "recommendations")
        x += provider_width
    y -= 205
    canvas.setFont(FONT_BOLD, 11)
    canvas.setFillColor(NAVY)
    canvas.drawString(MARGIN, y, "Eight tested consumer intents")
    y -= 22
    pill_width = (CONTENT_WIDTH - 12) / 2
    for index, intent in enumerate(data["intents"]):
        x = MARGIN + (index % 2) * (pill_width + 12)
        row_y = y - (index // 2) * 38
        _card(canvas, x, row_y, pill_width, 28, fill=WHITE)
        _paragraph(canvas, intent, x + 9, row_y - 10, pill_width - 54, size=8, color=INK, max_lines=1)
        canvas.setFont(FONT_BOLD, 8)
        canvas.setFillColor(MID)
        intent_result = data.get("intent_results", {}).get(intent, {})
        canvas.drawRightString(x + pill_width - 9, row_y - 17, _text(intent_result.get("display", "Measured")))
    y -= 182
    _card(canvas, MARGIN, y, CONTENT_WIDTH, 62, fill=PALE)
    _paragraph(canvas, data["verification_statement"], MARGIN + 14, y - 22, CONTENT_WIDTH - 28, font=FONT_BOLD, size=9, color=NAVY, max_lines=3)


def _draw_market(canvas: Canvas, report: Mapping[str, Any], client: str) -> None:
    data = report["recommendation_market"]
    y = _page_title(canvas, "Who AI recommends instead", "The full market is a measured result; the comparison cohort is selected separately.")
    _label(canvas, "Measured result", MARGIN, y, "measured")
    stats = [
        (data["original_slots"], "parsed slots"),
        (data["business_slots"], "valid business slots"),
        (data["excluded_slots"], "non-business slots excluded"),
    ]
    stat_width = (CONTENT_WIDTH - 20) / 3
    for index, (value, label) in enumerate(stats):
        x = MARGIN + index * (stat_width + 10)
        _card(canvas, x, y - 20, stat_width, 64, fill=PALE)
        canvas.setFont(FONT_BOLD, 18)
        canvas.setFillColor(NAVY)
        canvas.drawString(x + 12, y - 51, str(value))
        _paragraph(canvas, label, x + 52, y - 38, stat_width - 62, size=8, color=MID, max_lines=2)
    y -= 112
    businesses = data["businesses"][:8]
    max_sor = max(float(item["business_sor_pct"]) for item in businesses) or 1
    chart_x = MARGIN + 155
    chart_width = CONTENT_WIDTH - 205
    row_height = 39
    for index, item in enumerate(businesses):
        row_y = y - index * row_height
        name = item["business_name"]
        _paragraph(canvas, name, MARGIN, row_y, 142, size=8.2, color=INK, max_lines=2)
        bar_width = chart_width * float(item["business_sor_pct"]) / max_sor
        canvas.setFillColor(BLUE if index < 3 else TEAL)
        canvas.roundRect(chart_x, row_y - 12, bar_width, 13, 3, fill=1, stroke=0)
        canvas.setFont(FONT_BOLD, 8)
        canvas.setFillColor(NAVY)
        canvas.drawString(chart_x + bar_width + 7, row_y - 10, f"{float(item['business_sor_pct']):.2f}% | {item['recommendations']}")
    target_y = y - len(businesses) * row_height - 7
    canvas.setStrokeColor(RED)
    canvas.setLineWidth(2)
    canvas.line(chart_x, target_y, chart_x + chart_width, target_y)
    canvas.setFont(FONT_BOLD, 9)
    canvas.setFillColor(RED)
    canvas.drawString(MARGIN, target_y - 3, client)
    canvas.drawRightString(PAGE_WIDTH - MARGIN, target_y - 3, f"{float(report['visibility']['business_sor_pct']):.2f}% | {report['visibility']['recommendations']}")
    _paragraph(canvas, data["market_note"], MARGIN, target_y - 40, CONTENT_WIDTH, size=8.5, color=MID, max_lines=3)


def _draw_provider_comparison(canvas: Canvas, report: Mapping[str, Any]) -> None:
    rows = report["provider_comparison"]
    y = _page_title(canvas, "Different assistants favour different businesses", "Provider concentration remains visible rather than being hidden inside the overall market figure.")
    _label(canvas, "Measured result", MARGIN, y, "measured")
    columns = ["Business", "OpenAI", "Claude", "Gemini", "Breadth", "Intents"]
    widths = [168, 68, 68, 68, 68, 66]
    x = MARGIN
    header_y = y - 24
    for label, width in zip(columns, widths):
        canvas.setFillColor(NAVY)
        canvas.rect(x, header_y - 28, width, 28, fill=1, stroke=0)
        _paragraph(canvas, label, x + 7, header_y - 11, width - 14, font=FONT_BOLD, size=8, color=WHITE, max_lines=1)
        x += width
    for row_index, row in enumerate(rows):
        row_y = header_y - 28 - row_index * 58
        fill = WHITE if row_index % 2 == 0 else PALE
        canvas.setFillColor(fill)
        canvas.rect(MARGIN, row_y - 58, sum(widths), 58, fill=1, stroke=0)
        x = MARGIN
        values = [
            row["business"],
            row["OpenAI"],
            row["Claude"],
            row["Gemini"],
            row["provider_breadth"],
            row["intent_breadth"],
        ]
        for col_index, (value, width) in enumerate(zip(values, widths)):
            if col_index in (1, 2, 3):
                normalized = _text(value).lower()
                visible = normalized not in {
                    "",
                    "0",
                    "none",
                    "not visible",
                    "not materially visible",
                }
                canvas.setFillColor(BLUE if visible else LINE)
                canvas.circle(x + width / 2, row_y - 27, 7, fill=1, stroke=0)
                canvas.setFont(FONT_BOLD, 8)
                canvas.setFillColor(INK)
                canvas.drawCentredString(x + width / 2, row_y - 47, _text(value))
            else:
                _paragraph(canvas, value, x + 7, row_y - 18, width - 14, font=FONT_BOLD if col_index == 0 else FONT, size=8, color=NAVY if col_index == 0 else INK, max_lines=3)
            x += width
    note_y = header_y - 28 - len(rows) * 58 - 30
    _label(canvas, "Observed evidence", MARGIN, note_y, "observed")
    _paragraph(canvas, report["provider_observation"], MARGIN, note_y - 28, CONTENT_WIDTH, size=9, color=INK, max_lines=5)
    _paragraph(canvas, report["provider_caveat"], MARGIN, note_y - 90, CONTENT_WIDTH, size=8.2, color=MID, max_lines=4)


def _draw_cohort(canvas: Canvas, report: Mapping[str, Any]) -> None:
    cohort = report["diagnostic_cohort"]
    y = _page_title(canvas, "Three useful comparison businesses", "A concise diagnostic subset, not a replacement for the full recommendation market.")
    _label(canvas, "Observed evidence", MARGIN, y, "observed")
    card_height = 128
    for index, item in enumerate(cohort):
        card_y = y - 25 - index * (card_height + 16)
        _card(canvas, MARGIN, card_y, CONTENT_WIDTH, card_height, fill=WHITE)
        canvas.setFillColor(BLUE if index == 0 else TEAL if index == 1 else GOLD)
        canvas.roundRect(MARGIN, card_y - card_height, 8, card_height, 4, fill=1, stroke=0)
        _paragraph(canvas, item["business_name"], MARGIN + 24, card_y - 26, 228, font=FONT_BOLD, size=12, color=NAVY, max_lines=2)
        canvas.setFont(FONT_BOLD, 18)
        canvas.setFillColor(BLUE)
        canvas.drawString(MARGIN + 270, card_y - 35, f"{float(item['business_sor_pct']):.2f}%")
        canvas.setFont(FONT, 8)
        canvas.setFillColor(MID)
        canvas.drawString(MARGIN + 270, card_y - 52, f"{item['recommendations']} recommendations")
        _paragraph(canvas, ", ".join(item["provider_names"]), MARGIN + 395, card_y - 28, 110, font=FONT_BOLD, size=8, color=NAVY, max_lines=3)
        _paragraph(canvas, item["selection_reason"], MARGIN + 24, card_y - 80, CONTENT_WIDTH - 48, size=8.5, color=INK, max_lines=3)
    _paragraph(canvas, report["cohort_note"], MARGIN, 88, CONTENT_WIDTH, size=8.5, color=MID, max_lines=4)


def _draw_evidence_matrix(canvas: Canvas, report: Mapping[str, Any]) -> None:
    matrix = report["evidence_matrix"]
    businesses = matrix["businesses"]
    dimensions = matrix["dimensions"]
    y = _page_title(canvas, "The evidence across the four businesses", "Only the most decision-useful comparisons are shown here; supporting detail remains in the frozen audit evidence.")
    _label(canvas, "Observed evidence", MARGIN, y, "observed")
    label_width = 132
    value_width = (CONTENT_WIDTH - label_width) / len(businesses)
    top = y - 24
    canvas.setFillColor(NAVY)
    canvas.rect(MARGIN, top - 48, CONTENT_WIDTH, 48, fill=1, stroke=0)
    x = MARGIN + label_width
    for business in businesses:
        _paragraph(canvas, business, x + 6, top - 14, value_width - 12, font=FONT_BOLD, size=8, color=WHITE, max_lines=3)
        x += value_width
    row_height = 55
    for index, dimension in enumerate(dimensions):
        row_y = top - 48 - index * row_height
        canvas.setFillColor(WHITE if index % 2 == 0 else PALE)
        canvas.rect(MARGIN, row_y - row_height, CONTENT_WIDTH, row_height, fill=1, stroke=0)
        _paragraph(canvas, dimension["label"], MARGIN + 7, row_y - 17, label_width - 14, font=FONT_BOLD, size=8, color=NAVY, max_lines=3)
        x = MARGIN + label_width
        for business in businesses:
            _paragraph(canvas, dimension["values"][business], x + 6, row_y - 15, value_width - 12, size=8, color=INK, max_lines=3)
            x += value_width
    note_y = top - 48 - len(dimensions) * row_height - 25
    _paragraph(canvas, matrix["note"], MARGIN, note_y, CONTENT_WIDTH, size=8, color=MID, max_lines=4)


def _draw_strengths(canvas: Canvas, report: Mapping[str, Any], client: str) -> None:
    strengths = report["strengths"]
    y = _page_title(canvas, "A credible foundation to build on", f"{client} already has useful evidence that can be made clearer and more consistently reinforced.")
    _label(canvas, "Observed evidence", MARGIN, y, "observed")
    card_width = (CONTENT_WIDTH - 16) / 2
    card_height = 180
    for index, item in enumerate(strengths[:4]):
        x = MARGIN + (index % 2) * (card_width + 16)
        card_y = y - 25 - (index // 2) * (card_height + 16)
        _card(canvas, x, card_y, card_width, card_height, fill=WHITE)
        canvas.setFillColor(TEAL)
        canvas.circle(x + 20, card_y - 23, 8, fill=1, stroke=0)
        _paragraph(canvas, item["title"], x + 38, card_y - 18, card_width - 52, font=FONT_BOLD, size=11, color=NAVY, max_lines=2)
        _paragraph(canvas, item["body"], x + 14, card_y - 62, card_width - 28, size=8.7, color=INK, max_lines=6)
        _paragraph(canvas, f"Evidence: {_evidence_labels(item['evidence_refs'])}", x + 14, card_y - 138, card_width - 28, size=8, color=MID, max_lines=3)
    _paragraph(canvas, report["strengths_note"], MARGIN, 92, CONTENT_WIDTH, font=FONT_BOLD, size=9, color=NAVY, max_lines=4)


def _draw_gaps(canvas: Canvas, report: Mapping[str, Any]) -> None:
    gaps = report["priority_gaps"]
    y = _page_title(canvas, "Where the discoverability evidence is weakest", "Prioritised observable differences, not claims about undocumented AI ranking mechanisms.")
    _label(canvas, "Observed evidence", MARGIN, y, "observed")
    row_height = 122
    for index, gap in enumerate(gaps[:4]):
        row_y = y - 24 - index * (row_height + 8)
        _card(canvas, MARGIN, row_y, CONTENT_WIDTH, row_height, fill=WHITE)
        canvas.setFont(FONT_BOLD, 16)
        canvas.setFillColor(GOLD)
        canvas.drawString(MARGIN + 14, row_y - 30, str(index + 1))
        _paragraph(canvas, gap["title"], MARGIN + 42, row_y - 20, 190, font=FONT_BOLD, size=10, color=NAVY, max_lines=2)
        _paragraph(canvas, f"Target evidence: {gap['observed']}", MARGIN + 250, row_y - 20, CONTENT_WIDTH - 264, size=8, color=INK, max_lines=3)
        _paragraph(canvas, f"Comparison: {gap['comparison']}", MARGIN + 42, row_y - 68, 210, size=8, color=MID, max_lines=3)
        _paragraph(canvas, gap["relevance"], MARGIN + 268, row_y - 66, CONTENT_WIDTH - 282, size=8, color=MID, leading=10, max_lines=4)
        canvas.setFont(FONT_BOLD, 8)
        canvas.setFillColor(TEAL)
        canvas.drawRightString(PAGE_WIDTH - MARGIN - 14, row_y - 105, f"Confidence: {gap['confidence']}")
    _paragraph(canvas, report["gap_caveat"], MARGIN, 73, CONTENT_WIDTH, size=8, color=MID, max_lines=3)


def _draw_actions(canvas: Canvas, report: Mapping[str, Any]) -> None:
    actions = report["priority_actions"][:3]
    y = _page_title(canvas, "The three actions we recommend first", "Evidence-backed, client-controllable improvements to the underlying public information.")
    _label(canvas, "Recommended action", MARGIN, y, "action")
    card_height = 168
    for index, action in enumerate(actions):
        card_y = y - 25 - index * (card_height + 14)
        _card(canvas, MARGIN, card_y, CONTENT_WIDTH, card_height, fill=WHITE)
        canvas.setFillColor(NAVY)
        canvas.circle(MARGIN + 25, card_y - 30, 15, fill=1, stroke=0)
        canvas.setFont(FONT_BOLD, 12)
        canvas.setFillColor(WHITE)
        canvas.drawCentredString(MARGIN + 25, card_y - 35, str(index + 1))
        _paragraph(canvas, action["title"], MARGIN + 52, card_y - 20, CONTENT_WIDTH - 160, font=FONT_BOLD, size=11, color=NAVY, max_lines=2)
        canvas.setFont(FONT_BOLD, 8)
        canvas.setFillColor(GOLD)
        canvas.drawRightString(PAGE_WIDTH - MARGIN - 14, card_y - 29, action["timing"])
        _paragraph(canvas, f"Evidence: {_evidence_labels(action['evidence_refs'])}", MARGIN + 52, card_y - 64, 212, size=8, color=MID, max_lines=4)
        _paragraph(canvas, f"Do: {action['steps']}", MARGIN + 278, card_y - 64, CONTENT_WIDTH - 292, size=8, color=INK, max_lines=5)
        _paragraph(canvas, f"Intended improvement: {action['intended_improvement']}", MARGIN + 52, card_y - 133, CONTENT_WIDTH - 66, font=FONT_BOLD, size=8, color=TEAL, max_lines=3)
    _paragraph(canvas, report["action_caveat"], MARGIN, 68, CONTENT_WIDTH, size=8, color=MID, max_lines=3)


def _draw_roadmap(canvas: Canvas, report: Mapping[str, Any]) -> None:
    data = report["roadmap"]
    y = _page_title(canvas, "From baseline to measurable improvement", "Implement the foundations, allow the public evidence to establish, then remeasure after meaningful change.")
    _label(canvas, "Recommended action", MARGIN, y, "action")
    phases = data["phases"]
    phase_width = (CONTENT_WIDTH - 30) / 4
    for index, phase in enumerate(phases[:4]):
        x = MARGIN + index * (phase_width + 10)
        _card(canvas, x, y - 28, phase_width, 235, fill=WHITE)
        canvas.setFillColor(BLUE if index < 3 else TEAL)
        canvas.rect(x, y - 55, phase_width, 27, fill=1, stroke=0)
        _paragraph(canvas, phase["timing"], x + 8, y - 42, phase_width - 16, font=FONT_BOLD, size=8, color=WHITE, max_lines=1)
        _paragraph(canvas, phase["title"], x + 10, y - 78, phase_width - 20, font=FONT_BOLD, size=10, color=NAVY, max_lines=3)
        _paragraph(canvas, phase["body"], x + 10, y - 132, phase_width - 20, size=8, color=INK, max_lines=7)
    y -= 305
    canvas.setFont(FONT_BOLD, 12)
    canvas.setFillColor(NAVY)
    canvas.drawString(MARGIN, y, "Ways to proceed")
    option_width = (CONTENT_WIDTH - 20) / 3
    for index, option in enumerate(data["options"][:3]):
        x = MARGIN + index * (option_width + 10)
        _card(canvas, x, y - 20, option_width, 112, fill=PALE)
        _paragraph(canvas, option["title"], x + 10, y - 42, option_width - 20, font=FONT_BOLD, size=9, color=NAVY, max_lines=2)
        _paragraph(canvas, option["body"], x + 10, y - 75, option_width - 20, size=8, color=MID, max_lines=4)
    _paragraph(canvas, data["remeasurement_note"], MARGIN, 92, CONTENT_WIDTH, font=FONT_BOLD, size=9, color=TEAL, max_lines=3)


def _draw_methodology(canvas: Canvas, report: Mapping[str, Any]) -> None:
    data = report["methodology"]
    y = _page_title(canvas, "Methodology and limitations", "Technical provenance is retained here so the main report can remain decision-focused.")
    _label(canvas, "Measured result", MARGIN, y, "measured")
    left_width = 245
    canvas.setFont(FONT_BOLD, 11)
    canvas.setFillColor(NAVY)
    canvas.drawString(MARGIN, y - 34, "Benchmark design")
    benchmark_lines = [
        f"Providers: {', '.join(data['providers'])}",
        f"Prompts: {data['prompt_count']}",
        f"Repetitions: {data['repetitions']} per prompt/provider",
        f"Expected responses: {data['expected_responses']}",
        f"Complete responses: {data['complete_responses']}",
        f"Benchmark: {data['benchmark']}",
    ]
    _paragraph(canvas, "\n".join(benchmark_lines), MARGIN, y - 58, left_width, size=8.5, color=INK, leading=16, max_lines=8)
    canvas.setFont(FONT_BOLD, 11)
    canvas.setFillColor(NAVY)
    canvas.drawString(MARGIN + 270, y - 34, "Validation")
    _paragraph(canvas, "\n".join(f"• {item}" for item in data["validation"]), MARGIN + 270, y - 58, CONTENT_WIDTH - 270, size=8.2, color=INK, leading=15, max_lines=9)
    y -= 220
    canvas.setStrokeColor(LINE)
    canvas.line(MARGIN, y, PAGE_WIDTH - MARGIN, y)
    canvas.setFont(FONT_BOLD, 11)
    canvas.setFillColor(NAVY)
    canvas.drawString(MARGIN, y - 26, "Evidence inventory")
    _paragraph(canvas, "\n".join(f"• {item}" for item in data["evidence_inventory"]), MARGIN, y - 48, CONTENT_WIDTH, size=8.2, color=INK, leading=14, max_lines=8)
    y -= 165
    canvas.setFont(FONT_BOLD, 11)
    canvas.setFillColor(NAVY)
    canvas.drawString(MARGIN, y, "Limitations")
    _paragraph(canvas, "\n".join(f"• {item}" for item in data["limitations"]), MARGIN, y - 23, CONTENT_WIDTH, size=8, color=MID, leading=13, max_lines=14)
    _paragraph(canvas, data["non_causality"], MARGIN, 78, CONTENT_WIDTH, font=FONT_BOLD, size=8.2, color=NAVY, max_lines=4)


def render_poc_audit_pdf(payload: Mapping[str, Any]) -> bytes:
    """Render a deterministic 12-page PDF from one frozen payload only."""

    report = _validate_report_contract(payload)
    _register_fonts()
    audit = payload["audit"]
    client_name = _text(audit["target_business_name"])
    audit_date = _text(audit["audit_date"])
    output = io.BytesIO()
    canvas = Canvas(
        output,
        pagesize=A4,
        pageCompression=1,
        invariant=1,
    )
    canvas.setTitle(f"AI Visibility & Discoverability Audit - {client_name}")
    canvas.setAuthor("POC Audit v1")
    canvas.setSubject("Model-memory AI visibility and comparative evidence audit")

    _draw_cover(canvas, payload, report)
    _new_page(canvas, 2, client_name, audit_date)
    _draw_executive(canvas, report, client_name)
    _new_page(canvas, 3, client_name, audit_date)
    _draw_visibility(canvas, report, client_name)
    _new_page(canvas, 4, client_name, audit_date)
    _draw_market(canvas, report, client_name)
    _new_page(canvas, 5, client_name, audit_date)
    _draw_provider_comparison(canvas, report)
    _new_page(canvas, 6, client_name, audit_date)
    _draw_cohort(canvas, report)
    _new_page(canvas, 7, client_name, audit_date)
    _draw_evidence_matrix(canvas, report)
    _new_page(canvas, 8, client_name, audit_date)
    _draw_strengths(canvas, report, client_name)
    _new_page(canvas, 9, client_name, audit_date)
    _draw_gaps(canvas, report)
    _new_page(canvas, 10, client_name, audit_date)
    _draw_actions(canvas, report)
    _new_page(canvas, 11, client_name, audit_date)
    _draw_roadmap(canvas, report)
    _new_page(canvas, 12, client_name, audit_date)
    _draw_methodology(canvas, report)
    _footer(canvas, 12, client_name, audit_date)
    canvas.save()
    return output.getvalue()
