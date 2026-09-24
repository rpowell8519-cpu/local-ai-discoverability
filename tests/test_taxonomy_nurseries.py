"""A nursery/childcare business is recognised by its own taxonomy group, not left in "Other"."""
from src.feature_extraction import classify_groups
from src.report_competitors import catchment_radius_miles
from src.taxonomy import GROUP_LABELS


def test_common_google_categories_for_a_nursery_are_recognised():
    for category in ("Day care center", "Preschool", "Nursery school", "Child care agency"):
        primary_group, _, confidence, reasons = classify_groups({"category": category, "type": "", "subtypes": ""})
        assert primary_group == "childcare_nurseries", category
        assert confidence > 0.3 and reasons


def test_a_nursery_named_business_still_matches_on_its_type_or_subtypes_alone():
    by_type, *_ = classify_groups({"category": "", "type": "Preschool", "subtypes": ""})
    by_subtype, *_ = classify_groups({"category": "", "type": "", "subtypes": "Nursery school, Childminder"})
    assert by_type == "childcare_nurseries" and by_subtype == "childcare_nurseries"


def test_the_group_has_a_plain_label_for_the_ai_visibility_sidebar():
    assert GROUP_LABELS["childcare_nurseries"] == "Nurseries & childcare"


def test_a_nursery_is_chosen_as_locally_as_a_salon_not_over_the_wide_default():
    assert catchment_radius_miles("childcare_nurseries") == 3
    assert catchment_radius_miles("workspaces") == 15  # unrelated groups are unaffected


def test_an_unrelated_business_is_not_mistaken_for_a_nursery():
    primary_group, *_ = classify_groups({"category": "Coworking space", "type": "", "subtypes": ""})
    assert primary_group != "childcare_nurseries"
