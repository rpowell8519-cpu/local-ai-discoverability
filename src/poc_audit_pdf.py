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
LEGACY_REPORT_PAGE_COUNT = 13
BETA_REPORT_PAGE_COUNT = 17
PDF_RENDERER_VERSION = "poc_audit_pdf_v1_beta_accessible_2"

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
    _frozen_prompt_panel(payload)
    if report.get("report_format") == "beta_accessible_v2":
        introduction = report.get("introduction")
        if not isinstance(introduction, Mapping):
            raise PdfRenderError("The accessible beta report requires an introduction")
        for key in ("owner_priority", "method_steps", "scope_note"):
            _require(introduction, key, "report.introduction")
        if len(introduction["method_steps"]) != 3:
            raise PdfRenderError("The accessible beta introduction requires three method steps")
        _validate_review_quotes(payload, report)
        _validate_question_performance(payload, report)

    return report


def _validate_review_quotes(
    payload: Mapping[str, Any], report: Mapping[str, Any]
) -> None:
    quotes = report.get("review_quotes")
    if not isinstance(quotes, list) or len(quotes) > 6:
        raise PdfRenderError("The accessible beta report supports up to six review quotes")
    records_by_id: dict[str, tuple[str, Mapping[str, Any]]] = {}
    for review_set in payload["review_evidence"]["review_sets"]:
        place_id = str(review_set.get("google_place_id") or "")
        for record in review_set.get("records", []):
            records_by_id[str(record.get("review_id") or "")] = (place_id, record)
    for item in quotes:
        review_id = str(item.get("review_id") or "")
        source = records_by_id.get(review_id)
        if source is None:
            raise PdfRenderError(f"Review quote source not found: {review_id}")
        place_id, record = source
        if str(item.get("google_place_id") or "") != place_id:
            raise PdfRenderError(f"Review quote business does not match: {review_id}")
        if _text(item.get("quote")) != _text(record.get("review_text")):
            raise PdfRenderError(f"Review quote is not verbatim: {review_id}")
        _require(item, "business_name", "report.review_quotes")
        _require(item, "takeaway", "report.review_quotes")


def _validate_question_performance(
    payload: Mapping[str, Any], report: Mapping[str, Any]
) -> None:
    rows = report.get("question_performance")
    prompts = _frozen_prompt_panel(payload)
    if not isinstance(rows, list) or len(rows) != len(prompts):
        raise PdfRenderError("Question-level performance must cover every frozen prompt")
    expected_answers = int(payload["methodology"]["repetitions"]) * len(
        payload["methodology"]["providers"]
    )
    prompt_by_order = {item["order"]: item for item in prompts}
    target_total = 0
    for row in rows:
        order = int(row.get("order") or 0)
        prompt = prompt_by_order.get(order)
        if prompt is None or _text(row.get("prompt_text")) != prompt["prompt_text"]:
            raise PdfRenderError("Question-level performance does not match frozen prompts")
        if int(row.get("answer_count") or 0) != expected_answers:
            raise PdfRenderError("Question-level answer count does not reconcile")
        if len(row.get("provider_results") or []) != len(payload["methodology"]["providers"]):
            raise PdfRenderError("Question-level provider results are incomplete")
        target_total += int(row.get("target_appearances") or 0)
    if target_total != int(report["visibility"]["recommendations"]):
        raise PdfRenderError("Question-level target appearances do not reconcile")


