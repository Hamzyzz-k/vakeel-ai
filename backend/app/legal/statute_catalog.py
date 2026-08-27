"""Single source of truth for Vakeel AI's statutory coverage.

The catalogue deliberately separates *planned* coverage from *ready*
coverage.  A title appearing in this file does not make it safe to answer
questions about that Act: ingestion is enabled only after an official India
Code item and English PDF bitstream have been resolved and checked.
"""
from __future__ import annotations

from dataclasses import dataclass


CENTRAL_ACTS_COLLECTION = "69a0c1fb-7b22-4481-b16a-1dc59b5d02e6"
KARNATAKA_ACTS_COLLECTION = "960261cd-2b69-4ed0-916f-c52423f1253d"


@dataclass(frozen=True)
class StatuteSpec:
    key: str
    title: str
    filename: str
    domain: str
    tranche: int
    aliases: tuple[str, ...]
    collection_uuid: str | None = CENTRAL_ACTS_COLLECTION
    source_title: str | None = None
    state: str | None = None
    lifecycle_status: str = "verify_before_ingest"
    parser_profile: str = "sections"
    instrument_kind: str = "act"
    effective_from: str | None = None
    effective_to: str | None = None
    ingestion_enabled: bool = False
    act_id: str | None = None
    item_uuid: str | None = None
    bitstream_uuid: str | None = None
    verified_on: str | None = None
    expected_sections: int | None = None
    source_url_override: str | None = None
    source_note: str | None = None

    @property
    def source_url(self) -> str | None:
        if self.source_url_override:
            return self.source_url_override
        if not self.bitstream_uuid:
            return None
        return f"https://indiacode.gov.in/server/api/core/bitstreams/{self.bitstream_uuid}/content"

    @property
    def discovery_title(self) -> str:
        return self.source_title or self.title

    @property
    def jurisdiction(self) -> str:
        return f"India/{self.state}" if self.state else "India"

    @property
    def authority_level(self) -> int:
        return 1 if self.key == "constitution" else 2

    @property
    def source_type(self) -> str:
        if self.key == "constitution":
            return "CONSTITUTION"
        return "RULES" if self.instrument_kind == "rules" else "ACT"

    def validate(self) -> None:
        if self.tranche not in {1, 2, 3, 4}:
            raise ValueError(f"{self.key}: tranche must be 1-4")
        if self.instrument_kind not in {"act", "rules"}:
            raise ValueError(f"{self.key}: instrument_kind must be act or rules")
        if self.ingestion_enabled:
            missing = [
                name
                for name, value in (
                    ("source_url", self.source_url),
                    ("verified_on", self.verified_on),
                )
                if not value
            ]
            if missing:
                raise ValueError(f"{self.key}: enabled statute lacks {', '.join(missing)}")


def _central(
    key: str,
    title: str,
    domain: str,
    tranche: int,
    *aliases: str,
    **metadata,
) -> StatuteSpec:
    return StatuteSpec(
        key=key,
        title=title,
        filename=f"{key}.pdf",
        domain=domain,
        tranche=tranche,
        aliases=tuple(dict.fromkeys((title, *aliases))),
        **metadata,
    )


def _karnataka(
    key: str,
    title: str,
    domain: str,
    tranche: int,
    *aliases: str,
    **metadata,
) -> StatuteSpec:
    return _central(
        key,
        title,
        domain,
        tranche,
        *aliases,
        collection_uuid=KARNATAKA_ACTS_COLLECTION,
        state="Karnataka",
        **metadata,
    )


