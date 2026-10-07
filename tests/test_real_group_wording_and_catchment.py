"""Report wording and the local catchment apply to the groups businesses are really stored under.

Both once used only informal names ("salon", "coworking") that no stored business has, so almost
every report silently fell back to the general wording and the wide catchment. Every stored group
is listed here on purpose: adding a group to the taxonomy fails this test until someone decides
what wording and catchment it should get.
"""
from src.client_summary.actions import _DEFAULT, _PROFILES, has_builtin_profile, profile_for
from src.feature_extraction import classify_groups
from src.report_competitors import DEFAULT_CATCHMENT_MILES, WALK_IN_CATCHMENT_MILES, catchment_radius_miles
from src.taxonomy import GROUP_LABELS

# group: (built-in wording, or None for general wording; whether customers choose it very locally)
EXPECTED = {
    "bars_pubs": ("hospitality", True),
    "coffee_cafes": ("hospitality", True),
    "restaurants": ("hospitality", True),
    "hair_services": ("beauty", True),
    "beauty_wellness": ("beauty", True),
    "childcare_nurseries": (None, True),
    "cleaning_services": ("trades", False),
    "building_trades": ("trades", False),
    "workspaces": ("workspace", False),
    "nightlife_entertainment": (None, False),
    "saunas": (None, False),
    "other": (None, False),
}


def test_every_stored_group_has_a_decided_wording_and_catchment():
    assert set(EXPECTED) == set(GROUP_LABELS)
    for group, (wording, local) in EXPECTED.items():
        assert profile_for(group) == (_PROFILES[wording] if wording else _DEFAULT), group
        assert has_builtin_profile(group) is bool(wording), group
        assert catchment_radius_miles(group) == (WALK_IN_CATCHMENT_MILES if local else DEFAULT_CATCHMENT_MILES), group


def test_a_business_classified_from_google_categories_gets_its_own_wording():
    salon, *_ = classify_groups({"category": "Hair salon", "type": "Hair salon", "subtypes": "Hair salon"})
    builder, *_ = classify_groups({"category": "Building firm", "type": "Building firm", "subtypes": "Builder"})
    assert "book an appointment" == profile_for(salon).booking and catchment_radius_miles(salon) == 3
    assert "request a quote or book a visit" == profile_for(builder).booking and catchment_radius_miles(builder) == 15


def test_the_older_informal_names_still_work():
    assert profile_for("salon") == _PROFILES["beauty"] and profile_for("coworking") == _PROFILES["workspace"]
    assert catchment_radius_miles("salon") == 3 and catchment_radius_miles("pub") == 3
