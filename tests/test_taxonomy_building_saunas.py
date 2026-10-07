"""Builders and saunas are recognised by their own taxonomy groups, not left in "Other"."""
from src.feature_extraction import classify_groups
from src.report_competitors import catchment_radius_miles
from src.taxonomy import GROUP_LABELS, GROUP_RELATIONSHIPS


def group(category="", business_type="", subtypes=""):
    return classify_groups({"category": category, "type": business_type, "subtypes": subtypes})[0]


def test_common_google_categories_for_a_builder_are_recognised():
    for category in ("Construction company", "Building firm", "Home builder", "Builder", "Contractor",
                     "General contractor", "Roofing contractor", "Carpenter", "Property maintenance"):
        assert group(category) == "building_trades", category
    assert group(business_type="Roofing Service") == "building_trades"
    assert group(subtypes="Kitchen renovator, Bathroom renovator, Plasterer") == "building_trades"


def test_related_businesses_that_are_not_builders_stay_out_of_the_group():
    for business_type in ("Plumber", "Electrician", "Architect", "Surveyor", "Building materials supplier",
                          "Estate agent", "Recruiter", "Garden building supplier"):
        assert group(business_type=business_type) == "other", business_type
    # A cleaner that also lists construction work is still a cleaner.
    assert group(business_type="Cleaners", subtypes="Cleaners, Carpet cleaning service, Construction Company, "
                                                    "House cleaning service") == "cleaning_services"


def test_saunas_are_their_own_group_and_a_spa_stays_in_beauty_and_wellness():
    assert group("Sauna", "Sauna", "Sauna") == "saunas"
    assert group("Public sauna", "Public sauna", "Public sauna, Sauna") == "saunas"
    assert group(subtypes="Sauna") == "saunas"
    assert group("Spa", "Spa", "Spa") == "beauty_wellness"
    assert group("Spa", "Day spa", "Day spa, Massage therapist, Sauna") == "beauty_wellness"


def test_both_groups_have_plain_labels_and_keep_the_default_catchment():
    assert GROUP_LABELS["building_trades"] == "Builders & building trades"
    assert GROUP_LABELS["saunas"] == "Saunas"
    assert GROUP_RELATIONSHIPS["building_trades"] == {"building_trades": 1.00}
    assert catchment_radius_miles("building_trades") == catchment_radius_miles("workspaces")
    assert catchment_radius_miles("saunas") == catchment_radius_miles("workspaces")