# Four batches of ten.  Tranche 1 retains the four already-verified Acts and
# adds the six laws that unlock the largest immediate set of user scenarios.
# Later entries remain non-ingestible until source discovery and parser QA
# have both completed.
STATUTE_CATALOG: tuple[StatuteSpec, ...] = (
    # Tranche 1: current core + criminal procedure/evidence, digital,
    # property and Karnataka tenancy.
    _central(
        "contract_act_1872", "The Indian Contract Act, 1872", "contract", 1,
        "Indian Contract Act", "Contract Act", "ICA 1872",
        lifecycle_status="in_force", ingestion_enabled=True,
        bitstream_uuid="e7571d39-11a7-4a2c-86e3-c515ae43e617",
        verified_on="2026-08-26", expected_sections=268,
    ),
    _central(
        "sale_of_goods_act_1930", "The Sale of Goods Act, 1930", "contract", 1,
        "Sale of Goods Act", "SOGA",
        lifecycle_status="in_force", ingestion_enabled=True,
        bitstream_uuid="8d3daeca-d1b6-4692-aed1-758ded8ae027",
        verified_on="2026-08-26", expected_sections=67,
    ),
    _central(
        "consumer_protection_act_2019", "The Consumer Protection Act, 2019", "consumer", 1,
        "Consumer Protection Act", "CPA 2019",
        lifecycle_status="in_force", ingestion_enabled=True,
        bitstream_uuid="001fc870-0321-4c1f-8c29-c202608c9442",
        verified_on="2026-08-26", expected_sections=107,
    ),
    _central(
        "bns_2023", "The Bharatiya Nyaya Sanhita, 2023", "criminal", 1,
        "Bharatiya Nyaya Sanhita", "BNS", "BNS 2023",
        lifecycle_status="in_force", ingestion_enabled=True,
        bitstream_uuid="8007a80e-259b-429d-9ca4-1a2f474b5000",
        verified_on="2026-08-26", expected_sections=358,
    ),
    _central("bnss_2023", "The Bharatiya Nagarik Suraksha Sanhita, 2023", "criminal_procedure", 1,
             "Bharatiya Nagarik Suraksha Sanhita", "BNSS", "BNSS 2023",
             lifecycle_status="in_force", effective_from="2024-07-01",
             ingestion_enabled=True, verified_on="2026-08-27", expected_sections=531,
             act_id="AC_CEN_5_23_00049_202346_1719552320687",
             item_uuid="72592ac7-d084-4545-95d3-0c98dc49fac3",
             bitstream_uuid="dab4cf5a-e218-4c87-b397-d6ddd11a2b80"),
    _central("bsa_2023", "The Bharatiya Sakshya Adhiniyam, 2023", "evidence", 1,
             "Bharatiya Sakshya Adhiniyam", "BSA", "BSA 2023",
             lifecycle_status="in_force", effective_from="2024-07-01",
             ingestion_enabled=True, verified_on="2026-08-27", expected_sections=170,
             act_id="AC_CEN_5_23_00049_2023-47_1719292804654",
             item_uuid="9e461245-2c13-4171-9d9d-267425c01e1d",
             bitstream_uuid="fa0f7526-d871-41f2-a644-2a42952211f5"),
    _central("information_technology_act_2000", "The Information Technology Act, 2000", "technology", 1,
             "Information Technology Act", "IT Act", "IT Act 2000",
             lifecycle_status="in_force_provision_specific", effective_from="2000-10-17",
             ingestion_enabled=True, verified_on="2026-08-27", expected_sections=125,
             act_id="AC_CEN_45_76_00001_200021_1517807324077",
             item_uuid="d41fe391-b9c0-40b1-afdc-ad034c7ac62f",
             bitstream_uuid="61831783-4cf1-499b-9c2c-0b78f5fee4e9"),
    _central("real_estate_act_2016", "The Real Estate (Regulation and Development) Act, 2016", "real_estate", 1,
             "Real Estate Regulation and Development Act", "RERA", "RERA Act",
             lifecycle_status="in_force_provision_specific", effective_from="2017-05-01",
             ingestion_enabled=True, verified_on="2026-08-27", expected_sections=92,
             act_id="AC_CEN_17_19_00033_201616_1517807328405",
             item_uuid="769e081c-f8d1-4987-ab07-b93a11ae53ad",
             bitstream_uuid="b9a6905c-ede5-48e1-8c87-3d28be9707d7"),
    _central("transfer_of_property_act_1882", "The Transfer of Property Act, 1882", "property", 1,
             "Transfer of Property Act", "TPA",
             lifecycle_status="in_force", effective_from="1882-07-01",
             ingestion_enabled=True, verified_on="2026-08-27", expected_sections=148,
             act_id="AC_CEN_3_20_00042_188204_1523272233671",
             item_uuid="2b436b95-ae89-4c5f-ab70-3d5ef5ffd8e8",
             bitstream_uuid="df9f8770-4efe-4cf9-85ba-1ea884649679"),
    _karnataka("karnataka_rent_act_1999", "The Karnataka Rent Act, 1999", "tenancy", 1,
               "Karnataka Rent Act", "KRA 1999",
               lifecycle_status="in_force", effective_from="2001-12-31",
               ingestion_enabled=True, verified_on="2026-08-27", expected_sections=70,
               act_id="AC_KA_71_596_00019_34_1551958799294",
               item_uuid="18aab749-e4c5-4504-82bc-65a442000855",
               bitstream_uuid="42804bcc-e054-46ab-9253-e39fca1a2a25"),

    # Tranche 2: civil disputes and property transactions.
    _central("constitution", "The Constitution of India", "constitutional", 2,
             "Constitution of India", "Indian Constitution",
             collection_uuid="d5475e8d-1998-4ac8-8694-82f941074bb7",
             source_title="The Constitution of India in English 2026",
             parser_profile="constitution_articles",
             lifecycle_status="in_force", effective_from="1950-01-26",
             ingestion_enabled=True, verified_on="2026-08-27", expected_sections=500,
             item_uuid="544213ec-4072-44b2-a6fc-69fb84df2001",
             bitstream_uuid="14b362b4-9088-40ed-a098-d1df68ed7589"),
    _central("civil_procedure_code_1908", "The Code of Civil Procedure, 1908", "civil_procedure", 2,
             "Code of Civil Procedure", "Civil Procedure Code", "CPC", "CPC 1908",
             act_id="AC_CEN_3_20_00051_190805_1523340333624",
             item_uuid="3d38ec80-965e-4df0-a2d2-3d97cb1dc702",
             bitstream_uuid="fc9dad3f-97a9-4216-843b-934665693468"),
    _central("specific_relief_act_1963", "The Specific Relief Act, 1963", "civil_remedies", 2,
             "Specific Relief Act", "SRA 1963",
             parser_profile="sections_and_schedule",
             lifecycle_status="in_force", effective_from="1964-03-01",
             ingestion_enabled=True, verified_on="2026-08-27", expected_sections=49,
             act_id="AC_CEN_3_20_00009_196347_1517807320084",
             item_uuid="e0a1c7bb-8bed-47d7-a0b6-9fd3c8a3944c",
             bitstream_uuid="d47b330c-8fdb-4a6b-9fcf-72201b62e1ba"),
    _central("limitation_act_1963", "The Limitation Act, 1963", "civil_procedure", 2,
             "Limitation Act",
             parser_profile="sections_and_limitation_schedule",
             lifecycle_status="in_force", effective_from="1964-01-01",
             ingestion_enabled=True, verified_on="2026-08-27", expected_sections=169,
             act_id="AC_CEN_3_20_00005_196336_1517807319297",
             item_uuid="5e69d11a-63e7-4a63-b86f-e063bcdeaee2",
             bitstream_uuid="3900a3de-8131-435a-9af0-ebad58242273"),
    _central("registration_act_1908", "The Registration Act, 1908", "property", 2,
             "Registration Act",
             lifecycle_status="in_force", effective_from="1909-01-01",
             ingestion_enabled=True, verified_on="2026-08-27", expected_sections=96,
             act_id="AC_CEN_18_43_00004_190816_1523340837338",
             item_uuid="1930ffdb-10f3-4d71-bc42-f91303dae14e",
             bitstream_uuid="0b9471f4-9b18-47dd-bb76-cccf556db838"),
    _central("easements_act_1882", "The Indian Easements Act, 1882", "property", 2,
             "Indian Easements Act", "Easements Act",
             lifecycle_status="in_force", effective_from="1882-07-01",
             ingestion_enabled=True, verified_on="2026-08-27", expected_sections=64,
             act_id="AC_CEN_3_20_00043_188205_1523272326474",
             item_uuid="b020b170-1f08-440a-828f-8559cdc5f062",
             bitstream_uuid="a4b116ba-62b0-4a50-a010-617417512559"),
    _central("arbitration_act_1996", "The Arbitration and Conciliation Act, 1996", "dispute_resolution", 2,
             "Arbitration and Conciliation Act", "Arbitration Act", "ACA 1996",
             lifecycle_status="in_force", effective_from="1996-08-22",
             ingestion_enabled=True, verified_on="2026-08-27", expected_sections=106,
             act_id="AC_CEN_3_46_00004_199626_1517807323919",
             item_uuid="51601006-0e76-4a81-83ce-739f3a021112",
             bitstream_uuid="c368a901-3738-47f6-acb8-9885147945ec"),
    _central("negotiable_instruments_act_1881", "The Negotiable Instruments Act, 1881", "commercial", 2,
             "Negotiable Instruments Act", "NI Act", "NIA 1881",
             lifecycle_status="in_force", effective_from="1882-03-01",
             ingestion_enabled=True, verified_on="2026-08-27", expected_sections=155,
             act_id="AC_CEN_2_33_00042_00042_1523271998701",
             item_uuid="38b01c2d-f1b8-4b1f-a8bf-86b4da3b72a0",
             bitstream_uuid="82bf1927-5e52-4aab-a876-50552c5952cd"),
    _karnataka("karnataka_stamp_act_1957", "The Karnataka Stamp Act, 1957", "property", 2,
               "Karnataka Stamp Act",
               parser_profile="sections_and_trailing_schedule",
               lifecycle_status="in_force", effective_from="1958-06-01",
               ingestion_enabled=True, verified_on="2026-08-27", expected_sections=91,
               act_id="AC_KA_71_596_00001_34_1551857974089",
               item_uuid="c0b1c569-0f8c-4f93-bbb3-24de748d77d2",
               bitstream_uuid="03e18998-f449-440b-9d91-e8d1539e5d82"),
    _karnataka("karnataka_land_revenue_act_1964", "The Karnataka Land Revenue Act, 1964", "land", 2,
               "Karnataka Land Revenue Act", "KLRA",
               parser_profile="sections_and_trailing_schedule",
               lifecycle_status="in_force", effective_from="1964-04-01",
               ingestion_enabled=True, verified_on="2026-08-27", expected_sections=224,
               act_id="AC_KA_71_596_00007_12_1551859218716",
               item_uuid="807bf8b2-da59-40e5-8d00-0ff945ae7a64",
               bitstream_uuid="2b21d735-b27e-477e-ba6c-e088ba22c07f"),

    # Tranche 3: business, digital rights, transparency and transport.
    _central("partnership_act_1932", "The Indian Partnership Act, 1932", "commercial", 3,
             "Indian Partnership Act", "Partnership Act"),
    _central("companies_act_2013", "The Companies Act, 2013", "corporate", 3,
             "Companies Act"),
    _central("llp_act_2008", "The Limited Liability Partnership Act, 2008", "corporate", 3,
             "Limited Liability Partnership Act", "LLP Act"),
    _central("insolvency_bankruptcy_code_2016", "The Insolvency and Bankruptcy Code, 2016", "insolvency", 3,
             "Insolvency and Bankruptcy Code", "IBC", "IBC 2016"),
    _central("competition_act_2002", "The Competition Act, 2002", "competition", 3,
             "Competition Act"),
    _central("msmed_act_2006", "The Micro, Small and Medium Enterprises Development Act, 2006", "commercial", 3,
             "MSMED Act", "MSME Development Act"),
    _central("dpdp_act_2023", "The Digital Personal Data Protection Act, 2023", "data_protection", 3,
             "Digital Personal Data Protection Act", "DPDP Act", "DPDPA"),
    _central("right_to_information_act_2005", "The Right to Information Act, 2005", "public_law", 3,
             "Right to Information Act", "RTI Act", "RTI"),
    _central("motor_vehicles_act_1988", "The Motor Vehicles Act, 1988", "motor_vehicle", 3,
             "Motor Vehicles Act", "MV Act", "MVA 1988",
             lifecycle_status="in_force", effective_from="1989-07-01",
             ingestion_enabled=True, verified_on="2026-08-27", expected_sections=257,
             act_id="AC_CEN_30_42_00009_198859_1517807326286",
             item_uuid="2bbbcc40-38f1-4b15-ae94-646b85db4ee7",
             bitstream_uuid="ce64835f-dccf-4672-b68a-b6967dc011ce"),
    _central("central_motor_vehicles_rules_1989", "The Central Motor Vehicles Rules, 1989", "motor_vehicle", 3,
             "Central Motor Vehicles Rules", "CMVR", "CMV Rules",
             instrument_kind="rules", parser_profile="rules_and_schedule",
             lifecycle_status="in_force_versioned_official_copy", effective_from="1989-07-01",
             ingestion_enabled=True, verified_on="2026-08-27", expected_sections=195,
             act_id="AC_CG_61_1084_00001_00001_1554966634246",
             item_uuid="7d392b30-af7c-4bd5-b1ba-06c298320bc4",
             bitstream_uuid="a62b208e-181c-403c-990a-a234bdaae3b0"),
    _karnataka("karnataka_motor_vehicles_rules_1989", "The Karnataka Motor Vehicles Rules, 1989", "motor_vehicle", 3,
               "Karnataka Motor Vehicles Rules", "KMVR", "KMV Rules",
               instrument_kind="rules", parser_profile="rules_and_schedule",
               lifecycle_status="in_force_archived_consolidation", effective_from="1989-07-01",
               ingestion_enabled=True, verified_on="2026-08-27", expected_sections=268,
               bitstream_uuid="webarchive-20170329033539-revised-m-v",
               source_url_override="https://web.archive.org/web/20170329033539id_/http://transport.karnataka.gov.in/uploads/notice/Revised_M_V.pdf",
               source_note=(
                   "Archived Karnataka government consolidation captured in 2017. "
                   "Verify later amendments and current fees or procedures before relying on it."
               )),
    _karnataka("karnataka_shops_act_1961", "The Karnataka Shops and Commercial Establishments Act, 1961", "employment", 3,
               "Karnataka Shops and Commercial Establishments Act", "Karnataka Shops Act"),

    # Tranche 4: family, personal safety and special criminal laws.
    _central("domestic_violence_act_2005", "The Protection of Women from Domestic Violence Act, 2005", "family", 4,
             "Protection of Women from Domestic Violence Act", "Domestic Violence Act", "PWDVA"),
    _central("pocso_act_2012", "The Protection of Children from Sexual Offences Act, 2012", "criminal", 4,
             "Protection of Children from Sexual Offences Act", "POCSO Act", "POCSO"),
    _central("posh_act_2013", "The Sexual Harassment of Women at Workplace (Prevention, Prohibition and Redressal) Act, 2013", "employment", 4,
             "Sexual Harassment of Women at Workplace Act", "POSH Act", "POSH"),
    _central("hindu_marriage_act_1955", "The Hindu Marriage Act, 1955", "family", 4,
             "Hindu Marriage Act", "HMA"),
    _central("hindu_succession_act_1956", "The Hindu Succession Act, 1956", "succession", 4,
             "Hindu Succession Act", "HSA"),
    _central("special_marriage_act_1954", "The Special Marriage Act, 1954", "family", 4,
             "Special Marriage Act", "SMA"),
    _central("guardians_and_wards_act_1890", "The Guardians and Wards Act, 1890", "family", 4,
             "Guardians and Wards Act", "GWA"),
    _central("juvenile_justice_act_2015", "The Juvenile Justice (Care and Protection of Children) Act, 2015", "child_law", 4,
             "Juvenile Justice Act", "JJ Act"),
    _central("sc_st_atrocities_act_1989", "The Scheduled Castes and the Scheduled Tribes (Prevention of Atrocities) Act, 1989", "criminal", 4,
             "SC ST Prevention of Atrocities Act", "SC/ST Act", "Atrocities Act"),
    _central("ndps_act_1985", "The Narcotic Drugs and Psychotropic Substances Act, 1985", "criminal", 4,
             "Narcotic Drugs and Psychotropic Substances Act", "NDPS Act", "NDPS"),
)


for _spec in STATUTE_CATALOG:
    _spec.validate()

if len(STATUTE_CATALOG) != 42:
    raise ValueError(f"Expected a 42-instrument catalogue, found {len(STATUTE_CATALOG)}")
if len({spec.key for spec in STATUTE_CATALOG}) != len(STATUTE_CATALOG):
    raise ValueError("Statute catalogue keys must be unique")
if len({spec.title.casefold() for spec in STATUTE_CATALOG}) != len(STATUTE_CATALOG):
    raise ValueError("Statute catalogue titles must be unique")


STATUTES_BY_KEY = {spec.key: spec for spec in STATUTE_CATALOG}
STATUTES_BY_TITLE = {spec.title.casefold(): spec for spec in STATUTE_CATALOG}
INGESTIBLE_STATUTES = tuple(spec for spec in STATUTE_CATALOG if spec.ingestion_enabled)


def get_statute_by_title(title: str) -> StatuteSpec | None:
    return STATUTES_BY_TITLE.get(title.casefold())


def supported_act_titles() -> tuple[str, ...]:
    return tuple(spec.title for spec in INGESTIBLE_STATUTES)
