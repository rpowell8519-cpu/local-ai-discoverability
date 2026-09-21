"""The summary must fit for any realistic business, not only for tidy demonstration data."""
import copy
from io import BytesIO

import pytest
from pypdf import PdfReader

from src.client_summary import ReportLayoutError, render_pdf
from src.client_summary import pdf as renderer
from src.client_summary.actions import build_actions
from tests.wrap_fixture import wrap_summary
from tests.test_client_summary_adapter import CONTACT_GAP, CONTACT_OK, CRAWLER_GAP, CRAWLER_OK


def pages(data):
    return len(PdfReader(BytesIO(render_pdf(data))).pages)


def test_the_first_real_wrap_run_renders_instead_of_failing_on_page_4():
    # Regression: "Page 4 is too long" stopped the very first live report.
    assert pages(wrap_summary()) == 6


def test_wrap_needs_only_the_first_condensing_step_and_loses_no_content():
    validated = renderer.validate_report(wrap_summary())
    with pytest.raises(ReportLayoutError):
        renderer._render(validated, 0)
    text = " ".join(" ".join(p.extract_text().split()) for p in PdfReader(BytesIO(renderer._render(validated, 1))).pages)
    for expected in ("PLATF9RM Brighton", "Runway East Brighton", "Plus X Innovation Brighton", "E1:", "E2:", "wrap.space/robots.txt"):
        assert expected in text


def test_a_condensed_name_is_cut_at_a_word_boundary_with_an_ellipsis_never_mid_word():
    cut = renderer.one_line("PLATF9RM Brighton - Coworking, Offices & Events", "Helvetica", 12, 186)
    assert cut.endswith("…") and "Offices" not in cut and not cut[:-1].endswith(" ")
    assert renderer.one_line("The Skiff", "Helvetica", 12, 186) == "The Skiff"


def test_type_is_never_made_smaller_to_fit():
    source = open(renderer.__file__).read()
    for size in ("fontSize=8,", "fontSize=7,", "fontSize=6,"):
        assert size not in source


@pytest.mark.parametrize("change", ["names", "evidence", "limitations", "everything"])
def test_content_at_the_contract_maximum_still_renders(change):
    d = wrap_summary()
    long_name = ("Extremely Long Comparison Business Name Ltd " * 3)[:75].strip()
    long_evidence = [{"id": f"E{i}", "observation": ("An observation of the maximum permitted length. " * 6)[:220],
                      "source": ("https://example.co.uk/a/very/long/path/to/a/page " * 5)[:200]} for i in (1, 2, 3)]
    long_limits = [("A limitation at the maximum permitted length for this contract. " * 5)[:240] for _ in range(4)]
    if change in ("names", "everything"):
        for b in d["businesses"][1:]:
            b["name"] = long_name
    if change in ("evidence", "everything"):
        d["evidence"] = long_evidence
    if change in ("limitations", "everything"):
        d["limitations"] = long_limits
    assert pages(d) == 6


def test_content_that_truly_cannot_fit_is_refused_with_a_clear_message_not_clipped():
    d = wrap_summary()
    for a in d["actions"]:
        a.update(title=("Long action title " * 5)[:75].strip(), task=("Detailed task description with several words. " * 10)[:380],
                 owner=("Responsible person " * 6)[:100], done_when=("Completion criteria with words. " * 8)[:200])
    with pytest.raises(ReportLayoutError, match="Page 5 is too long"):
        render_pdf(d)


FINDINGS = {
    "none": [], "crawler gap": [CRAWLER_GAP], "contact gap": [CONTACT_GAP], "both gaps": [CRAWLER_GAP, CONTACT_GAP],
    "both ok": [CRAWLER_OK, CONTACT_OK], "crawler gap, contact ok": [CRAWLER_GAP, CONTACT_OK],
}


@pytest.mark.parametrize("group", ["pub", "salon", "cleaning_services", "coworking", None])
@pytest.mark.parametrize("findings", list(FINDINGS))
@pytest.mark.parametrize("label_length", [12, 65])
def test_every_real_action_and_finding_combination_fits(group, findings, label_length):
    d = copy.deepcopy(wrap_summary())
    if label_length == 65:
        for q in d["questions"]:
            q["label"] = (q["label"] + " x" * 40)[:65]
    measured = [{"id": q["id"], "label": q["label"], "answers": q["complete"], "appearances": q["appearances"]} for q in d["questions"]]
    numbered = [dict(f, id=f"E{i}") for i, f in enumerate(FINDINGS[findings], 1)]
    d["actions"] = build_actions(measured, business_group=group, findings=numbered)
    d["evidence"] = [{"id": f["id"], "observation": f["observation"], "source": f["source"]} for f in numbered]
    assert pages(d) == 6


