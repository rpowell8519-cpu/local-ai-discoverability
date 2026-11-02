"""Professional, health and other service businesses get their own groups instead of "Other local business"."""
from src.feature_extraction import classify_groups
from src.taxonomy import GROUP_LABELS, GROUP_RELATIONSHIPS, GROUP_RULES


def group_of(type_, subtypes=""):
    return classify_groups({"type": type_, "subtypes": subtypes or type_})[0]


def test_british_and_american_spellings_land_in_the_same_group():
    assert group_of("Counsellor") == group_of("Counselor") == "mental_health"
    assert group_of("Jewellery Store") == group_of("Jewelry store") == "jewellery_watches"
    assert group_of("Fitness centre") == group_of("Fitness center") == "fitness_sport"


def test_common_service_types_are_grouped():
    assert group_of("Accountant") == "accounting_finance"
    assert group_of("Dental clinic") == "dental_care"
    assert group_of("Estate Agent") == "property"
    assert group_of("Lawyer", "Lawyer, Legal services") == "legal_services"
    assert group_of("Veterinarian") == "vets_pets"
    assert group_of("MOT centre") == "vehicle_repair"


def test_an_osteopath_who_also_massages_is_a_therapist_not_a_beauty_salon():
    assert group_of("Osteopath", "Osteopath, Massage therapist, Chiropractor") == "physical_therapies"
    assert group_of("Massage therapist") == "beauty_wellness"


def test_every_group_has_a_label_and_relates_to_itself():
    assert set(GROUP_RULES) | {"other"} == set(GROUP_LABELS)
    for group in GROUP_RULES:
        assert GROUP_RELATIONSHIPS[group][group] == 1.00, group
