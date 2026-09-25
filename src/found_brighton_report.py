"""Populate the Found in Brighton Word layout from one saved GSO scan."""

from __future__ import annotations

from collections import defaultdict
from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any

from docx import Document
from docx.shared import Inches
from PIL import Image, ImageDraw, ImageFont

from gso_report.metrics import kpis, tables
from gso_report.schema import Report


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = ROOT / "found_in_brighton_report"
NAVY = "#173B48"
TEAL = "#168C92"
CORAL = "#CD7052"
GREY = "#617079"


def _pct(value: Any) -> str:
    return "N/A" if value is None else f"{value:g}%"


def _num(value: Any) -> str:
    return "N/A" if value is None else f"{value:g}"


def _top_three_rate(observations, brand_id: str) -> float | None:
    successful = [obs for obs in observations if obs.status == "ok"]
    ranked = [
        obs for obs in successful
        if any(m.brand_id == brand_id and m.recommended and m.recommendation_position is not None for m in obs.mentions)
    ]
    if not ranked:
        return None
    top_three = sum(
        any(m.brand_id == brand_id and m.recommended and m.recommendation_position is not None and m.recommendation_position <= 3 for m in obs.mentions)
        for obs in successful
    )
    return round(100 * top_three / len(successful), 2) if successful else None