def test_a_tile_label_is_measured_not_guessed_so_long_question_wording_never_breaks_page_1():
    # Regression: showing each question by its own wording put 50+ character labels on the page 1 tiles,
    # which the old estimate let through and the renderer then refused.
    label = "Recommend places for co working near Brighton station and the seafront area"
    text = renderer.tile_label(label)
    assert text.startswith("Answers about Recommend") and text.endswith("…")
    from reportlab.platypus import Paragraph
    from reportlab.lib.styles import ParagraphStyle
    height = Paragraph(renderer.safe(text), ParagraphStyle("t", fontName="Helvetica", fontSize=11, leading=16)).wrap(135, 200)[1]
    assert height <= 34
    assert renderer.tile_label("Meeting rooms") == "Answers about Meeting rooms"


# ---------------------------------------------------------------- the business plus seven others
def with_eight_businesses(long_names=False):
    d = copy.deepcopy(wrap_summary())
    names = ["Plus X Innovation Brighton", "Runway East Brighton | Office Space", "PLATF9RM Brighton - Coworking, Offices & Events",
             "Freedom Works - The Palace Workspace", "Projects Nile House", "Spaces Trafalgar Place", "The Skiff"]
    counts = [30, 23, 33, 0, 7, 7, 7]
    d["businesses"] = [d["businesses"][0]] + [
        {"id": f"biz-{i}", "name": (("Extremely Long Comparison Business Name Ltd " * 3)[:75].strip() if long_names else n), "appearances": c}
        for i, (n, c) in enumerate(zip(names, counts))
    ]
    return d


def test_the_business_plus_seven_others_renders_with_all_eight_bars():
    d = with_eight_businesses()
    assert len(d["businesses"]) == 8 and pages(d) == 6
    text = " ".join(" ".join(p.extract_text().split()) for p in PdfReader(BytesIO(render_pdf(d))).pages[3:4])
    for name in ("Freedom Works", "Projects Nile House", "The Skiff", "PLATF9RM"):
        assert name in text


def test_eight_businesses_with_maximum_length_names_still_render():
    assert pages(with_eight_businesses(long_names=True)) == 6


def test_eight_businesses_with_the_worst_findings_the_real_checks_can_produce_still_render():
    from src.site_checks import CrawlerAccess, AI_SEARCH_CRAWLERS, ContactCheck, contact_finding, crawler_finding

    everything_blocked = CrawlerAccess("blocked", tuple(AI_SEARCH_CRAWLERS), "https://www.a-rather-long-business-name.co.uk/robots.txt", "2026-09-21", True)
    both_wrong = ContactCheck(
        ("the Google listing gives 01273 123456; the pages read show 01273 654321 and 01273 111222 but not that number",
         "the Google listing has postcode BN1 3XE; the pages read show BN3 2FL but not that postcode"),
        ("phone number", "postcode"), (), ("https://www.a-rather-long-business-name.co.uk/contact-us/find-us-here",), "2026-09-13")
    findings = [crawler_finding(everything_blocked, "E1"), contact_finding(both_wrong, "E2")]
    d = with_eight_businesses(long_names=True)
    d["evidence"] = [{"id": f["id"], "observation": f["observation"], "source": f["source"]} for f in findings]
    d["limitations"] = ["2 business name(s) in the answers could not be matched to a verified business and are not shown.",
                        "A reviewer confirmed that the AI answers “WRAP” and “Wrap Brighton” refer to this business."]
    assert pages(d) == 6


def test_an_impossible_combination_is_refused_cleanly_never_clipped():
    d = with_eight_businesses(long_names=True)
    d["evidence"] = [{"id": f"E{i}", "observation": ("An observation of the maximum permitted length. " * 6)[:220],
                      "source": ("https://example.co.uk/a/very/long/path/to/a/page " * 5)[:200]} for i in (1, 2, 3)]
    d["limitations"] = [("A limitation at the maximum permitted length for this contract. " * 5)[:240] for _ in range(4)]
    try:
        assert pages(d) == 6            # fitting is fine
    except ReportLayoutError as error:
        assert "too long" in str(error)  # refusing with a clear message is the only other acceptable outcome


def test_an_owner_named_business_with_no_appearances_is_shown_with_a_zero_bar():
    d = with_eight_businesses()
    text = " ".join(" ".join(p.extract_text().split()) for p in PdfReader(BytesIO(render_pdf(d))).pages[3:4])
    assert "Freedom Works" in text  # 0 appearances, but the owner asked about it, so it is not dropped


def test_more_than_seven_comparison_businesses_is_refused_by_the_contract():
    d = with_eight_businesses()
    d["businesses"].append({"id": "one-too-many", "name": "Ninth Business", "appearances": 1})
    with pytest.raises(Exception, match="expected 1-8 items"):
        render_pdf(d)
