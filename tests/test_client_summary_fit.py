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
