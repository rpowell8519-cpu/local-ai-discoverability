"""Flowing, readable v4 layout shared by client and synthetic owner reports."""
from __future__ import annotations

import io
from html import escape
from urllib.parse import quote

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether

from src.owner_services_report import build_owner_report, provider_name, cited_urls


def render_owner_services_pdf(payload) -> bytes:
    from src.poc_audit_pdf import _register_fonts, FONT, FONT_BOLD, NAVY, BLUE, INK, MID, PALE, LINE
    _register_fonts()
    pdfmetrics.registerFontFamily(FONT, normal=FONT, bold=FONT_BOLD, italic=FONT, boldItalic=FONT_BOLD)
    report = build_owner_report(payload)
    cfg = report["config"]
    e = lambda value: escape(str(value if value is not None else ""), quote=True)
    styles = {
        "body": ParagraphStyle("body", fontName=FONT, fontSize=11.5, leading=16, textColor=INK, spaceAfter=8),
        "small": ParagraphStyle("small", fontName=FONT, fontSize=9.5, leading=13, textColor=MID, spaceAfter=7, splitLongWords=True),
        "h1": ParagraphStyle("h1", fontName=FONT_BOLD, fontSize=23, leading=29, textColor=NAVY, spaceAfter=18, keepWithNext=True),
        "h2": ParagraphStyle("h2", fontName=FONT_BOLD, fontSize=14, leading=19, textColor=NAVY, spaceBefore=9, spaceAfter=7, keepWithNext=True),
        "label": ParagraphStyle("label", fontName=FONT_BOLD, fontSize=10, leading=14, textColor=NAVY, spaceAfter=8, keepWithNext=True),
        "cell": ParagraphStyle("cell", fontName=FONT, fontSize=11, leading=14.5, textColor=INK),
    }
    story = []
    sections = []
    def p(text, style="body", markup=False):
        return Paragraph(text if markup else e(text), styles[style])
    def add(text, style="body"):
        story.append(p(text, style))
    def refs(values):
        return p("Sources: " + " · ".join(f'<link href="#{e(ref)}" color="#194db0">{e(ref)}</link>' for ref in values), "small", True)
    def start(key, title, label, new=True):
        if new and story:
            story.append(PageBreak())
        sections.append(key)
        story.append(p(label.upper(), "label"))
        heading = p(f'<a name="{e(key)}"/>{e(title)}', "h1", True)
        heading.section_key, heading.section_title = key, title
        story.append(heading)
    def table(headers, rows, widths):
        data = [[p(h, "cell") for h in headers]] + [[p(c, "cell") for c in row] for row in rows]
        tab = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
        tab.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), PALE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEBELOW", (0, 0), (-1, 0), 1, NAVY), ("LINEBELOW", (0, 1), (-1, -1), .4, LINE),
            ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
        story.extend([tab, Spacer(1, 10)])
    def observation(item):
        story.append(KeepTogether([p(item["title"], "h2"), p(item["body"]), refs(item["refs"])]))

    synthetic = bool(cfg.get("synthetic"))
    start("finding", report["headline"], "Synthetic demonstration — not client evidence" if synthetic else "Your AI visibility finding", new=False)
    add(f"{report['name']} · Test date: {report['audit']['audit_date']}", "small")
    if synthetic:
        add("All businesses, answers, reviews and website examples in this template are invented demonstration data. Do not use these figures as client evidence.")
    add(cfg.get("priority_context", "These results describe the saved questions. Confirm the owner's commercial priorities before choosing changes."))
    add("Why it matters", "h2")
    add(cfg.get("implication", "Use the service results to decide where further investigation is useful. The overall total is not a universal score for the business."))
    groups = [s for s in report["services"] if s["answers"]]
    visible = [s for s in groups if s["appearances"]]
    absent = [s for s in groups if not s["appearances"]]
    if visible and absent:
        table(["In this test", "Business appearances"], [
            [", ".join(s["name"] for s in visible) if len(visible) <= 2 else "Service groups with appearances", f"{sum(s['appearances'] for s in visible)} of {sum(s['answers'] for s in visible)} answers"],
            ["Other tested service groups", f"0 of {sum(s['answers'] for s in absent)} answers"],
            ["Overall", f"{report['appearances']} of {report['answers']} answers"]], [325, 180])
    else:
        add(f"Overall: {report['appearances']} of {report['answers']} completed AI answers checked.", "h2")
    untested = [s["name"] for s in report["services"] if s["status"] == "Not tested"]
    if untested:
        add("Not tested: " + ", ".join(untested) + ". This is missing coverage, not zero visibility.")
    add("What we did", "h2")
    add(f"We used {len(report['questions'])} customer-style questions and checked saved answers from {', '.join(report['providers'])}. These are controlled tests using provider models, not tests of a person's own app session; their answers may differ.")
    add("The test measures appearances. Website and review research supplies observations. The action plan is our interpretation—not proof of what caused an AI answer.")
    story.append(refs(["TEST"]))

    start("services", "Where you appear—and where coverage is missing", "Results by owner priority")
    add("Each count means answers in which the business appeared in the saved recommendation list. Repeated names for the same business count only once in an answer.")
    table(["Priority service", "Questions", "Result"], [[s["name"], ", ".join(f"Q{o}" for o in s["questions"]) or "—",
        f"{s['appearances']} of {s['answers']} answers" if s["answers"] else s["status"]] for s in report["services"]], [235, 105, 165])
    add(cfg.get("coverage_note", "A service-to-question mapping is included only where confirmed. Unmapped priorities need reviewer attention; they are not automatically classified as untested."))
    add("The overall result depends on this question mix. More questions about one service give it more weight. These counts are not the probability that a customer will see the business.")
    story.append(refs([f"Q{q['order']}" for q in report["questions"]]))

    start("evidence", "Keep the strengths. Check the gaps.", "Research findings")
    if cfg.get("strengths"):
        for item in cfg["strengths"]:
            observation(item)
    else:
        add("The saved benchmark measures appearances, but no source-specific research strengths have been approved for this report. This is not evidence that the business lacks strengths.")
    for item in cfg.get("gaps", []):
        observation(item)
    for ref, source in list((k, s) for k, s in report["sources"].items() if s["kind"] == "review" and s["business"] == report["name"])[:2]:
        review_source = "Google review (saved copy)" if source.get("source") == "outscraper_google_reviews" else source.get("source", "Source unavailable")
        story.append(KeepTogether([p('“' + source["excerpt"] + '”'), p(f"{review_source} · {str(source.get('date') or 'Date unavailable')[:10]}", "small"), refs([ref])]))

    if report["cohort"]:
        start("comparison", "Useful comparisons—not an overall league table", "Relevant businesses")
        add("These businesses appeared in the saved answers and have verified identities. Local relevance and evidence availability are considered separately; identity alone does not establish local relevance. They are not all better than the client at every service.")
        for member in report["cohort"]:
            pid = str(member["google_place_id"])
            measured = "; ".join(f"{s['name']}: {s['count']} of {s['answers']}" for s in member["services"] if s["count"])
            add(member["business_name"], "h2")
            add(f"Appearances: {measured or 'none in the completed answers' }.")
            specific = next((c for c in cfg.get("comparisons", []) if c.get("place_id") == pid), None)
            if specific:
                add(specific["body"])
                story.append(refs(specific["refs"]))
            else:
                add("Service-page comparison: Not assessed.")
            add(member.get("location_reason") or "Geographic relevance: not confirmed.", "small")
        add("The unfiltered frequency ranking in Appendix B can include unresolved or out-of-area names. This selected comparison is different. Review samples and website coverage are listed in Appendix D.", "small")

    for n, action in enumerate(cfg["actions"], 1):
        start(f"action{n}", action["title"], "Proposed action · owner approval needed")
        for title, field in [("Customer need", "need"), ("Observed evidence", "observation"), ("First concrete deliverable", "deliverable"),
                             ("Who supplies the information", "supplier"), ("Who implements it", "implementer"),
                             ("Estimated effort", "effort"), ("Dependencies", "dependencies"), ("Completion check", "check")]:
            story.append(KeepTogether([p(title, "h2"), p(action[field])]))
        story.append(refs(action["refs"]))

    start("delivery", "Agree the work, then measure again", "Responsibilities and follow-up")
    add("The service priorities came from the owner. The implementation order is our suggestion, not an owner-approved ranking of profitability, demand or capacity.")
    table(["Sequence", "Responsibility and deliverable"], [
        ["First: agree", "Owner selects the first service and confirms business facts. Reviewer checks the relevant evidence and agrees the brief."],
        ["Then: deliver", "Website manager or copywriter completes only the approved changes. Owner verifies factual accuracy and permissions."],
        ["Then: check", "Reviewer records the page addresses, dated changes and completed acceptance checks. Unresolved questions stay open."],
        ["Later: remeasure", "Suggested: 8–12 weeks after the agreed meaningful changes are live and checked—not 8–12 weeks from this report. A new benchmark needs separate approval."]], [125, 380])
    add("Two separate things to track", "h2")
    add("Delivery: did the agreed information and enquiry improvements pass their completion checks? Visibility: did the business appear differently in later AI answers? Finishing the work is not itself evidence of a visibility increase.")
    add("Keep the baseline questions and settings where possible. Report unchanged questions separately from new questions, such as an untested priority. Disclose changed models, providers, search mode and repetition counts. Do not blend search-disabled and search-grounded results.")
    add("Small movements may be ordinary answer variation. A before-and-after comparison cannot isolate the cause of a change or guarantee more recommendations. These counts do not measure customers, sales, revenue or commercial market share.")
    add("Detailed question results, methods and source references follow in the appendices.", "small")

    start("questions", "Exact questions and results", "Appendix A · unchanged original test")
    for q in report["questions"]:
        elements = [p(f'<a name="Q{q["order"]}"/>Q{q["order"]} · {q["appearances"]} of {q["answers"]} completed answers', "h2", True), p(q["prompt"])]
        details = []
        for provider in report["providers"]:
            rows = [r for r in q["records"] if provider_name(r["provider"]) == provider and r["response_complete"] and r["status"] == "completed" and not r.get("error_message") and r.get("raw_response", "").strip()]
            details.append(f"{provider}: {sum(r['response_id'] in report['target_answer_ids'] for r in rows)} of {len(rows)}")
        elements.append(p(" · ".join(details), "small"))
        story.append(KeepTogether(elements))

    start("market", "Named businesses in the saved answers", "Appendix B · unfiltered frequency ranking")
    add("Count = distinct completed answers containing this business in a recommendation entry. Ties share a rank; alphabetical display order is not a tie-breaker. Unresolved names remain visible but are not confirmed local businesses.")
    # A readable leading table; the full unfiltered market is in the index.
    leading = report["market"][:12]
    target_row = next((r for r in report["market"] if r["key"] == str(report["audit"]["target_google_place_id"])), None)
    if target_row and target_row not in leading:
        leading.append(target_row)
    add("Leading names (up to 12), plus the client if outside that set. The companion evidence index retains every name and its measured count.", "small")
    table(["Rank", "Business / name in answers", "Answers", "Identity"], [[("Joint " if row["tied"] else "") + str(row["rank"]), row["name"], str(row["count"]), "Resolved" if row["verified"] else "Unconfirmed"] for row in leading], [65, 270, 65, 105])
    if not report["market"]:
        add("No named business recommendations were retained in the completed answers.")
    add(f"There are {report['raw_entries']} eligible named-business entries before within-answer deduplication, and {report['deduplicated_entries']} after it. The client's {report['appearances']} of {report['answers']} result uses answers as its denominator, not business entries.")
    add("Client results by provider", "h2")
    table(["Provider models", "Client appearances / completed answers"], [[row["name"], f"{row['appearances']} / {row['answers']}"] for row in report["provider_counts"]], [185, 320])
    if report["owners"]:
        add("Owner-nominated competitors (separate view)", "h2")
        add("These names were nominated by the owner. Zero measured appearances does not remove a business from this view.")
        table(["Owner's name", "Matching result", "Answers"], [[r["owner_name"], r.get("business_name", "") + (" · identity resolved" if r["verified"] else " · identity unconfirmed"), str(r["count"])] for r in report["owners"]], [130, 310, 65])

    start("TEST", "How to interpret this test", "Appendix C · scope and definitions")
    add(f"Run: {report['audit']['baseline_run_id']}", "small")
    add(f"Date: {report['audit']['audit_date']} · Mode: {report['mode']}")
    repetition_text = (f"{report['repetition_counts'][0]} repetitions per question per provider" if len(report["repetition_counts"]) == 1 else "Uneven repetition coverage across questions/providers")
    add(f"{len(report['questions'])} questions · {len(report['providers'])} providers · {repetition_text}. The question tables show actual complete counts. Saved repetition indices: {', '.join(map(str, report['repetition_values']))}.")
    add(f"{report['answers']} completed answers included; {report['excluded']} failed or incomplete records excluded. {report['no_named_answers']} completed answers had no retained named recommendation; these remain in answer denominators.")
    for provider, model in report["models"].items():
        add(f"{provider_name(provider)}: {model}", "small")
    definitions = [
        ("Business appearance", "One business in at least one saved recommendation entry in a valid completed answer. Accepted aliases share a canonical Place ID and count once per answer."),
        ("Recommendation", "A business entry retained by the existing recommendation-list extraction and reconciliation—not every occurrence of a name in prose. " + cfg.get("recommendation_validation", "")),
        ("Passing mention", "A name in prose, a caveat or a citation is not independently counted unless retained as a recommendation entry. This report does not provide a separate, fully classified passing-mention total."),
        ("Incorrect or ambiguous match", "A suspected wrong or unresolved identity must not be credited to a verified business. Unresolved names remain separate. An identity marked resolved reflects the saved reconciliation, not proof of every AI claim."),
        ("Source citation", "A source link preserved in the AI answer. It is not a recommendation entry or evidence that the source caused the answer. Missing saved citation metadata does not establish that no sources were used."),
        ("No named recommendation", "A completed answer with no eligible named-business entry. It remains in the denominator."),
        ("Failed or incomplete answer", "A record not completed successfully, with an error, empty answer or incomplete flag. Excluded from measured answer denominators, never silently counted as a zero."),
    ]
    for title, body in definitions:
        story.append(KeepTogether([p(title, "h2"), p(body)]))
    add("Limits of interpretation", "h2")
    add("Results depend on the questions, date, provider models and settings, and may vary between runs. Website/review observations do not prove causes. Public-source evidence may predate the test. No source-quality score or improvement probability is inferred from these observations.")
    add("Search-grounded means the configured run allowed search; it does not establish that every answer searched or that all cited material was independently checked. Provider models are not consumer app sessions." if report["mode"] == "search_grounded" else "Search mode is recorded above. If it is unknown, do not assume live search or treat the run as comparable with a known search mode.")

    start("INVENTORY", "Research coverage and source references", "Appendix D · independently reviewed evidence")
    add("Website evidence is saved page text and audit metadata, not an exhaustive current-site assessment. Counts below are collected page records; duplicate URLs or truncated excerpts can reduce coverage. No new public research was added to this historical audit.")
    rows = []
    for audit in report["website_audits"]:
        group = next((g for g in report["review_sets"] if str(g.get("google_place_id")) == str(audit.get("google_place_id"))), {})
        rows.append([audit["business_name"], str(len(audit.get("pages", []))), str(len(group.get("records", []))) if group.get("records") else "Not assessed"])
    if rows:
        table(["Business", "Page records", "Reviews analysed"], rows, [305, 90, 110])
    add("No collected review text means review content was not assessed—not that the business has no reviews. Reviews analysed are a sample, not a verified total review count. The companion index lists every captured page with its date and record ID.")
    for ref, source in report["sources"].items():
        url = source.get("url")
        title = f'<a name="{e(ref)}"/>{e(ref)} · {e(source["title"])}'
        group = [p(title, "h2", True), p(f"{source['business']} · {str(source.get('date') or 'Date unavailable')[:10]}", "small")]
        if source.get("excerpt"):
            group.append(p('“' + source["excerpt"] + '”'))
        if source["kind"] in ("site_check", "listing") and source.get("text"):
            group.append(p(source["text"]))
        for excerpt in source.get("additional_excerpts", []):
            group.append(p('“' + excerpt + '”'))
        if url:
            what = {"review": "review", "site_check": "robots.txt file"}.get(source["kind"], "website page")
            group.append(p(f'<link href="{e(url)}" color="#194db0">Open original {what}</link>', "small", True))
        group.append(p(f"Record: {source['record_id']} · Collection: {source.get('collection_id', 'Not recorded')}", "small"))
        if source["kind"] == "review":
            group.append(p(f"Source: {source.get('source', 'Not recorded')} · imported {str(source.get('imported_at') or 'Not recorded')[:10]}. Quotation verified against saved text; date is the review date, not today's evidence.", "small"))
        story.append(KeepTogether(group))

    start("answers", "Inspect the saved AI answers", "Appendix E · AI-cited sources, separate from audit research")
    add("The companion evidence index contains every saved answer, its exact question, provider model, repetition, answer ID, query ID and content hash. It also contains the saved website excerpts and selected review records.")
    index_name = cfg.get("evidence_index")
    if index_name:
        story.append(p(f'<link href="{e(quote(index_name))}" color="#194db0">Open companion evidence index</link> (keep it beside this PDF).', markup=True))
        add(index_name, "small")
    add("Examples below are selected for inspection, not a replacement for the complete answer set. URLs are only those actually preserved in the answer. Claims made by an AI answer are not automatically verified audit findings.")
    for q in report["questions"]:
        candidates = [r for r in q["records"] if r["response_id"] in report["target_answer_ids"]]
        chosen = next((r for r in candidates if cited_urls(r["raw_response"])), None) or next(iter(candidates or q["records"]), None)
        if not chosen:
            continue
        label = f"Q{q['order']} · {provider_name(chosen['provider'])} · repetition {chosen['repetition']}"
        group = [p(label, "h2"), p(f"Answer ID: {chosen['response_id']}", "small")]
        if index_name:
            group.append(p(f'<link href="{e(quote(index_name))}#{e(chosen["response_id"])}" color="#194db0">Read this exact saved answer</link>', "small", True))
        urls = cited_urls(chosen["raw_response"])
        # One example URL, explicitly labelled; all preserved URLs are in the index.
        if urls:
            group.append(p(f'<link href="{e(urls[0])}" color="#194db0">Example source linked in this answer</link> · all preserved links are in the index.', "small", True))
        else:
            group.append(p("No source URL was preserved in this answer's text. Structured citation metadata is not supplied in this payload.", "small"))
        story.append(KeepTogether(group))

    class ReportDoc(SimpleDocTemplate):
        def afterFlowable(self, flowable):
            if hasattr(flowable, "section_key"):
                self.canv.bookmarkPage(flowable.section_key)
                self.canv.addOutlineEntry(flowable.section_title, flowable.section_key, 0)

        def afterPage(self):
            # Footer text follows the body in content-stream reading order.
            footer(self.canv, self)

    output = io.BytesIO()
    title = ("SYNTHETIC — " if synthetic else "") + report["name"] + " — AI Visibility Report"
    doc = ReportDoc(output, pagesize=(595.2756, 841.8898), leftMargin=45, rightMargin=45,
                    topMargin=51, bottomMargin=48, title=title, author="Local AI Discoverability",
                    subject="Synthetic demonstration data" if synthetic else "Existing benchmark and independently collected evidence; read-only report", pageCompression=1, invariant=1)
    def footer(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(LINE)
        canvas.line(45, 37, 550, 37)
        canvas.setFont(FONT, 9)
        canvas.setFillColor(MID)
        label = "SYNTHETIC DEMONSTRATION" if synthetic else report["name"]
        # Avoid footer collision for long business names without reducing type size.
        while pdfmetrics.stringWidth(label, FONT, 9) > 380:
            label = label[:-2]
        canvas.drawString(45, 24, label)
        canvas.drawRightString(550, 24, f"Page {document.page}")
        canvas.restoreState()
    def accent(canvas, document):
        canvas.setStrokeColor(BLUE)
        canvas.setLineWidth(3)
        canvas.line(45, 818, 110, 818)
    doc.build(story, onFirstPage=accent, onLaterPages=accent)
    return output.getvalue()