def _frozen_prompt_panel(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return eight verbatim prompts after reconciling queries and responses."""
    methodology = payload.get("methodology", {})
    queries = methodology.get("queries", [])
    repetitions = int(methodology.get("repetitions") or 0)
    prompt_count = int(methodology.get("prompt_count") or 0)
    if prompt_count != 8 or repetitions < 1:
        raise PdfRenderError("The prompts appendix requires exactly eight frozen prompts")

    grouped: dict[int, list[Mapping[str, Any]]] = {}
    for query in queries:
        try:
            order = int(query.get("base_prompt_order"))
        except (TypeError, ValueError):
            raise PdfRenderError("A frozen query has no valid base prompt order") from None
        grouped.setdefault(order, []).append(query)
    if set(grouped) != set(range(1, 9)):
        raise PdfRenderError("Frozen queries do not contain base prompts 1 through 8")

    panel: list[dict[str, Any]] = []
    for order in range(1, 9):
        records = grouped[order]
        texts = {_text(item.get("prompt_text")) for item in records}
        categories = {_text(item.get("prompt_category")) for item in records}
        sources = {_text(item.get("prompt_source")) for item in records}
        repeat_indexes = {int(item.get("repeat_index") or 0) for item in records}
        if len(records) != repetitions or repeat_indexes != set(range(1, repetitions + 1)):
            raise PdfRenderError(f"Frozen prompt {order} does not contain every repetition")
        if len(texts) != 1 or not next(iter(texts)):
            raise PdfRenderError(f"Frozen prompt {order} text is missing or inconsistent")
        if len(categories) != 1 or not next(iter(categories)):
            raise PdfRenderError(f"Frozen prompt {order} category is missing or inconsistent")
        if len(sources) != 1 or not next(iter(sources)):
            raise PdfRenderError(f"Frozen prompt {order} source is missing or inconsistent")
        panel.append({
            "order": order, "prompt_text": next(iter(texts)),
            "prompt_category": next(iter(categories)), "prompt_source": next(iter(sources)),
        })

    panel_lookup = {item["order"]: item for item in panel}
    responses = payload.get("baseline_validation", {}).get("responses", [])
    expected_providers = len(methodology.get("providers", []))
    expected_responses = prompt_count * repetitions * expected_providers
    if len(responses) != expected_responses:
        raise PdfRenderError("Frozen response count does not reconcile with the prompt panel")
    response_counts: dict[int, int] = {}
    for response in responses:
        order = int(response.get("base_prompt_order") or 0)
        source = panel_lookup.get(order)
        if source is None or _text(response.get("prompt_text")) != source["prompt_text"]:
            raise PdfRenderError("Frozen response prompts do not reconcile with frozen queries")
        if _text(response.get("prompt_category")) != source["prompt_category"]:
            raise PdfRenderError("Frozen response categories do not reconcile with frozen queries")
        response_counts[order] = response_counts.get(order, 0) + 1
    expected_per_prompt = repetitions * expected_providers
    if any(response_counts.get(order) != expected_per_prompt for order in range(1, 9)):
        raise PdfRenderError("Frozen responses do not represent every prompt consistently")
    return panel


def _prompt_result_panel(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Add target outcomes to the verbatim prompt panel from frozen responses."""
    panel = _frozen_prompt_panel(payload)
    responses = payload["baseline_validation"]["responses"]
    by_order: dict[int, list[Mapping[str, Any]]] = {item["order"]: [] for item in panel}
    for response in responses:
        by_order[int(response["base_prompt_order"])].append(response)

    result: list[dict[str, Any]] = []
    for prompt in panel:
        prompt_responses = by_order[prompt["order"]]
        valid_responses = [
            item for item in prompt_responses
            if item.get("status") == "completed"
            and bool(item.get("response_complete"))
        ]
        recommendations = sum(
            bool(item["parser_reconciliation"].get("persisted_target_recommended"))
            for item in valid_responses
        )
        mentions = sum(
            bool(item["parser_reconciliation"].get("persisted_target_mentioned"))
            for item in valid_responses
        )
        result.append({
            **prompt,
            "responses": len(valid_responses),
            "attempted_responses": len(prompt_responses),
            "recommendations": recommendations,
            "mentions": mentions,
        })
    return result


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
    sorted_frozen_rows = sorted(
        frozen_market["canonical_businesses"],
        key=lambda item: (-int(item["recommendations"]), _text(item["business_name"])),
    )
    target_id = str(payload["audit"]["target_google_place_id"])
    expected_target_rank = next(
        (
            index for index, item in enumerate(sorted_frozen_rows, start=1)
            if str(item.get("google_place_id")) == target_id
        ),
        None,
    )
    if "target_rank" in market_report and market_report.get("target_rank") != expected_target_rank:
        errors.append("recommendation-market target rank")
    if "business_count" in market_report and market_report.get("business_count") != len(sorted_frozen_rows):
        errors.append("recommendation-market business count")
    target_source = frozen_rows.get(target_id)
    if target_source and abs(
        float(visibility["business_sor_pct"])
        - float(target_source["share_of_recommendation"]) * 100
    ) > 0.0001:
        errors.append("visibility target SOR")
    target_slots = [
        item for item in slots
        if item["slot_disposition"] == "business"
        and str(item.get("google_place_id")) == target_id
    ]
    if target_slots and "average_position" in visibility:
        average_position = sum(float(item["position"]) for item in target_slots) / len(target_slots)
        if abs(float(visibility["average_position"]) - average_position) > 0.0001:
            errors.append("visibility average target position")
        if int(visibility.get("best_position") or 0) != min(int(item["position"]) for item in target_slots):
            errors.append("visibility best target position")
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
    flexible_evidence = report.get("report_format") == "beta_accessible_v2"
    if (
        (not flexible_evidence and len(audits) != 4)
        or len(audits) > 4
        or not all(item.get("pages") for item in audits)
    ):
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
    decision_status = decisions.get("status")
    if not decisions.get("version") or decision_status not in {
        "operator_approved",
        "review_draft",
    }:
        errors.append("recognised analyst-decision status")
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


def _footer(
    canvas: Canvas, page: int, client_name: str, audit_date: str, page_count: int
) -> None:
    canvas.setStrokeColor(LINE)
    canvas.line(MARGIN, 30, PAGE_WIDTH - MARGIN, 30)
    canvas.setFont(FONT, 8)
    canvas.setFillColor(MID)
    canvas.drawString(MARGIN, 17, f"{client_name} | POC AI visibility audit | {audit_date}")
    canvas.drawRightString(PAGE_WIDTH - MARGIN, 17, f"{page} / {page_count}")


def _new_page(
    canvas: Canvas, page: int, client_name: str, audit_date: str, page_count: int
) -> None:
    if page > 1:
        _footer(canvas, page - 1, client_name, audit_date, page_count)
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
            "website": "website evidence",
            "reviews": "customer-review evidence",
            "diagnostic": "business comparison",
            "market": "AI recommendation results",
            "gap": "priority-gap evidence",
        }.get(prefix, "audit evidence")
        if label not in labels:
            labels.append(label)
    return ", ".join(labels)


def _plain_client_text(value: Any) -> str:
    """Replace analytical jargon with equivalent client-facing language."""
    text = _text(value)
    replacements = (
        ("independent customer corroboration", "independent evidence from customers"),
        ("customer corroboration", "supporting customer evidence"),
        ("first-party evidence", "information on the business's own website"),
        ("machine-readable representation", "digital description"),
        ("diagnostic set", "set analysed for this audit"),
        ("adaptive audit", "website review"),
        ("crawlable", "accessible"),
        ("corroboration", "supporting evidence"),
        ("corpus", "body of customer reviews"),
    )
    for technical, plain in replacements:
        text = text.replace(technical, plain).replace(technical.capitalize(), plain.capitalize())
    return text


def _plain_gap_title(value: Any) -> str:
    title = _text(value)
    return {
        "Entity and structured-data clarity": "Make the business identity clearer online",
        "Service and expertise depth": "Explain services and expertise in more depth",
        "Review scale and recency": "Build a larger, more current review picture",
        "Authority and corroboration": "Reinforce key strengths across public sources",
    }.get(title, title)


def _plain_strength_title(value: Any) -> str:
    title = _text(value)
    return {
        "Relevant service evidence": "Important services are already covered",
        "Credible site presence": "A useful website foundation",
        "Positive customer sentiment": "Customers are positive about the business",
        "Local and human proposition": "A local, personal business story",
    }.get(title, title)


def _plain_action_title(value: Any) -> str:
    title = _plain_client_text(value)
    if title.startswith("Implement accurate ") and title.endswith(" structured data"):
        return "Add accurate structured business information to the website"
    return {
        "Develop stronger priority-service evidence hubs": "Build stronger pages for priority services",
        "Build stronger and more current supporting customer evidence": (
            "Build a stronger, more current customer review picture"
        ),
    }.get(title, title)


