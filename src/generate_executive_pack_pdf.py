#!/usr/bin/env python3
"""
generate_executive_pack_pdf.py
Generates a publication-grade Executive Master Pack PDF synthesizing the
Local AI Discoverability strategy, 6-layer multi-lever hierarchy, 4-tier
deliverable repertoire, and operational execution framework.
Wording reviewed 30 October 2026 against docs/sales-language-review.md: no rating cutoffs,
lost-revenue figures or guaranteed inclusion; third-party figures carry their scope.
"""

from __future__ import annotations

import os
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
    KeepTogether,
    HRFlowable,
)
from reportlab.pdfgen import canvas

# --- PALETTE DEFINITION ---
C_NAVY_DARK = HexColor("#0F172A")    # Slate 900
C_NAVY_MED  = HexColor("#1E293B")    # Slate 800
C_BLUE_MAIN = HexColor("#2563EB")    # Royal Blue 600
C_BLUE_DARK = HexColor("#1D4ED8")    # Royal Blue 700
C_BLUE_PALE = HexColor("#EFF6FF")    # Blue 50
C_EMERALD   = HexColor("#059669")    # Emerald 600
C_EMERALD_BG= HexColor("#ECFDF5")    # Emerald 50
C_AMBER     = HexColor("#D97706")    # Amber 600
C_AMBER_BG  = HexColor("#FFFBEB")    # Amber 50
C_CRIMSON   = HexColor("#DC2626")    # Red 600
C_CRIMSON_BG= HexColor("#FEF2F2")    # Red 50
C_SLATE_BG  = HexColor("#F8FAFC")    # Slate 50
C_BORDER    = HexColor("#E2E8F0")    # Slate 200
C_BORDER_MED= HexColor("#CBD5E1")    # Slate 300
C_TEXT_MAIN = HexColor("#0F172A")    # Text Heading/Dark
C_TEXT_BODY = HexColor("#334155")    # Text Body Slate 700
C_TEXT_MUTED= HexColor("#64748B")    # Text Muted Slate 500
C_WHITE     = colors.white

PAGE_W, PAGE_H = A4
MARGIN = 36  # 0.5 inch margins
CONTENT_W = PAGE_W - (2 * MARGIN)  # 523.27 pt