def _font(size: int, bold: bool = False):
    candidates = [
        f"/System/Library/Fonts/Supplemental/Arial{' Bold' if bold else ''}.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _chart(name: str, data: dict[str, Any]) -> bytes:
    """Create scan-derived images to replace all static performance charts."""
    width, height = (1800, 245 if name == "kpis" else 560 if name in {"platform", "trend"} else 300)
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    ink = "#172B33"
    if name == "kpis":
        items = [
            (_pct(data["kpis"].get("Mention rate %")), "Mention rate"),
            (_pct(data["kpis"].get("Recommendation rate %")), "Recommendation rate"),
            (_pct(data["kpis"].get("Tracked share of voice %")), "Tracked share of voice"),
        ]
        for i, (value, label) in enumerate(items):
            x = i * 600 + 5
            draw.text((x, 10), value, font=_font(88, True), fill=NAVY)
            draw.text((x, 125), label, font=_font(30), fill=ink)
        draw.text((5, 196), "Selected scan · no matched previous period", font=_font(24), fill=GREY)
    elif name == "platform":
        providers = data["providers"]
        start, end = 370, 1560
        for pct in (0, 25, 50, 75, 100):
            x = start + (end - start) * pct / 100
            draw.line((x, 65, x, 485), fill="#E1E7E7", width=2)
            draw.text((x, 510), f"{pct}%", font=_font(24), fill=GREY, anchor="mm")
        for i, row in enumerate(providers[:3]):
            y = 80 + i * 130
            label = str(row["Provider"])
            draw.text((0, y + 18), label, font=_font(34, True), fill=ink)
            for offset, key, color in ((0, "Mention rate %", NAVY), (48, "Recommendation rate %", TEAL)):
                value = row.get(key)
                if value is None:
                    draw.text((start + 10, y + offset), "N/A", font=_font(25), fill=GREY)
                    continue
                x = start + (end - start) * float(value) / 100
                draw.rounded_rectangle((start, y + offset, max(start + 4, x), y + offset + 30), radius=5, fill=color)
                draw.text((x + 12, y + offset - 2), _pct(value), font=_font(25, True), fill=color)
        for x, label, color in ((370, "Mention rate", NAVY), (760, "Recommendation rate", TEAL)):
            draw.rectangle((x, 15, x + 22, 37), fill=color)
            draw.text((x + 34, 11), label, font=_font(23), fill=ink)
    elif name == "voice":
        brands = data["benchmarks"][:5]
        values = [max(0.0, min(100.0, float(row.get("Tracked share of voice %") or 0))) for row in brands]
        colors = [TEAL, NAVY, "#58818D", "#9BB7BC", "#DCE6E7"]
        total = sum(values) or 1
        x = 0
        for i, (row, value) in enumerate(zip(brands, values)):
            w = 1800 * value / total
            draw.rectangle((x, 20, x + w - 4, 116), fill=colors[i % len(colors)])
            draw.text((x + w / 2, 68), _pct(row.get("Tracked share of voice %")), font=_font(26, True),
                      fill="white" if i < 3 else ink, anchor="mm")
            x += w
        for i, row in enumerate(brands):
            col, line = i % 3, i // 3
            x, y = col * 595, 155 + line * 62
            draw.rectangle((x, y, x + 24, y + 24), fill=colors[i % len(colors)])
            label = str(row["Brand"])
            draw.text((x + 38, y - 3), label[:35], font=_font(24), fill=ink)
    else:  # Single-scan cross-section by intent, never a fabricated time trend.
        rows = data["intent_rows"]
        left, right, top, bottom = 150, 1660, 65, 400
        for pct in (0, 25, 50, 75, 100):
            y = bottom - (bottom - top) * pct / 100
            draw.line((left, y, right, y), fill="#E1E7E7", width=2)
            draw.text((105, y), f"{pct}%", font=_font(22), fill=GREY, anchor="rm")
        points = []
        for i, row in enumerate(rows[:4]):
            x = left + (right - left) * (i / max(len(rows[:4]) - 1, 1))
            value = row.get("Mention rate %")
            if value is None:
                draw.text((x, bottom + 35), str(row["Intent"])[:15], font=_font(20), fill=ink, anchor="mm")
                draw.text((x, 220), "N/A", font=_font(24), fill=GREY, anchor="mm")
                continue
            y = bottom - (bottom - top) * float(value) / 100
            points.append((x, y))
            draw.ellipse((x - 9, y - 9, x + 9, y + 9), fill=TEAL)
            draw.text((x, y - 28), _pct(value), font=_font(23, True), fill=TEAL, anchor="mm")
            draw.text((x, bottom + 35), str(row["Intent"])[:15], font=_font(20), fill=ink, anchor="mm")
        if len(points) > 1:
            draw.line(points, fill=TEAL, width=6)
        draw.text((left, 500), "Client mention rate · one selected scan", font=_font(24), fill=ink)
    output = BytesIO()
    image.save(output, format="PNG", dpi=(300, 300))
    return output.getvalue()


def _set_table(table, rows: list[list[str]]) -> None:
    """Replace body rows while preserving the template's header and table styling."""
    from copy import deepcopy

    body_cell_properties = [
        deepcopy(cell._tc.tcPr) if cell._tc.tcPr is not None else None
        for cell in (table.rows[1].cells if len(table.rows) > 1 else table.rows[0].cells)
    ]
    body_run = None
    if len(table.rows) > 1 and table.rows[1].cells and table.rows[1].cells[0].paragraphs:
        first_runs = table.rows[1].cells[0].paragraphs[0].runs
        if first_runs:
            body_run = first_runs[0]
    while len(table.rows) > 1:
        table._tbl.remove(table.rows[-1]._tr)
    for values in rows:
        new_row = table.add_row()
        new_row._tr.get_or_add_trPr()
        for index, value in enumerate(values):
            cell = new_row.cells[index]
            cell.text = str(value)
            tc_pr = body_cell_properties[index]
            if tc_pr is not None:
                existing = cell._tc.tcPr
                for child in list(existing):
                    existing.remove(child)
                for child in tc_pr:
                    existing.append(deepcopy(child))
            for paragraph in cell.paragraphs:
                for run in paragraph.runs:
                    run.font.name = "Arial"
                    from docx.shared import Pt
                    run.font.size = Pt(9)
                    if body_run is not None:
                        run.font.color.rgb = body_run.font.color.rgb
    # The row settings on newly-added rows mirror the template body row.
    if len(table.rows) > 1:
        body_pr = table.rows[1]._tr.trPr
        if body_pr is not None:
            for row in table.rows[2:]:
                for child in body_pr:
                    if child.tag.endswith("cantSplit") and row._tr.trPr.find(child.tag) is None:
                        row._tr.trPr.append(deepcopy(child))


def _replace_paragraph_text(document, replacements: dict[str, str]) -> None:
    replacements = dict(sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True))
    for paragraph in document.paragraphs:
        text = paragraph.text
        for old, new in replacements.items():
            if old in text:
                text = text.replace(old, new)
        if text != paragraph.text:
            if paragraph.runs:
                paragraph.runs[0].text = text
                for run in paragraph.runs[1:]:
                    run.text = ""
            else:
                paragraph.add_run(text)
    for section in document.sections:
        for paragraph in section.footer.paragraphs:
            for run in paragraph.runs:
                run.text = run.text.replace("CLIENT REPORT TEMPLATE  •  ILLUSTRATIVE PLACEHOLDERS", "SELECTED SCAN RESULTS  •  SAVED EVIDENCE")


