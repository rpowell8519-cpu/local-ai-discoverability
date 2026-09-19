from src.report_competitors import (
    catchment_radius_miles,
    classify_location,
    match_owner_competitors,
)


def test_business_type_changes_default_catchment() -> None:
    for group in ("salons", "cafes", "pubs", "restaurants", "hair_beauty"):
        assert catchment_radius_miles(group) == 3
    assert catchment_radius_miles("cleaning_services") == 15
    assert catchment_radius_miles("specialist") == 15
    assert catchment_radius_miles("destination") == 15


def test_location_classification_preserves_out_of_area_result() -> None:
    target = {"latitude": 50.8225, "longitude": -0.1372}
    result = classify_location(
        {"latitude": 51.5074, "longitude": -0.1278, "city": "London"},
        target=target,
        primary_group="restaurants",
    )
    assert result["location_classification"] == "outside"
    assert result["distance_miles"] > 40


def test_reviewer_can_widen_service_catchment() -> None:
    target = {"latitude": 50.8225, "longitude": -0.1372}
    candidate = {"latitude": 51.20, "longitude": -0.14, "city": "Wider area"}
    narrow = classify_location(candidate, target=target, primary_group="cleaning_services", radius_miles=25)
    wide = classify_location(candidate, target=target, primary_group="cleaning_services", radius_miles=60)
    assert narrow["location_classification"] != "local"
    assert wide["location_classification"] == "local"


def test_owner_competitor_with_zero_visibility_is_retained() -> None:
    matches = match_owner_competitors(
        ["Daisy Fresh", "Unknown Local Cleaner"],
        [{"google_place_id": "place-daisy", "business_name": "Daisy Fresh Cleaning Ltd"}],
        {},
    )
    assert matches[0]["match_status"] == "matched"
    assert matches[0]["recommendations"] == 0
    assert matches[0]["visibility_status"] == "Not recommended in this benchmark"
    assert matches[1]["match_status"] == "needs_confirmation"