def _action_reason(action: Mapping[str, Any], report: Mapping[str, Any]) -> str:
    gap_by_ref = {
        f"gap:{gap['gap_id']}": gap
        for gap in report["priority_gaps"]
        if gap.get("gap_id")
    }
    for ref in action["evidence_refs"]:
        gap = gap_by_ref.get(ref)
        if gap:
            return _plain_client_text(gap["observed"])
    return f"Supported by {_evidence_labels(action['evidence_refs'])}."


def _plain_roadmap_title(value: Any) -> str:
    title = _text(value)
    return {
        "Entity foundations": "Clear business identity",
        "Content and propositions": "Services and expertise",
        "Review programme": "Customer review programme",
    }.get(title, title)


def _plain_dimension_label(label: Any) -> str:
    """Translate internal comparison labels without changing their values."""
    value = _text(label)
    return {
        "AI visibility": "How often AI recommended them",
        "Provider breadth": "AI assistants recommending them",
        "Tested intent breadth": "Customer questions they appeared for",
        "Intent breadth": "Customer questions they appeared for",
        "Audited site footprint": "Website pages reviewed",
        "Site footprint": "Website pages reviewed",
        "Structured business data": "Clear business details for digital systems",
        "Structured data": "Clear business details for digital systems",
        "Priority services": "Priority service information",
        "Service evidence": "Priority service information",
        "Review evidence analysed": "Customer reviews analysed",
        "Review evidence": "Customer reviews analysed",
    }.get(value, value)


def _interpretation_box(canvas: Canvas, y: float, heading: str, body: str) -> None:
    _card(canvas, MARGIN, y, CONTENT_WIDTH, 60, fill=PALE)
    canvas.setFont(FONT_BOLD, 8)
    canvas.setFillColor(TEAL)
    canvas.drawString(MARGIN + 16, y - 20, heading.upper())
    _paragraph(
        canvas, body, MARGIN + 16, y - 38, CONTENT_WIDTH - 32,
        size=8.5, color=NAVY, leading=11.5, max_lines=2,
    )


def _draw_cover(canvas: Canvas, payload: Mapping[str, Any], report: Mapping[str, Any]) -> None:
    audit = payload["audit"]
    client = _text(audit["target_business_name"])
    canvas.setFillColor(NAVY)
    canvas.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, fill=1, stroke=0)
    canvas.setFillColor(BLUE)
    canvas.rect(0, PAGE_HEIGHT - 20, PAGE_WIDTH, 20, fill=1, stroke=0)
    if payload["diagnostic"]["analyst_decisions"].get("status") == "review_draft":
        _label(canvas, "Review draft", PAGE_WIDTH - MARGIN - 96, PAGE_HEIGHT - 49, "action")
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
    canvas.drawString(MARGIN + 18, 105, f"{complete} API responses")
    canvas.setFont(FONT, 10)
    canvas.setFillColor(HexColor("#D7E1F0"))
    canvas.drawString(MARGIN + 18, 82, "Model-memory benchmark | Browsing disabled | Saved responses checked")
    canvas.setFont(FONT, 9)
    canvas.setFillColor(HexColor("#AFC0D6"))
    canvas.drawString(MARGIN, 38, f"Audit date: {_text(audit['audit_date'])}")


def _draw_introduction(canvas: Canvas, report: Mapping[str, Any], client: str) -> None:
    introduction = report["introduction"]
    y = _page_title(
        canvas,
        "How we explored your visibility in AI recommendations",
        "A straightforward comparison based on the services and customer questions that matter to your business.",
    )
    _label(canvas, "What we did", MARGIN, y, "measured")
    _card(canvas, MARGIN, y - 22, CONTENT_WIDTH, 94, fill=PALE)
    _paragraph(
        canvas,
        f"You told us what {client} should be known for. We used that starting point "
        "to explore how the business appears when potential customers ask AI for local recommendations.",
        MARGIN + 18, y - 48, CONTENT_WIDTH - 36,
        font=FONT_BOLD, size=11, color=NAVY, leading=15, max_lines=4,
    )
    y -= 146
    card_width = (CONTENT_WIDTH - 24) / 3
    for index, step in enumerate(introduction["method_steps"], start=1):
        x = MARGIN + (index - 1) * (card_width + 12)
        _card(canvas, x, y, card_width, 226, fill=WHITE)
        canvas.setFillColor(BLUE if index < 3 else TEAL)
        canvas.circle(x + 24, y - 28, 15, fill=1, stroke=0)
        canvas.setFont(FONT_BOLD, 12)
        canvas.setFillColor(WHITE)
        canvas.drawCentredString(x + 24, y - 33, str(index))
        _paragraph(
            canvas, step["title"], x + 14, y - 68, card_width - 28,
            font=FONT_BOLD, size=11, color=NAVY, leading=14, max_lines=3,
        )
        _paragraph(
            canvas, step["body"], x + 14, y - 122, card_width - 28,
            size=8.8, color=INK, leading=12.5, max_lines=7,
        )
    y -= 268
    _label(canvas, "Your priorities", MARGIN, y, "action")
    _paragraph(
        canvas, introduction["owner_priority"], MARGIN, y - 30, CONTENT_WIDTH,
        font=FONT_BOLD, size=12, color=NAVY, leading=16, max_lines=4,
    )
    _paragraph(
        canvas, introduction["scope_note"], MARGIN, y - 100, CONTENT_WIDTH,
        size=8.8, color=MID, leading=12.5, max_lines=4,
    )


def _draw_executive(canvas: Canvas, report: Mapping[str, Any], client: str) -> None:
    summary = report["executive_summary"]
    visibility = report["visibility"]
    observed = max(int(visibility["mentions"]), int(visibility["recommendations"]))
    y = _page_title(
        canvas,
        f"{client} appeared in {observed} of {visibility['responses_complete']} AI responses",
        "The headline finding, the evidence already in place and the practical next step.",
    )
    _label(canvas, "Measured result", MARGIN, y, "measured")
    _card(canvas, MARGIN, y - 20, 172, 118, fill=NAVY, border=NAVY)
    canvas.setFillColor(WHITE)
    headline_metric = f"{observed} of {visibility['responses_complete']}"
    metric_size = 34 if len(headline_metric) > 6 else 40
    canvas.setFont(FONT_BOLD, metric_size)
    canvas.drawString(MARGIN + 16, y - 70, headline_metric)
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
        _paragraph(canvas, _plain_strength_title(strength["title"]), x + 12, y - 42, card_width - 24, font=FONT_BOLD, size=10, color=NAVY, max_lines=2)
        _paragraph(canvas, _plain_client_text(strength["body"]), x + 12, y - 73, card_width - 24, size=8.2, color=MID, max_lines=4)
    y -= 160
    _label(canvas, "Recommended action", MARGIN, y, "action")
    _paragraph(canvas, _plain_client_text(summary["action_statement"]), MARGIN, y - 27, CONTENT_WIDTH, font=FONT_BOLD, size=12, color=NAVY, max_lines=3)
    _paragraph(canvas, summary["non_causality"], MARGIN, y - 76, CONTENT_WIDTH, size=8.5, color=MID, max_lines=3)