def _data(report: Report) -> dict[str, Any]:
    observations = report.observations
    metric = kpis(report, observations)
    report_tables = tables(report, observations)
    prompt_by_id = {prompt.id: prompt for prompt in report.prompts}
    successful = [obs for obs in observations if obs.status == "ok"]
    client_mentions = [mention for obs in successful for mention in obs.mentions if mention.brand_id == report.client_id]
    intent_rows = []
    for intent in ("discovery", "comparison", "transactional", "branded"):
        prompt_ids = {prompt.id for prompt in report.prompts if prompt.intent == intent}
        group = [obs for obs in observations if obs.prompt_id in prompt_ids]
        if group:
            intent_rows.append({"Intent": intent.title(), **kpis(report, group)})
    providers = report_tables["Provider performance"]
    brands = report_tables["Competitor benchmarks"]
    return {
        "kpis": metric, "providers": providers, "benchmarks": brands,
        "source_rows": report_tables["Sources"], "prompts": report.prompts,
        "prompt_by_id": prompt_by_id, "observations": observations,
        "successful": successful, "client_mentions": client_mentions,
        "intent_rows": intent_rows,
    }


def _fill(document, report: Report, data: dict[str, Any]) -> None:
    metrics = data["kpis"]
    observations = data["observations"]
    by_header = {tuple(cell.text for cell in table.rows[0].cells): table for table in document.tables}
    _set_table(by_header[("Measure", "Current", "Previous", "Change")], [
        ["Mention rate", _pct(metrics["Mention rate %"]), "No matched baseline", "N/A"],
        ["Recommendation rate", _pct(metrics["Recommendation rate %"]), "No matched baseline", "N/A"],
        ["Competitive share of voice", _pct(metrics["Tracked share of voice %"]), "No matched baseline", "N/A"],
        ["Average recorded mention position", _num(metrics["Average mention position"]), "No matched baseline", "N/A"],
        ["First recommendation rate", _pct(metrics["First recommendation rate %"]), "No matched baseline", "N/A"],
        ["Top 3 recommendation rate", _pct(_top_three_rate(report.observations, report.client_id)), "No matched baseline", "N/A"],
        ["Owned-site citation rate", _pct(metrics["Owned-site citation rate %"]), "No matched baseline", "N/A"],
        ["Citation evidence coverage", _pct(metrics["Citation evidence coverage %"]), "No matched baseline", "N/A"],
        ["Recommendation persistence", _pct(metrics["Recommendation persistence %"]), "N/A", "N/A"],
        ["Successful / failed or refused answers", f"{metrics['Successful answers']} / {metrics['Failed/refused runs']}", "N/A", "N/A"],
    ])
    provider_table = by_header[("Measure", "ChatGPT", "Claude", "Gemini")]
    provider_table.rows[0].cells[0].text = "Measured result"
    for column, provider in enumerate(("OpenAI", "Claude", "Gemini"), start=1):
        provider_table.rows[0].cells[column].text = provider
    providers = {row["Provider"]: row for row in data["providers"]}
    provider_metrics = [
        ("Successful answers", "Successful answers", False),
        ("Mention rate", "Mention rate %", True),
        ("Recommendation rate", "Recommendation rate %", True),
        ("Tracked share of voice", "Tracked share of voice %", True),
        ("Average recorded position", "Average mention position", False),
        ("First recommendation rate", "First recommendation rate %", True),
        ("Top 3 recommendation rate", "__top_three__", True),
        ("Owned-site citation rate", "Owned-site citation rate %", True),
    ]
    _set_table(provider_table, [[label] + [
        (_pct(_top_three_rate([obs for obs in data["observations"] if obs.provider == p], report.client_id)) if key == "__top_three__"
         else (_pct(providers.get(p, {}).get(key)) if percent else _num(providers.get(p, {}).get(key))))
        for p in ("OpenAI", "Claude", "Gemini")
    ] for label, key, percent in provider_metrics])

    valid = data["successful"]
    recommendations = sum(any(m.brand_id == report.client_id and m.recommended for m in obs.mentions) for obs in valid)
    mentions = sum(any(m.brand_id == report.client_id for m in obs.mentions) for obs in valid)
    mention_only = max(0, mentions - recommendations)
    absent = max(0, len(valid) - mentions)
    classification_table = by_header[("Response classification", "Illustrative count", "Share")]
    classification_table.rows[0].cells[1].text = "Count"
    _set_table(classification_table, [
        ["Explicitly recommended", str(recommendations), _pct(100 * recommendations / len(valid) if valid else None)],
        ["Mentioned, not recommended", str(mention_only), _pct(100 * mention_only / len(valid) if valid else None)],
        ["Not mentioned", str(absent), _pct(100 * absent / len(valid) if valid else None)],
        ["Successful answers", str(len(valid)), _pct(100 if valid else None)],
        ["Failed / refused", str(metrics["Failed/refused runs"]), "Excluded from rates"],
    ])
    _set_table(by_header[("Indicator", "Result", "Evidence required")], [
        ["Average mention position", _num(metrics["Average mention position"]), "Recorded ranks only"],
        ["First recommendation rate", _pct(metrics["First recommendation rate %"]), "Rank 1 / successful answers"],
        ["Top 3 recommendation rate", _pct(_top_three_rate(observations, report.client_id)), "Rank 1–3 recommendations / successful answers"],
    ])

    prompts = data["prompts"]
    prompt_rows = []
    for prompt in prompts[:12]:
        group = [obs for obs in observations if obs.prompt_id == prompt.id]
        visible = sum(any(m.brand_id == report.client_id for m in obs.mentions) for obs in group if obs.status == "ok")
        ok_count = sum(obs.status == "ok" for obs in group)
        prompt_rows.append([prompt.intent.title(), prompt.text, f"{visible} / {ok_count} successful answers"])
    prompt_table = by_header[("Topic or intent", "Example prompt", "Coverage")]
    prompt_table.rows[0].cells[1].text = "Exact saved prompt"
    _set_table(prompt_table, prompt_rows or [["N/A", "No prompts", "N/A"]])
    prompt_summary = [[row["Intent"], str(sum(p.intent == row["Intent"].lower() for p in prompts)), str(sum(p.intent == row["Intent"].lower() and any(m.brand_id == report.client_id for o in observations if o.prompt_id == p.id and o.status == "ok" for m in o.mentions) for p in prompts)), "Measured in prompt panel", "Not scored"] for row in data["intent_rows"]]
    summary_table = by_header[("Topic", "Prompts tested", "Prompts visible", "Coverage", "Value")]
    summary_table.rows[0].cells[0].text = "Intent"
    _set_table(summary_table, prompt_summary or [["N/A", "0", "0", "N/A", "Not measured"]])

    benchmark_table = by_header[("Business", "Mention rate", "Recommendation", "Share of voice", "Avg position")]
    _set_table(benchmark_table, [[
        row["Brand"], _pct(row["Mention rate %"]), _pct(row["Recommendation rate %"]),
        _pct(row["Tracked share of voice %"]), _num(row["Average mention position"]),
    ] for row in data["benchmarks"]])
    _set_table(by_header[("Gap", "Evidence to insert", "Client response")], [[
        "Observed prompt", prompt.text, "Review answer evidence before proposing action"
    ] for prompt in prompts[:5]] or [["N/A", "No prompt data", "Not measured"]])

    cite_obs = [obs for obs in valid if obs.citation_status == "measured"]
    cited_client = sum(any(c.source_type == "owned" for c in obs.citations) for obs in cite_obs)
    any_cite = sum(bool(obs.citations) for obs in cite_obs)
    owned_urls = {c.url for obs in cite_obs for c in obs.citations if c.source_type == "owned"}
    _set_table(by_header[("Source measure", "Result")], [
        ["Owned-site citation rate", _pct(metrics["Owned-site citation rate %"])],
        ["Answers citing client website", f"{cited_client} / {len(cite_obs)} measured citation answers"],
        ["Unique owned URLs cited", str(len(owned_urls))],
        ["Answers with any captured citation", f"{any_cite} / {len(cite_obs)} measured citation answers"],
        ["Citation capture coverage", _pct(metrics["Citation evidence coverage %"])],
    ])
    url_rows = []
    url_stats: dict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "providers": set(), "prompts": set()})
    for obs in cite_obs:
        for citation in {item.url: item for item in obs.citations}.values():
            row = url_stats[citation.url]
            row["count"] += 1
            row["providers"].add(obs.provider)
            row["prompts"].add(data["prompt_by_id"][obs.prompt_id].text[:45])
    for url, stats in sorted(url_stats.items(), key=lambda item: -item[1]["count"])[:10]:
        url_rows.append([url, str(stats["count"]), ", ".join(sorted(stats["providers"])), ", ".join(sorted(stats["prompts"])[:2])])
    _set_table(by_header[("Owned page URL", "Responses citing page", "Platform", "Topic")], url_rows or [["No citation URLs captured", "0", "N/A", "Not measured"]])

    # The supplied layout's progress table is repurposed for this scan's intent breakdown.
    # One scan has no historical periods, so never fill its space with an invented trend.
    intent_table = by_header[("Work item", "Delivery status", "Observed change", "Next step")]
    for column, value in enumerate(("Prompt intent", "Mention rate", "Recommendation rate", "Successful answers")):
        intent_table.rows[0].cells[column].text = value
    _set_table(intent_table, [[row["Intent"], _pct(row.get("Mention rate %")), _pct(row.get("Recommendation rate %")), str(row.get("Successful answers", 0))] for row in data["intent_rows"]] or [["No grouped results", "N/A", "N/A", "0"]])

    # Append exact question wording and captured source evidence to the existing editable appendices.
    prompt_appendix = by_header[("Prompt register field", "Value to record")]
    prompt_appendix.rows[0].cells[0].text = "Prompt ID / intent"
    _set_table(prompt_appendix, [[prompt.id, f"{prompt.intent.title()} · {prompt.text}"] for prompt in prompts] or [["N/A", "No prompts saved"]])
    source_appendix = by_header[("Source register field", "Value to record")]
    source_appendix.rows[0].cells[0].text = "Citation source"
    _set_table(source_appendix, [[row["Domain"], f"{row['Answers citing domain']} captured answers · {row['Types']} · client-owned: {row['Client owned']}"] for row in data["source_rows"][:20]] or [["No citation domains captured", "Citation capture unavailable or no URLs observed"]])

    methodology = by_header[("Metric", "Calculation and boundary")]
    _set_table(methodology, [
        ["Mention rate", "Successful answers containing the client / all successful answers. Each client business is counted once per answer."],
        ["Recommendation rate", "Successful answers explicitly recommending the client / all successful answers. Mention alone is not a recommendation."],
        ["Tracked share of voice", "Client mentions / mentions of all businesses present in this report's tracked set. It is not the whole local market."],
        ["Recorded position", "Mean of explicit recorded positions only. Unranked prose is not assigned an inferred position."],
        ["Citations", "Owned-site rate uses captured citation evidence and configured client domain. Unavailable capture is N/A, not zero."],
        ["Failed and refused calls", "Excluded from rates and shown separately. Successful response counts are reported for every provider."],
        ["Previous period and trend", "No matched baseline is included. The intent breakdown on page 13 is a cross-section of this one scan, not a time trend."],
    ])

    provider_names = ", ".join(dict.fromkeys(obs.provider for obs in observations))
    first_date = min((obs.collected_at.date() for obs in observations), default=report.start_date)
    last_date = max((obs.collected_at.date() for obs in observations), default=report.end_date)
    model_summary = ", ".join(dict.fromkeys(f"{obs.provider}: {obs.model}" for obs in observations))
    tracked_names = ", ".join(brand.name for brand in report.brands)
    repetitions = max((sum(obs.prompt_id == prompt.id for obs in observations) // max(len({obs.provider for obs in observations}), 1) for prompt in prompts), default=0)
    _replace_paragraph_text(document, {
        "CLIENT REPORT TEMPLATE  •  ILLUSTRATIVE PLACEHOLDERS": "SELECTED SCAN RESULTS  •  SAVED EVIDENCE",
        "TEMPLATE ONLY. All numbers, example findings and example actions are illustrative placeholders, not measured client results. Replace bracketed fields and example data before issuing a completed report. No AI platform audit has been performed for this template.": "Visibility results in this report are calculated from the selected saved scan. Pages covering source authority, brand accuracy, local profiles, reviews, website readiness and actions are analyst worksheets; this scan did not measure those items.",
        "ILLUSTRATIVE TEMPLATE. All sample figures are placeholders, not client results. Replace sample data and bracketed fields before sharing a completed report.": "Visibility results are calculated from the selected saved scan. The source-authority, brand-accuracy, local profile, review, website-readiness and action pages are analyst worksheets, not measurements from this scan.",
        "[CLIENT NAME]": next(b.name for b in report.brands if b.id == report.client_id),
        "[BUSINESS CATEGORY]": report.category,
        "[PRIMARY MARKET]": report.market,
        "[START DATE]": first_date.isoformat(),
        "[END DATE]": last_date.isoformat(),
        "[DATE]": last_date.isoformat(),
        "[PREVIOUS PERIOD]": "No matched baseline",
        "[MONTH YEAR]": last_date.strftime("%B %Y"),
        "[X]": provider_names,
        "Panel: [N] unbranded prompts × [N] repeats × [N] platforms; separate branded panel [N]. Dates [range]; language [X]; location [X]; model and search mode [X]. Use fresh sessions and record personalisation. Log failures; exclude technical failures, but retain valid no result answers. Report successful runs against planned runs.": f"Panel: {len(prompts)} saved prompts, up to {repetitions} repetitions and {len({obs.provider for obs in observations})} provider(s). Dates {first_date.isoformat()} to {last_date.isoformat()}; market {report.market}. These are saved API observations, not consumer-app visibility. Failed and refused calls are reported separately and excluded from rates.",
        "[Product / model / search mode / account tier / location / dates]": f"{model_summary}; saved API scan; {report.market}; {first_date.isoformat()} to {last_date.isoformat()}",
        "[Insert the main finding, its commercial importance and the one action to approve this month.]": "Review the answer evidence and decide whether the measured gaps justify a separate website, source or brand audit.",
        "Discovery  [Where customers are likely to encounter the business in the tested panel.]\nConsideration  [Whether the answer presents the business as a suitable choice.]\nAction  [The highest priority improvement, linked to evidence and an owner.]": "Discovery and recommendation rates describe the selected scan's prompts. Decide next steps only after reviewing the exact answers and captured sources.",
        "[PROMPT] → [CURRENT RESULT] → [COMPETITOR / SOURCE] → [RECOMMENDED ACTION].\nUse relevance to the client’s services and customer value to prioritise the gap. Prompt counts are not search volumes.": "Use Appendix A to review exact questions with lower visibility. Prompt counts are not search volumes; any proposed action needs separate evidence review.",
        "Competitor set  [Names and inclusion criteria].\nNew businesses found  [Names and frequency]. Track these separately until added to a revised baseline. A larger competitor set changes share of voice even if the client’s mention rate is unchanged.": f"Tracked businesses: {tracked_names}. Share of voice is relative to this set and not the whole local market. A changed tracked set changes the share-of-voice denominator.",
        "Test configuration  [Product / model / search mode / account tier / location / dates]. Capture each configuration separately in Appendix A.": f"Test configuration: {model_summary}; saved API scan in {report.market}, {first_date.isoformat()} to {last_date.isoformat()}.",
        "Commercial outcomes where measurable": "Commercial outcomes — not measured by this visibility scan",
        "Identifiable AI referral visits  [N]. Enquiries  [N]. Qualified leads  [N]. Bookings or revenue  [N / £X]. Source: [analytics / CRM / attribution rule]. Compare like for like dates and explain tracking coverage.": "Referral visits, enquiries, leads, bookings and revenue are not included in the saved visibility scan.",
        "[Client] is [overall assessment] for the customer questions in this reporting panel. [Explain the strongest result and the most valuable gap in two sentences.]": f"Across {metrics['Successful answers']} successful answers, {metrics['Mention rate %'] if metrics['Mention rate %'] is not None else 'N/A'}% mentioned the business and {metrics['Recommendation rate %'] if metrics['Recommendation rate %'] is not None else 'N/A'}% explicitly recommended it. Results describe this saved prompt panel and its recorded provider setup.",
        "Illustrative scorecard only. pp means percentage points. Current example panel: 300 valid unbranded responses. Comparisons require the same panel and settings. See page 14 for denominators.": "All current metrics use the saved scan. Previous-period comparisons are unavailable because no matched comparison run was selected. N/A means this scan did not capture the measure.",
        "[XX/100 or Not calculated]. A summary of eight published components, not an official platform score. Show only when every component has a documented calculation and the same method is used across periods. See page 14.": "No composite agency index is calculated for this report.",
        "Illustrative chart. Scale 0–100%; labels show the exact values. Replace bar lengths and figures together.": "Measured values from the selected saved scan. Provider-level denominators may differ; each rate uses successful answers for that provider.",
        "Illustrative benchmark: 300 responses and 675 business response mentions across the five businesses. Count each business at most once per response. Mention rates can total more than 100%; share of voice totals 100%, subject to rounding.": "Business-level rates use successful answers; tracked share of voice uses mentions among businesses in this report's tracked set. The chart shows the five most visible businesses; the table gives the complete tracked set. This is not the whole local market.",
        "Owned site citation rate 20% — illustrative": f"Owned-site citation rate {_pct(metrics['Owned-site citation rate %'])}",
        "Responses citing the client website 60 of 300 — illustrative": f"Responses citing the client website {cited_client} / {len(cite_obs)} with measured citation capture",
        "Illustrative trend only. Use equal comparison windows and the same prompt panel. Annotate model changes, search mode changes and material changes to the test conditions.": "This is a single-scan breakdown by prompt intent, not a time trend. There is no previous reporting period in this scan.",
        "Illustrative trend": "Current scan by intent",
        "The example recommendation rate is 30%: 90 of 300 responses. The mention rate is 45%: 135 of 300. Classify each response once using the categories above.": f"This scan recorded {recommendations} recommendations and {mentions} client mentions across {len(valid)} successful answers. The response categories above are mutually exclusive.",
        "Illustrative prompt: “Recommend a [service] in [area].”\nRepeat results: Recommended / Recommended / Absent / Recommended / Absent.\nRecommendation consistency: 3 of 5 runs, or 60%, for this prompt and platform.": "Repeat results are calculated from saved answer records. Recommendation persistence is N/A unless a prompt and provider group has at least two successful repeats.",
        "[X of Y prompt and platform groups] recommended the business on at least 4 of 5 runs. Show the repeat count, spread across groups and any unstable high value questions.": f"Measured recommendation persistence: {_pct(metrics['Recommendation persistence %'])}, the mean recommendation rate of prompt and provider groups with at least two successful repeats.",
        "Progress since the last report": "Visibility by prompt intent",
        "Delivery and observed outcomes": "Visibility rates by prompt intent",
        "Optional index formula  ": "Optional index formula (not calculated in this report): ",
        "Separate work delivered from changes observed. AI visibility changes alone do not establish that an individual action caused the movement.": "Compare the current scan's intent groups. No previous matched scan was selected, so change over time is not measured.",
        "Third party opportunities and authority": "Source authority worksheet — not measured",
        "Priorities and the 90 day roadmap": "Analyst action worksheet — not measured",
        "Brand accuracy and perception": "Brand accuracy worksheet — not measured",
        "Local visibility and reputation": "Local and reputation worksheet — not measured",
        "Content and technical readiness": "Website readiness worksheet — not measured",
        "Prioritise relevant sources actually observed in the response evidence. Distinguish a verified citation gap from a potential authority opportunity that has not yet appeared in the test panel.": "Not measured by this visibility scan. Analyst worksheet for a separate source-authority review; citation appearance alone does not establish source quality or authority.",
        "Check whether answers describe the right business and whether the information matches approved facts. Use the separate branded prompt panel for this diagnostic.": "Not measured by this visibility scan. Analyst worksheet for a separate review against client-approved business facts.",
        "Compare the areas the client actually serves. Keep explicit place names separate from device based “near me” tests, and record the location and time used.": "Not measured by this visibility scan. This report does not evaluate local profile, review, or physical-proximity signals.",
        "Connect each high value question to a useful page and check whether the published evidence is accessible, accurate and supported. Treat this as a readiness audit, separate from measured AI visibility.": "Not measured by this visibility scan. Analyst worksheet for a separate website content and technical readiness audit.",
        "Approve a small number of evidence backed actions. Each needs an owner, a delivery date and a measure that can be checked in the next report.": "Not generated from this visibility scan. Complete this worksheet only after reviewing the saved answer and source evidence.",
    })

    # The rest of the supplied format is retained as completion worksheets and made explicit.
    for paragraph in document.paragraphs:
        if paragraph.text.startswith(("Prioritisation rule", "Review protocol", "Include the prompt register")):
            continue
    for index, shape in enumerate(document.inline_shapes):
        if index == 0:
            continue  # Branded cover artwork carries no metric values.
        chart_name = {1: "kpis", 2: "platform", 3: "voice", 4: "trend"}.get(index)
        if not chart_name:
            continue
        rid = shape._inline.graphic.graphicData.pic.blipFill.blip.embed
        document.part.related_parts[rid]._blob = _chart(chart_name, data)

    document.core_properties.title = "Found in Brighton AI Visibility Report"
    document.core_properties.subject = f"Measured results from saved scan {report.start_date} to {report.end_date}"


def generate_filled_report(report: Report, *, agency: str = "Found in Brighton AI", website: str = "") -> bytes:
    """Run the included layout generator, replace its sample data, and return a DOCX."""
    data = _data(report)
    client = next(brand for brand in report.brands if brand.id == report.client_id)
    with tempfile.TemporaryDirectory(prefix="found-brighton-report-") as temp:
        temp_path = Path(temp)
        config = {
            "[CLIENT NAME]": client.name,
            "[Client]": client.name,
            "[client]": client.name,
            "[PRIMARY MARKET]": report.market,
            "[WEBSITE]": website or (client.domains[0] if client.domains else "Not recorded"),
            "[MONTH YEAR]": report.end_date.strftime("%B %Y"),
            "[REPORT OWNER]": agency,
            "[CONTACT EMAIL]": "",
        }
        config_path = temp_path / "client.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        output = temp_path / "output"
        command = [sys.executable, str(TEMPLATE_DIR / "generate_report.py"), "--config", str(config_path), "--output-dir", str(output)]
        result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=90)
        docx_path = output / "Found_in_Brighton_AI_Client_Report.docx"
        if result.returncode or not docx_path.is_file():
            raise RuntimeError(f"The Found in Brighton template generator failed: {(result.stderr or result.stdout)[-3000:]}")
        document = Document(docx_path)
        _fill(document, report, data)
        stream = BytesIO()
        document.save(stream)
        return stream.getvalue()