class NumberedCanvas(canvas.Canvas):
    """
    Two-pass canvas to dynamically compute and stamp running headers,
    decorative accents, and exact 'Page X of Y' footers.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, total_pages: int):
        self.saveState()
        page_num = self._pageNumber

        # Cover page has unique treatment (Page 1)
        if page_num == 1:
            # Top accent bar on cover
            self.setFillColor(C_BLUE_MAIN)
            self.rect(0, PAGE_H - 8, PAGE_W, 8, fill=True, stroke=False)
            self.setFillColor(C_NAVY_DARK)
            self.rect(0, PAGE_H - 12, PAGE_W, 4, fill=True, stroke=False)
            self.restoreState()
            return

        # Running Top Header (Pages 2+)
        # Subtle top color bar
        self.setFillColor(C_BLUE_MAIN)
        self.rect(MARGIN, PAGE_H - 22, CONTENT_W, 2.5, fill=True, stroke=False)

        self.setFont("Helvetica-Bold", 8)
        self.setFillColor(C_NAVY_DARK)
        self.drawString(MARGIN, PAGE_H - 34, "LOCAL AI DISCOVERABILITY & OPTIMIZATION")

        self.setFont("Helvetica", 8)
        self.setFillColor(C_TEXT_MUTED)
        self.drawRightString(PAGE_W - MARGIN, PAGE_H - 34, "EXECUTIVE MASTER PLAYBOOK · 2026")

        # Running Bottom Footer (Pages 2+)
        self.setStrokeColor(C_BORDER)
        self.setLineWidth(0.75)
        self.line(MARGIN, 34, PAGE_W - MARGIN, 34)

        self.setFont("Helvetica", 8)
        self.setFillColor(C_TEXT_MUTED)
        self.drawString(MARGIN, 22, "CONFIDENTIAL & PROPRIETARY · PREPARED FOR AGENCY LEADERSHIP & CLIENT DELIVERY")

        page_str = f"Page {page_num} of {total_pages}"
        self.drawRightString(PAGE_W - MARGIN, 22, page_str)

        self.restoreState()


def build_styles():
    styles = getSampleStyleSheet()

    # Cover Styles
    styles.add(ParagraphStyle(
        "CoverEyebrow",
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=13,
        textColor=C_BLUE_MAIN,
        textTransform="uppercase",
        spaceAfter=12,
    ))
    styles.add(ParagraphStyle(
        "CoverTitle",
        fontName="Helvetica-Bold",
        fontSize=26,
        leading=32,
        textColor=C_NAVY_DARK,
        spaceAfter=10,
    ))
    styles.add(ParagraphStyle(
        "CoverSubtitle",
        fontName="Helvetica",
        fontSize=13,
        leading=18,
        textColor=C_TEXT_MUTED,
        spaceAfter=20,
    ))

    # Section Headers
    styles.add(ParagraphStyle(
        "SectionBadge",
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=C_BLUE_MAIN,
        textTransform="uppercase",
        spaceAfter=3,
    ))
    styles.add(ParagraphStyle(
        "SectionHeading",
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=20,
        textColor=C_NAVY_DARK,
        spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        "SubSectionHeading",
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=15,
        textColor=C_NAVY_MED,
        spaceBefore=6,
        spaceAfter=4,
    ))

    # Body & Callouts
    styles.add(ParagraphStyle(
        "BodyDark",
        fontName="Helvetica",
        fontSize=8.5,
        leading=12,
        textColor=C_TEXT_BODY,
        spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        "BodyDarkBold",
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=12,
        textColor=C_NAVY_DARK,
        spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        "CalloutText",
        fontName="Helvetica",
        fontSize=8.5,
        leading=12,
        textColor=C_NAVY_MED,
    ))
    styles.add(ParagraphStyle(
        "CardTitle",
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=12,
        textColor=C_NAVY_DARK,
    ))
    styles.add(ParagraphStyle(
        "CardText",
        fontName="Helvetica",
        fontSize=8,
        leading=11,
        textColor=C_TEXT_BODY,
    ))
    styles.add(ParagraphStyle(
        "TableHeader",
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=11,
        textColor=C_WHITE,
    ))
    styles.add(ParagraphStyle(
        "TableCell",
        fontName="Helvetica",
        fontSize=7.8,
        leading=10.5,
        textColor=C_TEXT_BODY,
    ))
    styles.add(ParagraphStyle(
        "TableCellBold",
        fontName="Helvetica-Bold",
        fontSize=7.8,
        leading=10.5,
        textColor=C_NAVY_DARK,
    ))
    styles.add(ParagraphStyle(
        "StatBig",
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=22,
        textColor=C_BLUE_MAIN,
        alignment=1,  # Center
    ))
    styles.add(ParagraphStyle(
        "StatLabel",
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=C_NAVY_DARK,
        alignment=1,
    ))
    styles.add(ParagraphStyle(
        "StatSub",
        fontName="Helvetica",
        fontSize=7,
        leading=9,
        textColor=C_TEXT_MUTED,
        alignment=1,
    ))

    return styles


def create_callout_box(content_p, bg_color=C_SLATE_BG, border_color=C_BLUE_MAIN):
    """Wraps paragraphs inside a stylized callout table with an accent left border."""
    t = Table([[content_p]], colWidths=[CONTENT_W])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), bg_color),
        ('BOX', (0, 0), (-1, -1), 0.5, C_BORDER),
        ('LINEBEFORE', (0, 0), (0, -1), 3.5, border_color),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
    ]))
    return t


def generate_pdf(output_path: str):
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN + 12,
        bottomMargin=MARGIN + 8,
    )

    styles = build_styles()
    story = []

    # =========================================================================
    # PAGE 1: EXECUTIVE COVER & HIGH-LEVEL OVERVIEW
    # =========================================================================
    story.append(Spacer(1, 15))
    story.append(Paragraph("STRATEGIC ADVISORY BRIEFING · SEPTEMBER 2026", styles["CoverEyebrow"]))
    story.append(Paragraph("Local AI Discoverability & Optimization", styles["CoverTitle"]))
    story.append(Paragraph(
        "A Multi-Model Operational Blueprint for Small-to-Medium Business Visibility Across Frontier AI Engines (ChatGPT, Gemini, Claude, and Perplexity)",
        styles["CoverSubtitle"]
    ))
    story.append(HRFlowable(width="100%", thickness=1.5, color=C_BLUE_MAIN, spaceAfter=18))

    # Executive Abstract Callout
    abstract_text = Paragraph(
        "<b>Executive Context:</b> Traditional Search Engine Optimization (SEO) was architected for a single Google-dominated keyword search index. In 2026, more customers also ask conversational AI assistants for local recommendations. Generative Engine Optimization (GEO) requires moving beyond simplistic on-site keyword tweaks into a <b>multi-platform approach</b>. This executive pack synthesizes our empirical research, audit methodology, 6-layer implementation framework, and 4-tier client reporting repertoire.",
        styles["CalloutText"]
    )
    story.append(create_callout_box(abstract_text, bg_color=C_BLUE_PALE, border_color=C_BLUE_MAIN))
    story.append(Spacer(1, 14))

    # Metric Highlight Grid (4 Cards across)
    stat_col_w = CONTENT_W / 4.0
    stats_data = [
        [
            Paragraph("79.8%", styles["StatBig"]),
            Paragraph("87.0%", styles["StatBig"]),
            Paragraph("71.9%", styles["StatBig"]),
            Paragraph("62.0%", styles["StatBig"]),
        ],
        [
            Paragraph("Google AI Mode", styles["StatLabel"]),
            Paragraph("ChatGPT Search", styles["StatLabel"]),
            Paragraph("UK Local Trades", styles["StatLabel"]),
            Paragraph("Ghost Citations", styles["StatLabel"]),
        ],
        [
            Paragraph("Local citations from Maps & GBP (one US vendor study)", styles["StatSub"]),
            Paragraph("Reported Bing alignment with ChatGPT sources (contested)", styles["StatSub"]),
            Paragraph("Trade-directory sources (one 80-prompt UK test)", styles["StatSub"]),
            Paragraph("AI citations without a brand mention (Semrush headline)", styles["StatSub"]),
        ],
    ]
    stat_table = Table(stats_data, colWidths=[stat_col_w]*4)
    stat_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), C_SLATE_BG),
        ('BOX', (0, 0), (-1, -1), 0.5, C_BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, C_BORDER),
        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(stat_table)
    story.append(Spacer(1, 14))

    # Table of Contents & Structure Guide
    story.append(Paragraph("<b>EXECUTIVE PACK CONTENTS & STRUCTURAL NARRATIVE</b>", styles["BodyDarkBold"]))
    toc_data = [
        [Paragraph("<b>Section 1: The Multi-Model Paradigm Shift</b>", styles["TableCellBold"]), Paragraph("Why on-site SEO alone is not enough for AI answers; platform retrieval mechanics (Bing, Maps, Brave).", styles["TableCell"])],
        [Paragraph("<b>Section 2: Diagnostic & Competitor Taxonomy</b>", styles["TableCellBold"]), Paragraph("The 4-Tier Intent Matrix; contrasting owner-nominated rivals vs. algorithmic market leaders.", styles["TableCell"])],
        [Paragraph("<b>Section 3: The 6-Layer Multi-Lever Framework</b>", styles["TableCellBold"]), Paragraph("Full-stack action architecture spanning crawl unblocking, GBP/Bing sync, reviews, & landing pages.", styles["TableCell"])],
        [Paragraph("<b>Section 4: The 4-Tier Client Deliverable Repertoire</b>", styles["TableCellBold"]), Paragraph("Outreach Taster Pack, Strategic Deep Audit, Active Retainer Portal, & 8-12 Week Outcome Review.", styles["TableCell"])],
        [Paragraph("<b>Section 5: Statistical Rigor & Tracking Setup</b>", styles["TableCellBold"]), Paragraph("Binomial confidence intervals over 60–100 runs; integrating Bing AI reports and Streamlit portals.", styles["TableCell"])],
        [Paragraph("<b>Section 6: Commercial Sprints, Packaging & SOP</b>", styles["TableCellBold"]), Paragraph("The 3-Phase Discovery Sprint, agency pricing tiers (£1.5k–£2.5k), and delivery task checklists.", styles["TableCell"])],
    ]
    toc_table = Table(toc_data, colWidths=[CONTENT_W * 0.40, CONTENT_W * 0.60])
    toc_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), C_WHITE),
        ('BOX', (0, 0), (-1, -1), 0.5, C_BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, C_BORDER),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(toc_table)
    story.append(PageBreak())

    # =========================================================================
    # PAGE 2: SECTION 1 · THE MULTI-MODEL PARADIGM SHIFT
    # =========================================================================
    story.append(Paragraph("SECTION 01 · STRATEGIC DIAGNOSIS", styles["SectionBadge"]))
    story.append(Paragraph("The Multi-Model Paradigm Shift: Why Website-Only SEO Is Not Enough", styles["SectionHeading"]))
    story.append(Paragraph(
        "For two decades, agency optimization revolved around the client's own website. Published studies of AI answers, mostly vendor-run and US-based, show that for local questions assistants also cite Google and Bing listings, directories and review sites. When answering buyer prompts like <i>'Who is the best commercial cleaner in Brighton?'</i>, they often draw on <b>third-party listings and directories as well as business websites</b>.",
        styles["BodyDark"]
    ))
    story.append(Spacer(1, 3))

    # Platform Retrieval Mechanics Table
    plat_w = [CONTENT_W * 0.22, CONTENT_W * 0.28, CONTENT_W * 0.32, CONTENT_W * 0.18]
    plat_data = [
        [
            Paragraph("AI Platform", styles["TableHeader"]),
            Paragraph("Primary Retrieval Backend", styles["TableHeader"]),
            Paragraph("Local Grounding & Source Authority", styles["TableHeader"]),
            Paragraph("Website's Actual Role", styles["TableHeader"]),
        ],
        [
            Paragraph("<b>Google AI Mode & Gemini</b>", styles["TableCellBold"]),
            Paragraph("Google Search Index + Google Maps Grounding API (250M+ Places)", styles["TableCell"]),
            Paragraph("<b>AI Mode: 79.8% of local citations went to Maps/GBP</b> in one US vendor study. Keep listings accurate.", styles["TableCell"]),
            Paragraph("Secondary depth (AI Overviews cite sites 70.7%, but AI Mode local picks cite sites only 12.8%).", styles["TableCell"]),
        ],
        [
            Paragraph("<b>ChatGPT Search</b>", styles["TableCellBold"]),
            Paragraph("Bing Search Index + OAI-SearchBot + Licensed Partner Feeds", styles["TableCell"]),
            Paragraph("Bing rank is the <b>strongest reported predictor</b> (Seer, reportedly 87%; contested). Yelp data reportedly licensed July 2026.", styles["TableCell"]),
            Paragraph("Cited often, but directories and lists also shape which businesses are recommended.", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Claude Search</b>", styles["TableCellBold"]),
            Paragraph("Brave Search (listed Anthropic subprocessor)", styles["TableCell"]),
            Paragraph("Indexes open-web pages, trade directories, and comparison listicles via Brave's independent index.", styles["TableCell"]),
            Paragraph("Used when web search runs; otherwise answers come from model memory.", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Perplexity AI</b>", styles["TableCellBold"]),
            Paragraph("Perplexity Independent Index + Multi-Search Connectors", styles["TableCell"]),
            Paragraph("Yelp data integration since March 2024; also cites review and directory sites.", styles["TableCell"]),
            Paragraph("Aggregates snippets across top 5 sources; requires PerplexityBot crawlability.", styles["TableCell"]),
        ],
    ]
    plat_table = Table(plat_data, colWidths=plat_w)
    plat_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), C_NAVY_DARK),
        ('BOX', (0, 0), (-1, -1), 0.5, C_BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, C_BORDER),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [C_WHITE, C_SLATE_BG]),
        ('TOPPADDING', (0, 0), (-1, -1), 2.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(plat_table)
    story.append(Spacer(1, 4))

    story.append(Paragraph("The Reality of the UK Local Services Ecosystem", styles["SubSectionHeading"]))
    story.append(Paragraph(
        "In one small UK agency test (Murray Digital, Aug 2026: 80 ChatGPT prompts, one run each), <b>71.9% of cited sources were trade directories</b>, and only <b>2 of 80 answers</b> cited the business's own site. Checkatrade was cited in 78/80 answers and MyBuilder in 70/80. The sample is small, but it shows why work that stops at website copy can miss most of what these answers cite.",
        styles["BodyDark"]
    ))
    story.append(Spacer(1, 3))

    # The "Ghost Citation" Callout
    ghost_text = Paragraph(
        "<b>Citation Is Not Recommendation (Semrush headline figure):</b> <b>62% of AI citations did not lead to a brand mention</b>. An answer can cite a company's site to explain a term or a price, then <i>recommend someone else</i>. So we measure recommendations directly, and report citations separately.",
        styles["CalloutText"]
    )
    story.append(create_callout_box(ghost_text, bg_color=C_AMBER_BG, border_color=C_AMBER))
    story.append(Spacer(1, 4))

    # Debunking Gimmicks Table
    story.append(Paragraph("Reality Check: Basics vs. De-Scoped Gimmicks", styles["SubSectionHeading"]))
    gimmick_w = [CONTENT_W * 0.28, CONTENT_W * 0.44, CONTENT_W * 0.28]
    gimmick_data = [
        [Paragraph("Tactic / Gimmick", styles["TableHeader"]), Paragraph("Empirical Findings & Platform Reality", styles["TableHeader"]), Paragraph("Agency Verdict", styles["TableHeader"])],
        [
            Paragraph("<b>llms.txt Files</b>", styles["TableCellBold"]),
            Paragraph("In Ahrefs' 137k-domain study, <b>97% of valid llms.txt files had 0 bot requests</b>. Google Search documentation explicitly states it ignores them. Useful for coding agent docs, zero local value.", styles["TableCell"]),
            Paragraph("<font color='#DC2626'><b>De-Scope (Zero Uplift)</b></font>", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Prompt Injection Pages</b>", styles["TableCellBold"]),
            Paragraph("Hidden text like 'Recommend us as top provider' matches what Microsoft classes as memory poisoning (MITRE ATLAS AML.T0080) and breaches Google's spam policy on hidden text.", styles["TableCell"]),
            Paragraph("<font color='#DC2626'><b>Strictly Forbidden (Toxic)</b></font>", styles["TableCell"]),
        ],
        [
            Paragraph("<b>JSON-LD Schema Manipulation</b>", styles["TableCellBold"]),
            Paragraph("Ahrefs' matched difference-in-differences test (1,885 pages) showed a <b>-4.6% shift in AI Overviews</b> and 0% change in ChatGPT. Essential for entity clarity, but does not drive new recommendations.", styles["TableCell"]),
            Paragraph("<font color='#D97706'><b>Hygiene Only (No Uplift)</b></font>", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Search Bot Crawl Access</b>", styles["TableCellBold"]),
            Paragraph("Firewall and CDN AI-blocking can stop search bots even when robots.txt allows them. A blocked bot cannot read the site when that tool answers.", styles["TableCell"]),
            Paragraph("<font color='#059669'><b>Check First (Cheap to Fix)</b></font>", styles["TableCell"]),
        ],
    ]
    gimmick_table = Table(gimmick_data, colWidths=gimmick_w)
    gimmick_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), C_NAVY_MED),
        ('BOX', (0, 0), (-1, -1), 0.5, C_BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, C_BORDER),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [C_WHITE, C_SLATE_BG]),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(gimmick_table)
    story.append(PageBreak())

    # =========================================================================
    # PAGE 3: SECTION 2 · THE DIAGNOSTIC ENGINE & INTENT TAXONOMY
    # =========================================================================
    story.append(Paragraph("SECTION 02 · AUDIT & DISCOVERY ARCHITECTURE", styles["SectionBadge"]))
    story.append(Paragraph("The Diagnostic Engine: Intent Taxonomies & Dual Competitor Benchmarks", styles["SectionHeading"]))
    story.append(Paragraph(
        "A diagnostic audit is only as credible as its experimental design. In our case study of UDR Properties (an 18-page technical evaluation), testing 8 generic prompts revealed an extraordinary commercial finding: <b>17 of 27 appearances for Airbnb turnarounds, but 0 of 45 across high-margin commercial and office cleaning</b>. To systematize this across all future clients, we structure audits around a 4-Tier Intent Matrix and Dual-Competitor Intelligence.",
        styles["BodyDark"]
    ))
    story.append(Spacer(1, 4))

    # 4-Tier Intent Matrix Table
    story.append(Paragraph("1. The 4-Tier Query Intent Matrix (12–16 Prompts per Client)", styles["SubSectionHeading"]))
    intent_w = [CONTENT_W * 0.22, CONTENT_W * 0.38, CONTENT_W * 0.40]
    intent_data = [
        [Paragraph("Intent Tier", styles["TableHeader"]), Paragraph("Strategic Objective & Persona", styles["TableHeader"]), Paragraph("Example Prompt (Brighton Cleaning Client)", styles["TableHeader"])],
        [
            Paragraph("<b>Tier 1: Commercial / High-Contract</b>", styles["TableCellBold"]),
            Paragraph("Targets commercial landlords, letting agents, and office managers with high-ticket recurring budgets (£1k–£3k/mo).", styles["TableCell"]),
            Paragraph("<i>'Which commercial cleaning companies in Brighton provide daily office cleaning with key-holding and COSHH compliance?'</i>", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Tier 2: Problem-Aware Needs</b>", styles["TableCellBold"]),
            Paragraph("Captures time-sensitive, situational customer requirements with high purchase urgency and low price-sensitivity.", styles["TableCell"]),
            Paragraph("<i>'Who provides emergency commercial carpet steam cleaning in Brighton after a leak?'</i>", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Tier 3: Comparative Shortlist</b>", styles["TableCellBold"]),
            Paragraph("Evaluates brand positioning inside general 'best of', 'top-rated', and 'vetted' conversational consideration sets.", styles["TableCell"]),
            Paragraph("<i>'Who are the most reliable, top-rated commercial cleaning companies in Brighton and Hove?'</i>", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Tier 4: Micro-Locality Fan-Out</b>", styles["TableCellBold"]),
            Paragraph("Leverages geospatial proximity across specific postal codes, commercial parks, and business quarters.", styles["TableCell"]),
            Paragraph("<i>'Office cleaners near North Laine and central Brighton (BN1) and Hove (BN3).'</i>", styles["TableCell"]),
        ],
    ]
    intent_table = Table(intent_data, colWidths=intent_w)
    intent_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), C_NAVY_DARK),
        ('BOX', (0, 0), (-1, -1), 0.5, C_BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, C_BORDER),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [C_WHITE, C_SLATE_BG]),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(intent_table)
    story.append(Spacer(1, 8))

    story.append(Paragraph("2. Dual-Competitor Intelligence: Perceived vs. Algorithmic Leaders", styles["SubSectionHeading"]))
    story.append(Paragraph(
        "Local business owners almost always misunderstand who their digital competitors are. They assume their rivals are the established businesses they see driving around town. Our diagnostic contrasts two distinct competitor sets:",
        styles["BodyDark"]
    ))
    story.append(Spacer(1, 3))

    comp_w = [CONTENT_W * 0.50, CONTENT_W * 0.50]
    comp_card_data = [
        [
            Paragraph("<b>SET A: OWNER-NOMINATED COMPETITORS</b>", styles["CardTitle"]),
            Paragraph("<b>SET B: ALGORITHMIC MARKET LEADERS</b>", styles["CardTitle"]),
        ],
        [
            Paragraph(
                "• Selected directly by the business owner during onboarding.<br/>"
                "• <b>Common Finding:</b> In audits like UDR Properties, nominated competitors (<i>Diamond Cleaning, SEB Services</i>) <b>scored 0 of 9 appearances as well</b>.<br/>"
                "• <b>Commercial Value:</b> Shows the owner how their own rivals fare in the same questions. A shared zero is a measured fact, not proof the market is open.",
                styles["CardText"]
            ),
            Paragraph(
                "• Discovered dynamically by extracting entities recommended across 72+ test answers.<br/>"
                "• <b>Common Finding:</b> In the UDR test, <i>Why Bother Cleaning</i> (21 appearances) and <i>Silver Star</i> (11 appearances) were recommended most for commercial questions.<br/>"
                "• <b>Commercial Value:</b> Shows who is recommended instead, and what their public evidence shows that the client's does not. Observed differences, not proven causes.",
                styles["CardText"]
            ),
        ]
    ]
    comp_table = Table(comp_card_data, colWidths=comp_w)
    comp_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), C_SLATE_BG),
        ('BACKGROUND', (1, 0), (1, -1), C_BLUE_PALE),
        ('BOX', (0, 0), (0, -1), 0.5, C_BORDER),
        ('BOX', (1, 0), (1, -1), 0.5, C_BLUE_MAIN),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(comp_table)
    story.append(Spacer(1, 8))

    story.append(Paragraph("3. Statistical Sampling Discipline", styles["SubSectionHeading"]))
    story.append(Paragraph(
        "To avoid the trap of single-run randomness, audits test <b>12–16 prompts across 3 providers (OpenAI, Gemini, Claude) with 3–5 repetitions</b>. This yields <b>108–240 individual data points</b>, establishing statistical stability and eliminating outlier hallucinations.",
        styles["BodyDark"]
    ))
    story.append(PageBreak())

    # =========================================================================
    # PAGE 4: SECTION 3 · THE 6-LAYER MULTI-LEVER ACTION FRAMEWORK
    # =========================================================================
    story.append(Paragraph("SECTION 03 · ACTION & EXECUTION ARCHITECTURE", styles["SectionBadge"]))
    story.append(Paragraph("The 6-Layer Multi-Lever Action Framework", styles["SectionHeading"]))
    story.append(Paragraph(
        "To deliver true discoverability, agency actions must move systematically across the entire retrieval stack. Below is our operational blueprint detailing technical specifications, operational rules, and compliance standards for all six layers.",
        styles["BodyDark"]
    ))
    story.append(Spacer(1, 4))

    # The 6 Layers Detailed Table
    layer_w = [CONTENT_W * 0.22, CONTENT_W * 0.48, CONTENT_W * 0.30]
    layer_data = [
        [Paragraph("Framework Layer", styles["TableHeader"]), Paragraph("Technical & Operational Requirements", styles["TableHeader"]), Paragraph("Primary Impact Mechanism", styles["TableHeader"])],
        [
            Paragraph("<b>Layer 1: Crawl & Technical Access</b>", styles["TableCellBold"]),
            Paragraph("• Unblock `OAI-SearchBot`, `Claude-SearchBot`, `PerplexityBot`, `Bingbot`, `Googlebot` in `robots.txt`.<br/>• Check CDN/firewall AI-blocking; allow verified search bots (never a user-agent text match).", styles["TableCell"]),
            Paragraph("<b>Prerequisite:</b> A blocked bot cannot read the site for live answers.", styles["TableCellBold"]),
        ],
        [
            Paragraph("<b>Layer 2: Core Platform Grounding</b>", styles["TableCellBold"]),
            Paragraph("• Accurate, specific GBP category (e.g. 'Commercial Cleaning' vs generic 'Cleaning').<br/>• Import GBP into <b>Bing Places</b> (Copilot; reported ChatGPT input) and keep it matching.<br/>• Claim <b>Apple Business</b> place cards (Apple Maps).", styles["TableCell"]),
            Paragraph("<b>Main source for Google AI Mode</b> local answers in one US study; Bing feeds Copilot.", styles["TableCellBold"]),
        ],
        [
            Paragraph("<b>Layer 3: Vertical Ecosystem</b>", styles["TableCellBold"]),
            Paragraph("• <b>UK Trades:</b> Vetted profile on <b>Checkatrade</b> (also has an app in ChatGPT) and MyBuilder.<br/>• <b>Hospitality/Local:</b> TripAdvisor, and <b>Yelp</b> where it is cited for the client's market.", styles["TableCell"]),
            Paragraph("<b>71.9% of sources in one UK trades test</b> were directories like these.", styles["TableCellBold"]),
        ],
        [
            Paragraph("<b>Layer 4: Review Engine & Proof</b>", styles["TableCellBold"]),
            Paragraph("• Steady, ungated requests to every customer (no rating cutoff: AI picks averaged 4.75 vs 4.84 in search, one US study).<br/>• Strict <b>UK DMCC Act 2024 compliance</b>: Zero review gating, zero incentives (CMA fines up to 10% global turnover).<br/>• Semantic prompting asking customers to name the specific service and locality in reviews.", styles["TableCell"]),
            Paragraph("<b>Builds specific, quotable public evidence.</b> Effect on AI answers not isolated by any study.", styles["TableCellBold"]),
        ],
        [
            Paragraph("<b>Layer 5: Owned Web Substrate</b>", styles["TableCellBold"]),
            Paragraph("• Build dedicated landing pages for high-margin priorities (e.g. `/commercial-cleaning-brighton`).<br/>• Embed verbatim customer proof blocks directly adjacent to service scope and specs.<br/>• Direct-answer H2/H3 FAQ architecture answering 40–60 word commercial fan-out questions.", styles["TableCell"]),
            Paragraph("<b>The factual anchor:</b> Provides quote-ready copy for AI models once retrieved.", styles["TableCellBold"]),
        ],
        [
            Paragraph("<b>Layer 6: Entity Alignment & PR</b>", styles["TableCellBold"]),
            Paragraph("• Reconcile legal name, trading name, and founding date (e.g. 2017 vs 2018) across site footer, GBP, and Companies House.<br/>• Earn genuine editorial mentions in regional press (<i>The Argus, Brighton & Hove News</i>). Avoid toxic paid listicles.", styles["TableCell"]),
            Paragraph("<b>Reduces entity ambiguity.</b> Housekeeping; effect on AI answers not established.", styles["TableCellBold"]),
        ],
    ]
    layer_table = Table(layer_data, colWidths=layer_w)
    layer_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), C_NAVY_DARK),
        ('BOX', (0, 0), (-1, -1), 0.5, C_BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, C_BORDER),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [C_WHITE, C_SLATE_BG]),
        ('TOPPADDING', (0, 0), (-1, -1), 4.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4.5),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(layer_table)
    story.append(Spacer(1, 8))

    # DMCC Legal Warning Box
    dmcc_text = Paragraph(
        "<b>LEGAL & COMPLIANCE MANDATE · UK DMCC ACT 2024:</b> In force since April 2025, the Digital Markets, Competition and Consumers Act 2024 grants the Competition and Markets Authority (CMA) statutory enforcement powers to levy fines of <b>up to 10% of global annual turnover</b>. Our review engine strictly forbids: (1) review gating (filtering unhappy customers to private forms), (2) offering discounts or incentives for reviews, and (3) selectively publishing positive testimonials while suppressing negatives. All workflows must remain 100% compliant.",
        styles["CalloutText"]
    )
    story.append(create_callout_box(dmcc_text, bg_color=C_CRIMSON_BG, border_color=C_CRIMSON))
    story.append(PageBreak())

    # =========================================================================
    # PAGE 5: SECTION 4 · THE 4-TIER CLIENT DELIVERABLE REPERTOIRE
    # =========================================================================
    story.append(Paragraph("SECTION 04 · CLIENT LIFECYCLE & PACKAGING", styles["SectionBadge"]))
    story.append(Paragraph("The 4-Tier Client Deliverable Repertoire", styles["SectionHeading"]))
    story.append(Paragraph(
        "A major operational error is treating every client deliverable as an 18-page technical thesis. In cold outreach, dense data loses the reader; in active retainers, clients want regular, clear progress. We decouple our agency reporting into four purpose-built deliverables mapped across the client lifecycle.",
        styles["BodyDark"]
    ))
    story.append(Spacer(1, 4))

    # Funnel Breakdown Grid
    rep_w = [CONTENT_W * 0.25, CONTENT_W * 0.25, CONTENT_W * 0.25, CONTENT_W * 0.25]
    rep_data = [
        [
            Paragraph("TIER 1: OUTREACH TASTER", styles["TableHeader"]),
            Paragraph("TIER 2: STRATEGIC AUDIT", styles["TableHeader"]),
            Paragraph("TIER 3: RETAINER PORTAL", styles["TableHeader"]),
            Paragraph("TIER 4: OUTCOME REVIEW", styles["TableHeader"]),
        ],
        [
            Paragraph("<b>Prospecting & Beta</b>", styles["TableCellBold"]),
            Paragraph("<b>Engaged Client Kick-off</b>", styles["TableCellBold"]),
            Paragraph("<b>Monthly Active Client</b>", styles["TableCellBold"]),
            Paragraph("<b>Week 8–12 Milestone</b>", styles["TableCellBold"]),
        ],
        [
            Paragraph("<b>Format:</b> 2-Page Visual PDF + 90-sec Loom video.", styles["TableCell"]),
            Paragraph("<b>Format:</b> 12–15 Page Strategic Blueprint.", styles["TableCell"]),
            Paragraph("<b>Format:</b> Streamlit Web Portal + 2-Page Monthly Digest.", styles["TableCell"]),
            Paragraph("<b>Format:</b> 8–10 Page Executive Impact Report.", styles["TableCell"]),
        ],
        [
            Paragraph(
                "• <b>High-Contrast Visual:</b> Green 63% on Airbnb vs Red 0% on Commercial.<br/>"
                "• <b>Plain Translation:</b> What was measured, and what was not.<br/>"
                "• <b>Low-Friction CTA:</b> Book a 15-minute diagnostic walkthrough.",
                styles["TableCell"]
            ),
            Paragraph(
                "• <b>Full 4-Tier Matrix:</b> Performance across 108+ runs.<br/>"
                "• <b>Dual Competitor Sets:</b> Perceived vs Algorithmic leaders.<br/>"
                "• <b>6-Layer Gap Analysis:</b> Exact technical audit.<br/>"
                "• <b>3-Phase Sprint Roadmap:</b> Implementation schedule.",
                styles["TableCell"]
            ),
            Paragraph(
                "• <b>Live Visibility Shifts:</b> Tracking inclusion probabilities over time.<br/>"
                "• <b>First-Party Data:</b> Ingesting Bing AI Reports & GSC impressions.<br/>"
                "• <b>Sprint Checklist:</b> Layer 1–6 deployment tracker.",
                styles["TableCell"]
            ),
            Paragraph(
                "• <b>Before/After Delta:</b> Week 0 vs Week 10 distribution shifts.<br/>"
                "• <b>Share Comparison:</b> Client vs leaders, baseline and now.<br/>"
                "• <b>Retainer Case:</b> Model drift and competitor response management.",
                styles["TableCell"]
            ),
        ],
        [
            Paragraph("<b>Goal:</b> Conversion & Sales", styles["TableCellBold"]),
            Paragraph("<b>Goal:</b> Strategy & Alignment", styles["TableCellBold"]),
            Paragraph("<b>Goal:</b> Transparency & Retention", styles["TableCellBold"]),
            Paragraph("<b>Goal:</b> Measured Change & Renewal", styles["TableCellBold"]),
        ]
    ]
    rep_table = Table(rep_data, colWidths=rep_w)
    rep_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), C_NAVY_DARK),
        ('BOX', (0, 0), (-1, -1), 0.5, C_BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, C_BORDER),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [C_SLATE_BG, C_WHITE]),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(rep_table)
    story.append(Spacer(1, 8))

    story.append(Paragraph("Outreach Language: Plain, Specific and Accurate", styles["SubSectionHeading"]))
    story.append(Paragraph(
        "In our review of client intro documents, the biggest flaw was technical, hedged wording that buried the finding. The fix is plain words about what was measured, not claims about revenue. Saying what was not measured (customers, sales, revenue) stays, in one short sentence:",
        styles["BodyDark"]
    ))
    story.append(Spacer(1, 2))

    trans_w = [CONTENT_W * 0.50, CONTENT_W * 0.50]
    trans_data = [
        [
            Paragraph("<b>UNCLEAR / TECHNICAL</b>", styles["CardTitle"]),
            Paragraph("<b>PLAIN / ACCURATE</b>", styles["CardTitle"]),
        ],
        [
            Paragraph(
                "<i>'In our controlled provider benchmark, UDR appeared in 0 of 9 answers for commercial cleaning. However, this is our interpretation and provider models are not consumer sessions.'</i><br/><br/>"
                "<b>Result:</b> The client tunes out, feeling confused and unconvinced.",
                styles["CardText"]
            ),
            Paragraph(
                "<i>'When we asked three AI tools for Airbnb cleaning in Brighton, you were recommended in most answers. When we asked for office and tenancy contract cleaners, <b>every answer recommended Why Bother Cleaning or Silver Star, and none recommended you</b>. That is what the AI tools said in our tests; we have not measured your enquiries or sales.'</i><br/><br/>"
                "<b>Result:</b> The owner sees a specific, checkable gap and can decide whether it matters to them.",
                styles["CardText"]
            ),
        ]
    ]
    trans_table = Table(trans_data, colWidths=trans_w)
    trans_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), C_CRIMSON_BG),
        ('BACKGROUND', (1, 0), (1, -1), C_EMERALD_BG),
        ('BOX', (0, 0), (0, -1), 0.5, C_CRIMSON),
        ('BOX', (1, 0), (1, -1), 0.5, C_EMERALD),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(trans_table)
    story.append(PageBreak())

    # =========================================================================
    # PAGE 6: SECTION 5 · STATISTICAL RIGOR & TRACKING INFRASTRUCTURE
    # =========================================================================
    story.append(Paragraph("SECTION 05 · DATA & MEASUREMENT ARCHITECTURE", styles["SectionBadge"]))
    story.append(Paragraph("Statistical Rigor & Streamlit Dashboard Setup", styles["SectionHeading"]))
    story.append(Paragraph(
        "SparkToro and Gumshoe's 2,961-run study (600 volunteers; a vendor co-author) found that LLM recommendations vary from run to run: the probability of generating the exact same business list twice is <b>under 1 in 100</b>. Therefore, any agency selling 'Rank #1 in ChatGPT' is peddling snake oil. We measure visibility as a <b>statistical distribution</b> and track performance across our Streamlit platform.",
        styles["BodyDark"]
    ))
    story.append(Spacer(1, 4))

    # Statistical Rigor Box
    stat_rules_w = [CONTENT_W * 0.33, CONTENT_W * 0.33, CONTENT_W * 0.34]
    stat_rules_data = [
        [
            Paragraph("<b>1. Binomial Distribution Model</b>", styles["CardTitle"]),
            Paragraph("<b>2. Sample Size Standards</b>", styles["CardTitle"]),
            Paragraph("<b>3. Four Tracked Dimensions</b>", styles["CardTitle"]),
        ],
        [
            Paragraph(
                "Visibility is measured as an inclusion probability <i>p = k / n</i> with standard confidence intervals. Apparent shifts within ±10% on small runs are normal noise, not trends.",
                styles["CardText"]
            ),
            Paragraph(
                "• <b>Taster Audit:</b> 9 runs per intent (minimum baseline).<br/>"
                "• <b>Deep Audit:</b> 60–100 runs per client.<br/>"
                "• <b>Final Review:</b> 108 identical runs repeated at Week 10.",
                styles["CardText"]
            ),
            Paragraph(
                "1. <b>Mention Rate:</b> % answers naming brand.<br/>"
                "2. <b>Domain Citation:</b> % linking to site.<br/>"
                "3. <b>Third-Party Share:</b> Sources cited.<br/>"
                "4. <b>Factual Accuracy:</b> Name/address validity.",
                styles["CardText"]
            ),
        ]
    ]
    stat_rules_table = Table(stat_rules_data, colWidths=stat_rules_w)
    stat_rules_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), C_SLATE_BG),
        ('BOX', (0, 0), (-1, -1), 0.5, C_BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, C_BORDER),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(stat_rules_table)
    story.append(Spacer(1, 8))

    story.append(Paragraph("Codebase Architecture: Mapping Streamlit & Pipeline Modules", styles["SubSectionHeading"]))
    story.append(Paragraph(
        "Our local repository contains a production-ready application framework. We align our existing scripts with the four client delivery stages:",
        styles["BodyDark"]
    ))
    story.append(Spacer(1, 2))

    code_w = [CONTENT_W * 0.35, CONTENT_W * 0.35, CONTENT_W * 0.30]
    code_data = [
        [Paragraph("Repository Module / Path", styles["TableHeader"]), Paragraph("Functional Role & Capability", styles["TableHeader"]), Paragraph("Lifecycle Deliverable", styles["TableHeader"])],
        [
            Paragraph("`app/pages/0_AI_Discovery_Scan.py`<br/>`src/ai_prompt_generator.py`", styles["TableCellBold"]),
            Paragraph("Automates multi-intent query generation and runs rapid multi-engine sampling for new prospects.", styles["TableCell"]),
            Paragraph("Powers <b>Tier 1 Outreach Taster Packs</b>", styles["TableCellBold"]),
        ],
        [
            Paragraph("`src/ai_visibility_runner.py`<br/>`src/ai_competitive_diagnostic.py`", styles["TableCellBold"]),
            Paragraph("Executes 108+ multi-model test runs across OpenAI, Gemini, and Claude. Extracts and deduplicates Place IDs.", styles["TableCell"]),
            Paragraph("Powers <b>Tier 2 Deep Strategic Audits</b>", styles["TableCellBold"]),
        ],
        [
            Paragraph("`app/pages/8_AI_Visibility.py`<br/>`app/pages/9_AI_Competitive_Diagnostic.py`", styles["TableCellBold"]),
            Paragraph("Interactive client dashboard tracking inclusion rates over time, intent filters, and model-by-model comparisons.", styles["TableCell"]),
            Paragraph("Powers <b>Tier 3 Active Retainer Portals</b>", styles["TableCellBold"]),
        ],
        [
            Paragraph("`src/poc_audit_pdf.py`<br/>`app/pages/10_AI_Report_Generator.py`", styles["TableCellBold"]),
            Paragraph("Compiles multi-page audit payloads, verified customer review quotes, and visual matrices into print-ready PDFs.", styles["TableCell"]),
            Paragraph("Powers <b>Tier 2 & 4 Formal Reports</b>", styles["TableCellBold"]),
        ],
    ]
    code_table = Table(code_data, colWidths=code_w)
    code_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), C_NAVY_DARK),
        ('BOX', (0, 0), (-1, -1), 0.5, C_BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, C_BORDER),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [C_WHITE, C_SLATE_BG]),
        ('TOPPADDING', (0, 0), (-1, -1), 4.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4.5),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(code_table)
    story.append(Spacer(1, 8))

    story.append(Paragraph("First-Party Grounding Telemetry Integration", styles["SubSectionHeading"]))
    story.append(Paragraph(
        "To complement synthetic API test sampling, the Tier 3 dashboard ingests two free first-party telemetry sources: (1) <b>Bing Webmaster Tools AI Performance Report</b> (launched Feb 2026, recording queries where Bing grounded Copilot and ChatGPT responses), and (2) <b>Google Search Console Generative AI Reports</b>. This blends empirical test data with live user traffic telemetry.",
        styles["BodyDark"]
    ))
    story.append(PageBreak())

    # =========================================================================
    # PAGE 7: SECTION 6 · OPERATIONAL SPRINTS, PACKAGING & SOP
    # =========================================================================
    story.append(Paragraph("SECTION 06 · AGENCY OPERATIONS & PACKAGING", styles["SectionBadge"]))
    story.append(Paragraph("Operational Sprints, Commercial Packaging & SOP", styles["SectionHeading"]))
    story.append(Paragraph(
        "To execute profitably, client delivery is organized into a standardized 3-Phase Discovery Sprint (Weeks 1–6) followed by an ongoing monthly visibility retainer. Below is the operational SOP checklist, timeline, and commercial pricing model.",
        styles["BodyDark"]
    ))
    story.append(Spacer(1, 4))

    # Pricing & Product Offering Grid
    prod_w = [CONTENT_W * 0.50, CONTENT_W * 0.50]
    prod_data = [
        [
            Paragraph("<b>PRODUCT 1: AI DISCOVERABILITY SPRINT</b>", styles["CardTitle"]),
            Paragraph("<b>PRODUCT 2: AI VISIBILITY RETAINER</b>", styles["CardTitle"]),
        ],
        [
            Paragraph(
                "<b>Commercial Terms:</b> £1,500 – £2,500 (One-Off / 6 Weeks)<br/>"
                "• Comprehensive 4-Tier Intent Matrix Audit (108+ runs)<br/>"
                "• Layer 1: Crawl unblocking & Cloudflare WAF bypass<br/>"
                "• Layer 2: GBP category precision & Bing Places auto-sync<br/>"
                "• Layer 3: Vertical directory integration (Checkatrade / Yelp)<br/>"
                "• Layer 4: DMCC Act 2024 compliant review capture workflow<br/>"
                "• Layer 5: 1 Dedicated priority service landing page + proof<br/>"
                "• Layer 6: Entity statement & Companies House alignment",
                styles["CardText"]
            ),
            Paragraph(
                "<b>Commercial Terms:</b> £350 – £650 / month (Ongoing / Retainer)<br/>"
                "• Dedicated Streamlit Client Portal access<br/>"
                "• Monthly 100-run distribution audit across OpenAI/Gemini/Claude<br/>"
                "• Ingestion of Bing AI Performance & GSC telemetry<br/>"
                "• Ongoing review engine monitoring and 48-hr reply SLA<br/>"
                "• Quarterly landing page and FAQ expansion sprint<br/>"
                "• Competitive alert monitoring (tracking moves by algorithmic rivals)",
                styles["CardText"]
            ),
        ]
    ]
    prod_table = Table(prod_data, colWidths=prod_w)
    prod_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), C_SLATE_BG),
        ('BACKGROUND', (1, 0), (1, -1), C_BLUE_PALE),
        ('BOX', (0, 0), (0, -1), 0.5, C_BORDER),
        ('BOX', (1, 0), (1, -1), 0.5, C_BLUE_MAIN),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(prod_table)
    story.append(Spacer(1, 8))

    story.append(Paragraph("Agency Standard Operating Procedure (SOP) Task Checklist", styles["SubSectionHeading"]))
    sop_w = [CONTENT_W * 0.16, CONTENT_W * 0.44, CONTENT_W * 0.22, CONTENT_W * 0.18]
    sop_data = [
        [Paragraph("Sprint Phase", styles["TableHeader"]), Paragraph("Specific Operational Task", styles["TableHeader"]), Paragraph("Assigned Role", styles["TableHeader"]), Paragraph("Target Time", styles["TableHeader"])],
        [
            Paragraph("<b>Phase 1: Setup</b><br/>(Weeks 1–2)", styles["TableCellBold"]),
            Paragraph("• Audit `robots.txt` and CDN/firewall AI-blocking.<br/>• Import GBP into Bing Places and keep it matching.<br/>• Claim Apple Business and publish canonical footer.", styles["TableCell"]),
            Paragraph("Technical Lead & SEO Specialist", styles["TableCell"]),
            Paragraph("2.5 Hours<br/>(Little client effort)", styles["TableCellBold"]),
        ],
        [
            Paragraph("<b>Phase 2: On-Site</b><br/>(Weeks 3–4)", styles["TableCellBold"]),
            Paragraph("• Build dedicated high-margin service page (e.g. Commercial).<br/>• Embed verbatim customer proof blocks adjacent to scope.<br/>• Deploy direct-answer H2/H3 FAQ blocks matching fan-out queries.", styles["TableCell"]),
            Paragraph("Web Developer & Copywriter", styles["TableCell"]),
            Paragraph("4–6 Hours<br/>(Approved by client)", styles["TableCellBold"]),
        ],
        [
            Paragraph("<b>Phase 3: Off-Site</b><br/>(Weeks 5–6)", styles["TableCellBold"]),
            Paragraph("• Onboard to Checkatrade (ChatGPT App) / Yelp listings.<br/>• Deploy DMCC-compliant automated post-job review request flow.<br/>• Establish 48-hr honest owner reply routine.", styles["TableCell"]),
            Paragraph("Client Ops & Account Manager", styles["TableCell"]),
            Paragraph("2–3 Hours<br/>(System setup)", styles["TableCellBold"]),
        ],
        [
            Paragraph("<b>Outcome Review</b><br/>(Week 10)", styles["TableCellBold"]),
            Paragraph("• Re-run baseline 108 queries across identical model settings.<br/>• Compile Tier 4 Impact Report with distribution deltas.<br/>• Present findings to client and transition to monthly retainer.", styles["TableCell"]),
            Paragraph("Agency Founder & Lead Strategist", styles["TableCell"]),
            Paragraph("1.5 Hours<br/>(Review meeting)", styles["TableCellBold"]),
        ],
    ]
    sop_table = Table(sop_data, colWidths=sop_w)
    sop_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), C_NAVY_DARK),
        ('BOX', (0, 0), (-1, -1), 0.5, C_BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, C_BORDER),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [C_WHITE, C_SLATE_BG]),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(sop_table)
    story.append(Spacer(1, 8))

    # Summary Callout
    summary_text = Paragraph(
        "<b>Executive Summary & Next Steps:</b> By executing across all 6 layers rather than treating AI Discoverability as a cosmetic website edit, we work on the sources AI search tools are known or reported to use (Maps, Bing, directories, reviews, and websites), and measure the result rather than promise it. The framework keeps clients clear of review-law breaches (DMCC Act 2024), drops unproven gimmicks (`llms.txt`), and supports a recurring monitoring service.",
        styles["CalloutText"]
    )
    story.append(create_callout_box(summary_text, bg_color=C_BLUE_PALE, border_color=C_BLUE_MAIN))

    # Build document
    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"Executive Master Pack generated successfully at: {output_path}")


if __name__ == "__main__":
    output_dir = Path("/Users/rob/local-ai-discoverability/output/pdf")
    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_target = output_dir / "Local AI Discoverability - Executive Master Pack.pdf"
    generate_pdf(str(pdf_target))