def _draw_question_visibility(
    canvas: Canvas,
    payload: Mapping[str, Any],
    report: Mapping[str, Any],
    client: str,
) -> None:
    data = report["visibility"]
    rows = report["question_performance"]
    y = _page_title(
        canvas,
        f"How visible was {client} for each customer question?",
        "Each question was asked nine times: three times each through the OpenAI, Anthropic and Google APIs.",
    )
    _label(canvas, "Measured result", MARGIN, y, "measured")
    top = y - 24
    widths = [27, 225, 88, CONTENT_WIDTH - 340]
    headers = ["#", "Customer question", client, "Businesses appearing most often"]
    x = MARGIN
    for index, (header, width) in enumerate(zip(headers, widths)):
        canvas.setFillColor(NAVY)
        canvas.rect(x, top - 34, width, 34, fill=1, stroke=0)
        _paragraph(
            canvas, header, x + 6, top - 13, width - 12,
            font=FONT_BOLD, size=8, color=WHITE, max_lines=2,
        )
        x += width
    row_height = 63
    for index, row in enumerate(rows):
        row_y = top - 34 - index * row_height
        canvas.setFillColor(WHITE if index % 2 == 0 else PALE)
        canvas.rect(MARGIN, row_y - row_height, CONTENT_WIDTH, row_height, fill=1, stroke=0)
        canvas.setFont(FONT_BOLD, 9)
        canvas.setFillColor(BLUE)
        canvas.drawCentredString(MARGIN + widths[0] / 2, row_y - 31, str(row["order"]))
        question_x = MARGIN + widths[0]
        _paragraph(
            canvas, row["prompt_category"], question_x + 7, row_y - 14,
            widths[1] - 14, font=FONT_BOLD, size=8, color=BLUE, max_lines=1,
        )
        _paragraph(
            canvas, row["prompt_text"], question_x + 7, row_y - 31,
            widths[1] - 14, font=FONT_BOLD, size=8.2, color=NAVY,
            leading=10.5, max_lines=3,
        )
        target_x = question_x + widths[1]
        appearances = int(row["target_appearances"])
        canvas.setFont(FONT_BOLD, 11)
        canvas.setFillColor(TEAL if appearances else RED)
        canvas.drawCentredString(
            target_x + widths[2] / 2, row_y - 27,
            f"{appearances} of {row['answer_count']}",
        )
        canvas.setFont(FONT_BOLD, 8)
        canvas.drawCentredString(
            target_x + widths[2] / 2, row_y - 43,
            "APPEARED" if appearances else "DID NOT APPEAR",
        )
        leader_x = target_x + widths[2]
        leader_lines = [
            f"{item['business_name']}{' [identity unverified]' if item.get('identity_status') == 'unresolved' else ''} "
            f"- {item['appearances']} of {row['answer_count']}"
            for item in row["leaders"][:2]
        ]
        _paragraph(
            canvas, "\n".join(leader_lines) or "No named business recommendations",
            leader_x + 7, row_y - 18, widths[3] - 14,
            size=8, color=INK, leading=12, max_lines=4,
        )
    y = top - 34 - len(rows) * row_height - 18
    _interpretation_box(
        canvas,
        y,
        "What this means",
        f"{client} did not appear for any of the eight customer needs tested. The right-hand "
        "column shows which businesses were most strongly associated with each individual need.",
    )


