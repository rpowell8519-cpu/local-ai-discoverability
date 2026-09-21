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


def test_run_location_prefers_service_areas_then_the_businesss_city():
    from src.report_competitors import resolve_run_location

    assert resolve_run_location(["Leeds", " Harrogate "], "Manchester") == "Leeds, Harrogate"
    assert resolve_run_location([], "Manchester") == "Manchester"
    assert resolve_run_location(["", "  "], " Bath ") == "Bath"


def test_run_location_has_no_default_so_a_run_cannot_start_in_the_wrong_place():
    from src.report_competitors import resolve_run_location

    assert resolve_run_location([], None) == ""
    assert resolve_run_location([], float("nan")) == ""
    assert resolve_run_location([], "  ") == ""


def test_report_page_has_no_hardcoded_local_default():
    from pathlib import Path

    page = Path(__file__).resolve().parents[1] / "app" / "pages" / "10_AI_Report_Generator.py"
    source = page.read_text()
    assert 'or "Brighton and Hove"' not in source
    assert "location_context=run_location" in source
