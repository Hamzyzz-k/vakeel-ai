from collections import Counter

from app.legal.statute_catalog import INGESTIBLE_STATUTES, STATUTE_CATALOG


def test_catalog_has_four_review_tranches():
    assert len(STATUTE_CATALOG) == 42
    assert Counter(spec.tranche for spec in STATUTE_CATALOG) == {1: 10, 2: 10, 3: 12, 4: 10}


def test_only_source_verified_statutes_are_ingestible():
    assert {spec.key for spec in INGESTIBLE_STATUTES} == {
        "constitution",
        "specific_relief_act_1963",
        "limitation_act_1963",
        "karnataka_stamp_act_1957",
        "karnataka_land_revenue_act_1964",
        "contract_act_1872",
        "sale_of_goods_act_1930",
        "consumer_protection_act_2019",
        "bns_2023",
        "bnss_2023",
        "bsa_2023",
        "information_technology_act_2000",
        "real_estate_act_2016",
        "transfer_of_property_act_1882",
        "karnataka_rent_act_1999",
        "registration_act_1908",
        "easements_act_1882",
        "arbitration_act_1996",
        "negotiable_instruments_act_1881",
        "motor_vehicles_act_1988",
        "central_motor_vehicles_rules_1989",
        "karnataka_motor_vehicles_rules_1989",
    }
    for spec in INGESTIBLE_STATUTES:
        assert spec.source_url and spec.source_url.startswith("https://")
        assert spec.verified_on
        assert spec.lifecycle_status.startswith("in_force")


def test_catalog_keys_titles_and_aliases_are_nonempty():
    assert len({spec.key for spec in STATUTE_CATALOG}) == 42
    assert len({spec.title.casefold() for spec in STATUTE_CATALOG}) == 42
    assert all(spec.aliases for spec in STATUTE_CATALOG)