def _draw_visibility(
    canvas: Canvas,
    payload: Mapping[str, Any],
    report: Mapping[str, Any],
    client: str,
) -> None:
    data = report["visibility"]
    prompts = _prompt_result_panel(payload)
    y = _page_title(
        canvas,
        f"What customers might ask AI - did {client} appear?",
        "The exact questions are shown below. Each was tested repeatedly across all three AI assistants.",
    )
    _label(canvas, "Measured result", MARGIN, y, "measured")
    y -= 26
    card_width = (CONTENT_WIDTH - 14) / 2
    card_height = 116
    for index, prompt in enumerate(prompts):
        x = MARGIN + (index % 2) * (card_width + 14)
        card_y = y - (index // 2) * (card_height + 10)
        proposition = prompt["prompt_source"] == "client_proposition"
        accent = GOLD if proposition else BLUE
        fill = HexColor("#FFF8E9") if proposition else WHITE
        _card(canvas, x, card_y, card_width, card_height, fill=fill)
        canvas.setFillColor(accent)
        canvas.roundRect(x, card_y - card_height, 6, card_height, 4, fill=1, stroke=0)
        canvas.setFont(FONT_BOLD, 8)
        canvas.setFillColor(accent)
        canvas.drawString(x + 16, card_y - 19, _text(prompt["prompt_category"]).upper())
        _paragraph(
            canvas, f'"{prompt["prompt_text"]}"', x + 16, card_y - 40,
            card_width - 32, font=FONT_BOLD, size=9, color=NAVY,
            leading=12, max_lines=4,
        )
        recommendations = int(prompt["recommendations"])
        status = (
            "NOT RECOMMENDED"
            if recommendations == 0
            else f"RECOMMENDED IN {recommendations} OF {prompt['responses']} RESPONSES"
        )
        canvas.setFont(FONT_BOLD, 8)
        canvas.setFillColor(RED if recommendations == 0 else TEAL)
        canvas.drawString(x + 16, card_y - 101, f"{client}: {status}")
    y -= 4 * (card_height + 10) + 4
    _interpretation_box(
        canvas,
        y,
        "What this means",
        f"Across these eight recommendation questions, {client} was recommended "
        f"in {data['recommendations']} of {data['responses_complete']} responses. "
        "This is a snapshot of how the assistants answered, not a claim about lost customers or revenue.",
    )


def _draw_market(canvas: Canvas, report: Mapping[str, Any], client: str) -> None:
    data = report["recommendation_market"]
    target_recommendations = int(report["visibility"]["recommendations"])
    target_rank = int(data.get("target_rank") or 0)
    if target_recommendations:
        title = (
            f"{client} ranks #{target_rank} in the measured recommendation market"
        )
        subtitle = (
            "The chart shows where the target sits among the businesses named most often."
        )
    else:
        title = "These are the businesses AI recommended instead"
        subtitle = (
            "The chart shows the named businesses that appeared most often across the complete benchmark."
        )
    y = _page_title(
        canvas,
        title,
        subtitle,
    )
    _label(canvas, "Measured result", MARGIN, y, "measured")
    _card(canvas, MARGIN, y - 20, CONTENT_WIDTH, 62, fill=PALE)
    canvas.setFont(FONT_BOLD, 20)
    canvas.setFillColor(NAVY)
    canvas.drawString(MARGIN + 16, y - 52, str(data["business_slots"]))
    _paragraph(
        canvas, "recommendations of named businesses were analysed",
        MARGIN + 66, y - 43, 270, font=FONT_BOLD, size=9, color=NAVY, max_lines=2,
    )
    if target_recommendations and report["visibility"].get("average_position"):
        market_summary = (
            f"{client}: #{target_rank} | {target_recommendations} recommendations | "
            f"average position {float(report['visibility']['average_position']):.2f} | "
            f"best #{int(report['visibility']['best_position'])}"
        )
    else:
        market_summary = (
            f"{data['excluded_slots']} general-advice or platform-name items were not counted as businesses."
        )
    _paragraph(
        canvas, market_summary,
        MARGIN + 350, y - 42, CONTENT_WIDTH - 366, size=8, color=MID, max_lines=3,
    )
    y -= 105
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
        is_target = name == client
        canvas.setFillColor(BLUE if is_target else TEAL)
        canvas.roundRect(chart_x, row_y - 12, bar_width, 13, 3, fill=1, stroke=0)
        canvas.setFont(FONT_BOLD, 8)
        canvas.setFillColor(NAVY)
        canvas.drawString(chart_x + bar_width + 7, row_y - 10, f"{float(item['business_sor_pct']):.2f}% | {item['recommendations']}")
    target_y = y - len(businesses) * row_height - 7
    target_is_shown = any(item["business_name"] == client for item in businesses)
    if not target_is_shown:
        canvas.setStrokeColor(RED)
        canvas.setLineWidth(2)
        canvas.line(chart_x, target_y, chart_x + chart_width, target_y)
        canvas.setFont(FONT_BOLD, 9)
        canvas.setFillColor(RED)
        canvas.drawString(MARGIN, target_y - 3, client)
        canvas.drawRightString(PAGE_WIDTH - MARGIN, target_y - 3, f"{float(report['visibility']['business_sor_pct']):.2f}% | {report['visibility']['recommendations']}")
    _interpretation_box(
        canvas,
        target_y - 28,
        "What this means",
        "These businesses appeared most often when the assistants named local options. "
        "The percentages show share of named-business recommendations in this audit - not commercial market share.",
    )


def _draw_provider_comparison(
    canvas: Canvas, report: Mapping[str, Any], client: str
) -> None:
    rows = report["provider_comparison"]
    target_recommendations = int(report["visibility"]["recommendations"])
    subtitle = (
        f"{client} was not recommended by any assistant in this benchmark; "
        "the other businesses had distinct patterns."
        if target_recommendations == 0
        else "The measured pattern varies by assistant and by business."
    )
    y = _page_title(
        canvas,
        "Different AI assistants produced different competitor lists",
        subtitle,
    )
    _label(canvas, "Measured result", MARGIN, y, "measured")
    columns = ["Business", "OpenAI", "Claude", "Gemini", "Assistants", "Questions"]
    widths = [168, 68, 68, 68, 68, 66]
    x = MARGIN
    header_y = y - 24
    for column_index, (label, width) in enumerate(zip(columns, widths)):
        canvas.setFillColor(NAVY)
        canvas.rect(x, header_y - 28, width, 28, fill=1, stroke=0)
        if column_index == 0:
            _paragraph(canvas, label, x + 12, header_y - 11, width - 24, font=FONT_BOLD, size=8, color=WHITE, max_lines=1)
        else:
            canvas.setFont(FONT_BOLD, 8)
            canvas.setFillColor(WHITE)
            canvas.drawCentredString(x + width / 2, header_y - 18, label)
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
                canvas.circle(x + width / 2, row_y - 23, 7, fill=1, stroke=0)
                canvas.setFont(FONT_BOLD, 8)
                canvas.setFillColor(INK)
                canvas.drawCentredString(x + width / 2, row_y - 45, _text(value))
            elif col_index in (4, 5):
                canvas.setFont(FONT_BOLD, 9)
                canvas.setFillColor(INK)
                canvas.drawCentredString(x + width / 2, row_y - 32, _text(value))
            else:
                _paragraph(canvas, value, x + 12, row_y - 21, width - 24, font=FONT_BOLD, size=8, color=NAVY, max_lines=3)
            x += width
    note_y = header_y - 28 - len(rows) * 58 - 30
    _interpretation_box(
        canvas,
        note_y + 2,
        "What this means",
        "Each assistant produced its own mix. Looking across all three shows which businesses "
        "had broad visibility and which appeared mainly on one platform, without guessing why.",
    )
    _paragraph(canvas, report["provider_caveat"], MARGIN, note_y - 76, CONTENT_WIDTH, size=8.2, color=MID, max_lines=4)


def _draw_cohort(canvas: Canvas, report: Mapping[str, Any]) -> None:
    cohort = report["diagnostic_cohort"]
    y = _page_title(
        canvas,
        "Why we compared these three AI-recommended businesses",
        "These businesses were selected because each adds a relevant, evidence-based comparison.",
    )
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
    _paragraph(
        canvas,
        "The full results remain unchanged. These three businesses were "
        "chosen only for the deeper website and customer-review comparison.",
        MARGIN, 88, CONTENT_WIDTH, size=8.5, color=MID, max_lines=4,
    )


def _draw_evidence_matrix(canvas: Canvas, report: Mapping[str, Any]) -> None:
    matrix = report["evidence_matrix"]
    businesses = matrix["businesses"]
    dimensions = matrix["dimensions"]
    y = _page_title(
        canvas,
        "What appears different about the businesses AI recommends",
        "A focused comparison of public information - not a claim that any one difference caused the AI result.",
    )
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
        _paragraph(canvas, _plain_dimension_label(dimension["label"]), MARGIN + 7, row_y - 17, label_width - 14, font=FONT_BOLD, size=8, color=NAVY, max_lines=3)
        x = MARGIN + label_width
        for business in businesses:
            display_value = _text(dimension["values"][business])
            if _text(dimension["label"]) == "AI visibility":
                display_value = display_value.replace(" SOR", " of named recommendations")
            _paragraph(canvas, display_value, x + 6, row_y - 15, value_width - 12, size=8, color=INK, max_lines=3)
            x += value_width
    note_y = top - 48 - len(dimensions) * row_height - 25
    _paragraph(canvas, matrix["note"], MARGIN, note_y, CONTENT_WIDTH, size=8, color=MID, max_lines=4)


def _draw_strengths(canvas: Canvas, report: Mapping[str, Any], client: str) -> None:
    strengths = report["strengths"]
    y = _page_title(
        canvas,
        f"{client} already has useful strengths to build on",
        "The opportunity is to make these strengths clearer and reinforce them consistently across public information.",
    )
    _label(canvas, "Observed evidence", MARGIN, y, "observed")
    card_width = (CONTENT_WIDTH - 16) / 2
    card_height = 180
    for index, item in enumerate(strengths[:4]):
        x = MARGIN + (index % 2) * (card_width + 16)
        card_y = y - 25 - (index // 2) * (card_height + 16)
        _card(canvas, x, card_y, card_width, card_height, fill=WHITE)
        canvas.setFillColor(TEAL)
        canvas.circle(x + 20, card_y - 23, 8, fill=1, stroke=0)
        _paragraph(canvas, _plain_strength_title(item["title"]), x + 38, card_y - 18, card_width - 52, font=FONT_BOLD, size=11, color=NAVY, max_lines=2)
        _paragraph(canvas, _plain_client_text(item["body"]), x + 14, card_y - 62, card_width - 28, size=8.7, color=INK, max_lines=6)
        _paragraph(canvas, f"Evidence: {_evidence_labels(item['evidence_refs'])}", x + 14, card_y - 138, card_width - 28, size=8, color=MID, max_lines=3)
    _paragraph(canvas, report["strengths_note"], MARGIN, 92, CONTENT_WIDTH, font=FONT_BOLD, size=9, color=NAVY, max_lines=4)


def _draw_review_quotes(canvas: Canvas, report: Mapping[str, Any], client: str) -> None:
    quotes = report["review_quotes"]
    y = _page_title(
        canvas,
        "What customers say in their own words",
        "These are exact quotations from the review sets used in this report. They bring the wider patterns to life.",
    )
    _label(canvas, "Customer voice", MARGIN, y, "observed")
    y -= 26
    if not quotes:
        _card(canvas, MARGIN, y, CONTENT_WIDTH, 150, fill=PALE)
        _paragraph(
            canvas,
            "No usable customer-review quotations were available when this report was prepared.",
            MARGIN + 22,
            y - 42,
            CONTENT_WIDTH - 44,
            font=FONT_BOLD,
            size=12,
            color=NAVY,
            max_lines=3,
        )
        _paragraph(
            canvas,
            "This is recorded as an evidence limitation. It is not treated as a negative customer result or a zero review score.",
            MARGIN + 22,
            y - 98,
            CONTENT_WIDTH - 44,
            size=9,
            color=MID,
            max_lines=4,
        )
        return
    card_height = 94
    for index, item in enumerate(quotes):
        card_y = y - index * (card_height + 10)
        is_client = item["business_name"] == client
        _card(canvas, MARGIN, card_y, CONTENT_WIDTH, card_height, fill=WHITE)
        canvas.setFillColor(TEAL if is_client else GOLD)
        canvas.roundRect(MARGIN, card_y - card_height, 7, card_height, 4, fill=1, stroke=0)
        label = f"{client} customer" if is_client else f"Comparison: {item['business_name']}"
        canvas.setFont(FONT_BOLD, 8)
        canvas.setFillColor(TEAL if is_client else GOLD)
        canvas.drawString(MARGIN + 18, card_y - 19, label.upper())
        _paragraph(
            canvas, f'"{item["quote"]}"', MARGIN + 18, card_y - 39,
            CONTENT_WIDTH - 185, font=FONT_BOLD, size=8.8, color=NAVY,
            leading=11.5, max_lines=4,
        )
        _paragraph(
            canvas, item["takeaway"], PAGE_WIDTH - MARGIN - 150, card_y - 31,
            132, size=8, color=MID, leading=10.5, max_lines=5,
        )
    _paragraph(
        canvas,
        "The quotations are examples, not the whole review picture. Recommendations in this "
        "report use the complete review sets and the wider website and AI evidence.",
        MARGIN, 69, CONTENT_WIDTH, size=8, color=MID, max_lines=3,
    )


def _draw_gaps(canvas: Canvas, report: Mapping[str, Any]) -> None:
    gaps = report["priority_gaps"]
    y = _page_title(
        canvas,
        "The biggest opportunities are clear and practical",
        "Four evidence-backed areas where the business can improve the information available to customers and digital systems.",
    )
    _label(canvas, "Observed evidence", MARGIN, y, "observed")
    row_height = 122
    for index, gap in enumerate(gaps[:4]):
        row_y = y - 24 - index * (row_height + 8)
        _card(canvas, MARGIN, row_y, CONTENT_WIDTH, row_height, fill=WHITE)
        canvas.setFont(FONT_BOLD, 16)
        canvas.setFillColor(GOLD)
        canvas.drawString(MARGIN + 16, row_y - 30, str(index + 1))
        left_x = MARGIN + 44
        divider_x = MARGIN + 244
        right_x = divider_x + 18
        right_width = PAGE_WIDTH - MARGIN - 16 - right_x
        _paragraph(canvas, _plain_gap_title(gap["title"]), left_x, row_y - 20, 184, font=FONT_BOLD, size=10, color=NAVY, max_lines=3)
        canvas.setStrokeColor(LINE)
        canvas.line(divider_x, row_y - 16, divider_x, row_y - row_height + 16)
        _paragraph(canvas, f"What we saw: {gap['observed']}", right_x, row_y - 20, right_width, size=8, color=INK, max_lines=3)
        _paragraph(canvas, f"What others show: {_plain_client_text(gap['comparison'])}", left_x, row_y - 68, 184, size=8, color=MID, max_lines=4)
        _paragraph(canvas, f"Why it is worth addressing: {_plain_client_text(gap['relevance'])}", right_x, row_y - 66, right_width, size=8, color=MID, leading=10, max_lines=4)
        canvas.setFont(FONT_BOLD, 8)
        canvas.setFillColor(TEAL)
        canvas.drawRightString(PAGE_WIDTH - MARGIN - 16, row_y - 105, f"Confidence: {gap['confidence']}")
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
        _paragraph(canvas, _plain_action_title(action["title"]), MARGIN + 52, card_y - 20, CONTENT_WIDTH - 160, font=FONT_BOLD, size=11, color=NAVY, max_lines=2)
        canvas.setFont(FONT_BOLD, 8)
        canvas.setFillColor(GOLD)
        canvas.drawRightString(PAGE_WIDTH - MARGIN - 14, card_y - 29, action["timing"])
        _paragraph(canvas, f"WHY THIS COMES FIRST\n{_action_reason(action, report)}", MARGIN + 52, card_y - 64, 212, size=8, color=MID, leading=11, max_lines=5)
        _paragraph(canvas, f"WHAT THIS INVOLVES\n{action['steps']}", MARGIN + 278, card_y - 64, CONTENT_WIDTH - 292, size=8, color=INK, leading=11, max_lines=6)
        _paragraph(canvas, f"THE PRACTICAL BENEFIT\n{_plain_client_text(action['intended_improvement'])}", MARGIN + 52, card_y - 128, CONTENT_WIDTH - 66, font=FONT_BOLD, size=8, color=TEAL, leading=10.5, max_lines=4)
    _paragraph(canvas, report["action_caveat"], MARGIN, 68, CONTENT_WIDTH, size=8, color=MID, max_lines=3)


def _draw_roadmap(canvas: Canvas, report: Mapping[str, Any]) -> None:
    data = report["roadmap"]
    y = _page_title(
        canvas,
        "What happens next",
        "Implement the foundations, allow the public evidence to establish, then repeat the same benchmark after meaningful change.",
    )
    _label(canvas, "Recommended action", MARGIN, y, "action")
    phases = data["phases"]
    phase_width = (CONTENT_WIDTH - 30) / 4
    for index, phase in enumerate(phases[:4]):
        x = MARGIN + index * (phase_width + 10)
        _card(canvas, x, y - 28, phase_width, 235, fill=WHITE)
        canvas.setFillColor(BLUE if index < 3 else TEAL)
        canvas.rect(x, y - 55, phase_width, 27, fill=1, stroke=0)
        _paragraph(canvas, phase["timing"], x + 8, y - 42, phase_width - 16, font=FONT_BOLD, size=8, color=WHITE, max_lines=1)
        _paragraph(canvas, _plain_roadmap_title(phase["title"]), x + 10, y - 78, phase_width - 20, font=FONT_BOLD, size=10, color=NAVY, max_lines=3)
        _paragraph(canvas, _plain_client_text(phase["body"]), x + 10, y - 132, phase_width - 20, size=8, color=INK, max_lines=7)
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
        *[
            f"{provider} model: {model}"
            for provider, model in data.get("models", {}).items()
        ],
        f"Prompts: {data['prompt_count']}",
        f"Repetitions: {data['repetitions']} per prompt/provider",
        f"Expected responses: {data['expected_responses']}",
        f"Complete responses: {data['complete_responses']}",
        f"Benchmark: {data['benchmark']}",
        "Live web search: disabled",
    ]
    _paragraph(canvas, "\n".join(benchmark_lines), MARGIN, y - 58, left_width, size=8, color=INK, leading=13, max_lines=12)
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


def _draw_prompts_tested(canvas: Canvas, payload: Mapping[str, Any]) -> None:
    prompts = _frozen_prompt_panel(payload)
    methodology = payload["methodology"]
    providers = len(methodology["providers"])
    repetitions = int(methodology["repetitions"])
    responses = len(payload["baseline_validation"]["responses"])
    y = _page_title(
        canvas,
        "Prompts tested",
        "The exact frozen questions used to produce this recommendation benchmark.",
    )
    _label(canvas, "Measured result", MARGIN, y, "measured")
    y -= 28
    row_height = 62
    label_width = 148
    for prompt in prompts:
        is_proposition = prompt["prompt_source"] == "client_proposition"
        accent = GOLD if is_proposition else BLUE
        fill = HexColor("#FFF8E9") if is_proposition else WHITE
        _card(canvas, MARGIN, y, CONTENT_WIDTH, row_height, fill=fill)
        canvas.setFillColor(accent)
        canvas.roundRect(MARGIN, y - row_height, 7, row_height, 4, fill=1, stroke=0)
        canvas.setFont(FONT_BOLD, 8)
        canvas.setFillColor(accent)
        canvas.drawString(MARGIN + 18, y - 20, f"{prompt['order']:02d}")
        kind = "CLIENT PROPOSITION" if is_proposition else "GENERAL INTENT"
        canvas.setFont(FONT_BOLD, 8)
        canvas.drawString(MARGIN + 42, y - 20, kind)
        _paragraph(
            canvas, prompt["prompt_category"], MARGIN + 18, y - 39,
            label_width - 28, font=FONT_BOLD, size=8, color=NAVY, max_lines=2,
        )
        _paragraph(
            canvas, prompt["prompt_text"], MARGIN + label_width, y - 23,
            CONTENT_WIDTH - label_width - 18, font=FONT_BOLD, size=10,
            color=INK, leading=13, max_lines=3,
        )
        y -= row_height + 8
    note = (
        f"Each prompt was run {repetitions} times against each of the "
        f"{providers} providers, producing {responses} frozen responses. "
        "The wording above is reproduced verbatim from the baseline evidence."
    )
    _card(canvas, MARGIN, y + 2, CONTENT_WIDTH, 55, fill=PALE)
    _paragraph(
        canvas, note, MARGIN + 16, y - 17, CONTENT_WIDTH - 32,
        size=8.5, color=NAVY, leading=12, max_lines=3,
    )


def _draw_question_details(
    canvas: Canvas,
    report: Mapping[str, Any],
    client: str,
    *,
    part: int,
) -> None:
    rows = report["question_performance"][(part - 1) * 4:part * 4]
    y = _page_title(
        canvas,
        f"Question-by-question detail ({part} of 2)",
        "The leading business for each AI platform, based on three answers per platform. Best position is shown where available.",
    )
    _label(canvas, "Detailed results", MARGIN, y, "measured")
    y -= 27
    card_height = 128
    for index, row in enumerate(rows):
        card_y = y - index * (card_height + 11)
        _card(canvas, MARGIN, card_y, CONTENT_WIDTH, card_height, fill=WHITE)
        canvas.setFillColor(BLUE)
        canvas.roundRect(MARGIN, card_y - card_height, 7, card_height, 4, fill=1, stroke=0)
        canvas.setFont(FONT_BOLD, 8)
        canvas.setFillColor(BLUE)
        canvas.drawString(
            MARGIN + 18, card_y - 18,
            f"QUESTION {row['order']:02d}  |  {_text(row['prompt_category']).upper()}",
        )
        _paragraph(
            canvas, row["prompt_text"], MARGIN + 18, card_y - 39,
            CONTENT_WIDTH - 36, font=FONT_BOLD, size=9.5,
            color=NAVY, leading=12.5, max_lines=2,
        )
        target_appearances = int(row["target_appearances"])
        target_result = f"{client}: {target_appearances} of {row['answer_count']} answers"
        if row.get("target_best_position"):
            target_result += f" | best position #{int(row['target_best_position'])}"
        canvas.setFont(FONT_BOLD, 8)
        canvas.setFillColor(TEAL if target_appearances else RED)
        canvas.drawString(MARGIN + 18, card_y - 69, target_result)
        provider_width = (CONTENT_WIDTH - 36) / 3
        for provider_index, provider_result in enumerate(row["provider_results"]):
            x = MARGIN + 18 + provider_index * provider_width
            leaders = provider_result["leaders"]
            if leaders:
                leader = leaders[0]
                detail = (
                    f"{leader['business_name']}"
                    f"{' [identity unverified]' if leader.get('identity_status') == 'unresolved' else ''}\n"
                    f"{leader['appearances']} of {provider_result['answer_count']} answers | "
                    f"best #{int(leader['best_position'])}"
                )
            else:
                detail = "No named business recommendation"
            _paragraph(
                canvas, f"{provider_result['provider']}\n{detail}",
                x, card_y - 91, provider_width - 10,
                size=8, color=INK, leading=10, max_lines=4,
            )
    _paragraph(
        canvas,
        "Appearances show how many answers included the business. Best position is the "
        "highest place it reached in any of those answers.",
        MARGIN, 72, CONTENT_WIDTH, size=8, color=MID, max_lines=3,
    )


def render_poc_audit_pdf(payload: Mapping[str, Any]) -> bytes:
    """Render a deterministic PDF from one frozen payload only."""

    report = _validate_report_contract(payload)
    accessible_beta = report.get("report_format") == "beta_accessible_v2"
    page_count = BETA_REPORT_PAGE_COUNT if accessible_beta else LEGACY_REPORT_PAGE_COUNT
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
    page = 2
    _new_page(canvas, page, client_name, audit_date, page_count)
    if accessible_beta:
        _draw_introduction(canvas, report, client_name)
        page += 1
        _new_page(canvas, page, client_name, audit_date, page_count)
    _draw_executive(canvas, report, client_name)
    page += 1
    _new_page(canvas, page, client_name, audit_date, page_count)
    if accessible_beta:
        _draw_question_visibility(canvas, payload, report, client_name)
    else:
        _draw_visibility(canvas, payload, report, client_name)
    page += 1
    _new_page(canvas, page, client_name, audit_date, page_count)
    _draw_market(canvas, report, client_name)
    page += 1
    _new_page(canvas, page, client_name, audit_date, page_count)
    _draw_provider_comparison(canvas, report, client_name)
    page += 1
    _new_page(canvas, page, client_name, audit_date, page_count)
    _draw_cohort(canvas, report)
    page += 1
    _new_page(canvas, page, client_name, audit_date, page_count)
    _draw_evidence_matrix(canvas, report)
    page += 1
    _new_page(canvas, page, client_name, audit_date, page_count)
    _draw_strengths(canvas, report, client_name)
    page += 1
    _new_page(canvas, page, client_name, audit_date, page_count)
    if accessible_beta:
        _draw_review_quotes(canvas, report, client_name)
        page += 1
        _new_page(canvas, page, client_name, audit_date, page_count)
    _draw_gaps(canvas, report)
    page += 1
    _new_page(canvas, page, client_name, audit_date, page_count)
    _draw_actions(canvas, report)
    page += 1
    _new_page(canvas, page, client_name, audit_date, page_count)
    _draw_roadmap(canvas, report)
    page += 1
    _new_page(canvas, page, client_name, audit_date, page_count)
    _draw_methodology(canvas, report)
    page += 1
    _new_page(canvas, page, client_name, audit_date, page_count)
    _draw_prompts_tested(canvas, payload)
    if accessible_beta:
        page += 1
        _new_page(canvas, page, client_name, audit_date, page_count)
        _draw_question_details(canvas, report, client_name, part=1)
        page += 1
        _new_page(canvas, page, client_name, audit_date, page_count)
        _draw_question_details(canvas, report, client_name, part=2)
    _footer(canvas, page, client_name, audit_date, page_count)
    if page != page_count:
        raise PdfRenderError(
            f"Rendered page plan ended at {page}; expected {page_count} pages"
        )
    canvas.save()
    return output.getvalue()
