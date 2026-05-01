from __future__ import annotations

from au_politics_money.models import SourceRecord


SOURCES: tuple[SourceRecord, ...] = (
    SourceRecord(
        source_id="aec_transparency_home",
        name="AEC Transparency Register",
        jurisdiction="Commonwealth",
        level="federal",
        source_type="financial_disclosure_portal",
        url="https://transparency.aec.gov.au/",
        expected_format="html",
        update_frequency="ongoing",
        priority="core",
        notes="Primary federal disclosure portal for annual, election, referendum, entity, and download pages.",
    ),
    SourceRecord(
        source_id="aec_transparency_downloads",
        name="AEC Download All Disclosure Data",
        jurisdiction="Commonwealth",
        level="federal",
        source_type="bulk_download_index",
        url="https://transparency.aec.gov.au/Download",
        expected_format="html",
        update_frequency="ongoing",
        priority="core",
        notes="Index for bulk annual, election, and referendum disclosure zip downloads.",
    ),
    SourceRecord(
        source_id="aec_annual_detailed_receipts",
        name="AEC Annual Detailed Receipts",
        jurisdiction="Commonwealth",
        level="federal",
        source_type="financial_disclosure_table",
        url="https://transparency.aec.gov.au/AnnualDetailedReceipts",
        expected_format="html_dynamic",
        update_frequency="annual_plus_amendments",
        priority="core",
        notes="Detailed receipts for parties, significant third parties, and associated entities from 1998-99 onwards.",
    ),
    SourceRecord(
        source_id="aec_download_all_annual_data",
        name="AEC All Annual Disclosure Data ZIP",
        jurisdiction="Commonwealth",
        level="federal",
        source_type="bulk_disclosure_zip",
        url="https://transparency.aec.gov.au/Download/AllAnnualData",
        expected_format="zip",
        update_frequency="ongoing",
        priority="core",
        notes="Bulk annual disclosure data export.",
    ),
    SourceRecord(
        source_id="aec_download_all_election_data",
        name="AEC All Election Disclosure Data ZIP",
        jurisdiction="Commonwealth",
        level="federal",
        source_type="bulk_disclosure_zip",
        url="https://transparency.aec.gov.au/Download/AllElectionsData",
        expected_format="zip",
        update_frequency="event_plus_amendments",
        priority="core",
        notes="Bulk election disclosure data export.",
    ),
    SourceRecord(
        source_id="aec_2025_federal_election_funding_finalised",
        name="AEC 2025 Federal Election Funding Payments Finalised",
        jurisdiction="Commonwealth",
        level="federal",
        source_type="election_public_funding_summary",
        url="https://www.aec.gov.au/media/2025/11-27.htm",
        expected_format="html",
        update_frequency="event_finalisation",
        priority="core",
        notes=(
            "Official AEC summary of final 2025 election public funding payments "
            "to parties and independent candidates."
        ),
    ),
    SourceRecord(
        source_id="aec_download_all_referendum_data",
        name="AEC All Referendum Disclosure Data ZIP",
        jurisdiction="Commonwealth",
        level="federal",
        source_type="bulk_disclosure_zip",
        url="https://transparency.aec.gov.au/Download/AllReferendumData",
        expected_format="zip",
        update_frequency="event_plus_amendments",
        priority="medium",
        notes="Bulk referendum disclosure data export.",
    ),
    SourceRecord(
        source_id="aec_member_senator_returns",
        name="AEC MP and Senator Annual Returns",
        jurisdiction="Commonwealth",
        level="federal",
        source_type="financial_disclosure_table",
        url="https://transparency.aec.gov.au/MemberOfParliament",
        expected_format="html_dynamic",
        update_frequency="annual_plus_amendments",
        priority="core",
        notes="Annual returns for Members of the House of Representatives and Senators.",
    ),
    SourceRecord(
        source_id="aec_disclosure_threshold",
        name="AEC Disclosure Threshold",
        jurisdiction="Commonwealth",
        level="federal",
        source_type="legal_threshold_reference",
        url="https://www.aec.gov.au/Parties_and_Representatives/public_funding/threshold.htm",
        expected_format="html",
        update_frequency="annual",
        priority="high",
        notes="Disclosure thresholds by financial year.",
    ),
    SourceRecord(
        source_id="aec_fad_reform",
        name="AEC Funding and Disclosure Reform",
        jurisdiction="Commonwealth",
        level="federal",
        source_type="legal_reform_reference",
        url="https://www.aec.gov.au/news/disclosure-legislative-changes.htm",
        expected_format="html",
        update_frequency="as_needed",
        priority="high",
        notes="Explains reforms commencing 2026-07-01.",
    ),
    SourceRecord(
        source_id="aph_members_interests_48",
        name="House Register of Members' Interests, 48th Parliament",
        jurisdiction="Commonwealth",
        level="federal",
        source_type="interests_register",
        url="https://www.aph.gov.au/senators_and_members/members/register",
        expected_format="html_plus_pdf",
        update_frequency="ongoing",
        priority="core",
        notes="Index of current House member interests PDFs.",
    ),
    SourceRecord(
        source_id="aph_senators_interests",
        name="Senate Register of Senators' Interests",
        jurisdiction="Commonwealth",
        level="federal",
        source_type="interests_register",
        url="https://www.aph.gov.au/Parliamentary_Business/Committees/Senate/Senators_Interests/Senators_Interests_Register",
        expected_format="html_plus_pdf",
        update_frequency="ongoing",
        priority="core",
        notes="Current Senate interests register.",
    ),
    SourceRecord(
        source_id="aph_contacts_csv",
        name="Parliament address labels and CSV files",
        jurisdiction="Commonwealth",
        level="federal",
        source_type="people_roster",
        url="https://www.aph.gov.au/Senators_and_Members/Contacting_Senators_and_Members/Address_labels_and_CSV_files",
        expected_format="html_plus_csv",
        update_frequency="ongoing",
        priority="core",
        notes="Current MP and Senator CSV files by name, state, party, and gender.",
    ),
    SourceRecord(
        source_id="aph_members_contact_list_pdf",
        name="APH House of Representatives contact list PDF",
        jurisdiction="Commonwealth",
        level="federal",
        source_type="people_contact_list",
        url="https://www.aph.gov.au/-/media/03_Senators_and_Members/32_Members/Lists/Members_List.pdf",
        expected_format="pdf",
        update_frequency="ongoing",
        priority="core",
        notes="Current House member office details and email addresses.",
    ),
    SourceRecord(
        source_id="aph_senators_contact_list_pdf",
        name="APH Senate contact list PDF",
        jurisdiction="Commonwealth",
        level="federal",
        source_type="people_contact_list",
        url="https://www.aph.gov.au/-/media/03_Senators_and_Members/31_Senators/Contacts/los.pdf",
        expected_format="pdf",
        update_frequency="ongoing",
        priority="core",
        notes="Current senator office details and email addresses.",
    ),
    SourceRecord(
        source_id="aec_federal_boundaries_gis",
        name="AEC Federal Electoral Boundary GIS Data",
        jurisdiction="Commonwealth",
        level="federal",
        source_type="geospatial_boundaries",
        url="https://www.aec.gov.au/Electorates/gis/gis_datadownload.htm",
        expected_format="html_plus_zip_shapefile",
        update_frequency="redistribution",
        priority="core",
        notes="Current and superseded federal electoral boundary downloads.",
    ),
    SourceRecord(
        source_id="aec_electorate_finder",
        name="AEC Electorate Finder",
        jurisdiction="Commonwealth",
        level="federal",
        source_type="postcode_locality_electorate_lookup",
        url="https://electorate.aec.gov.au/",
        expected_format="html",
        update_frequency="redistribution_or_aec_update",
        priority="high",
        notes=(
            "Official AEC electorate finder used for source-backed postcode and "
            "locality candidate lookups. Postcodes can map to multiple electorates; "
            "results are candidates, not address-level determinations, and may "
            "reflect next-election boundaries rather than current member boundaries."
        ),
    ),
    SourceRecord(
        source_id="natural_earth_admin0_countries_10m",
        name="Natural Earth 1:10m Admin 0 Countries",
        jurisdiction="Global",
        level="national",
        source_type="display_land_mask",
        url="https://naturalearth.s3.amazonaws.com/10m_cultural/ne_10m_admin_0_countries.zip",
        expected_format="zip_shapefile",
        update_frequency="rare",
        priority="medium",
        notes=(
            "Public-domain country land polygons used only for display clipping. "
            "Official electoral boundary geometries remain preserved separately."
        ),
    ),
    SourceRecord(
        source_id="natural_earth_physical_land_10m",
        name="Natural Earth 1:10m Physical Land",
        jurisdiction="Global",
        level="national",
        source_type="display_land_mask",
        url="https://naturalearth.s3.amazonaws.com/10m_physical/ne_10m_land.zip",
        expected_format="zip_shapefile",
        update_frequency="rare",
        priority="medium",
        notes=(
            "Public-domain physical land polygons used with Admin 0 countries to clip "
            "display-only electorate geometry to actual land."
        ),
    ),
    SourceRecord(
        source_id="aims_australian_coastline_50k_2024_simp",
        name="Australian Coastline 50K 2024 Simplified",
        jurisdiction="Australia",
        level="national",
        source_type="display_land_mask",
        url=(
            "https://nextcloud.eatlas.org.au/s/DcGmpS3F5KZjgAG/download"
            "?path=%2FV1-1%2F&files=Simp"
        ),
        expected_format="zip_shapefile",
        update_frequency="rare",
        priority="high",
        notes=(
            "Australian coastline and surrounding-island land-area polygons from "
            "AIMS/eAtlas/AODN, derived from 2022-2024 Sentinel-2 imagery. Used as "
            "the preferred display-only land mask for Australian electorate maps; "
            "official electoral boundary geometries remain preserved separately. "
            "Catalogue licence currently shows Not Specified, so raw/processed "
            "coastline files must not be publicly redistributed until reuse terms "
            "are confirmed; metadata carries source limitation caveats."
        ),
    ),
    SourceRecord(
        source_id="they_vote_for_you_api",
        name="They Vote For You API",
        jurisdiction="Commonwealth",
        level="federal",
        source_type="division_vote_api",
        url="https://theyvoteforyou.org.au/help/data",
        expected_format="json_api_docs",
        update_frequency="ongoing",
        priority="high",
        notes="Civic API for people, policies, divisions, and votes. Requires API key.",
    ),
    SourceRecord(
        source_id="aph_hansard",
        name="Parliament of Australia Hansard",
        jurisdiction="Commonwealth",
        level="federal",
        source_type="official_parliamentary_transcript",
        url="https://www.aph.gov.au/Hansard",
        expected_format="html_pdf_xml",
        update_frequency="sitting_days",
        priority="high",
        notes="Official transcript/report context for chamber proceedings; not the sole formal division record.",
    ),
    SourceRecord(
        source_id="aph_house_votes_and_proceedings",
        name="House Votes and Proceedings",
        jurisdiction="Commonwealth",
        level="federal",
        source_type="official_house_decision_record",
        url="https://www.aph.gov.au/Parliamentary_Business/Chamber_documents/HoR/Votes_and_Proceedings",
        expected_format="html_plus_parlinfo_html_pdf",
        update_frequency="sitting_days",
        priority="high",
        notes="Formal House record for proceedings, decisions, attendance, and divisions.",
    ),
    SourceRecord(
        source_id="aph_senate_journals",
        name="Journals of the Senate",
        jurisdiction="Commonwealth",
        level="federal",
        source_type="official_senate_decision_record",
        url=(
            "https://www.aph.gov.au/About_Parliament/Senate/"
            "Powers_practice_n_procedures/~/~/link.aspx"
            "?_id=732F8182C02D4B3699E417F33843A933"
        ),
        expected_format="html_pdf",
        update_frequency="sitting_days",
        priority="high",
        notes="Formal Senate record for proceedings and decisions, including senators voting in divisions.",
    ),
    SourceRecord(
        source_id="open_australia_api",
        name="OpenAustralia API",
        jurisdiction="Commonwealth",
        level="federal",
        source_type="hansard_member_api",
        url="https://www.openaustralia.org.au/api/",
        expected_format="api_docs",
        update_frequency="ongoing",
        priority="medium",
        notes="Legacy civic API for Hansard and member data.",
    ),
    SourceRecord(
        source_id="australian_lobbyists_register",
        name="Australian Government Register of Lobbyists",
        jurisdiction="Commonwealth",
        level="federal",
        source_type="lobbyist_register",
        url="https://www.ag.gov.au/integrity/australian-government-register-lobbyists",
        expected_format="html",
        update_frequency="ongoing",
        priority="high",
        notes="Federal third-party lobbyists and clients.",
    ),
    SourceRecord(
        source_id="centre_public_integrity_lobbyists",
        name="Centre for Public Integrity Lobbyist Register",
        jurisdiction="Commonwealth",
        level="federal",
        source_type="civic_lobbyist_register",
        url="https://publicintegrity.org.au/lobbyist-register/about-2/",
        expected_format="html",
        update_frequency="ongoing",
        priority="medium",
        notes="Civic presentation of Australian Government Register of Lobbyists data.",
    ),
    SourceRecord(
        source_id="asic_companies_dataset",
        name="ASIC Company Dataset",
        jurisdiction="Commonwealth",
        level="national",
        source_type="company_register_extract",
        url="https://www.data.gov.au/data/dataset/asic-companies",
        expected_format="html_plus_csv",
        update_frequency="weekly",
        priority="high",
        notes="Company register extract for entity resolution.",
    ),
    SourceRecord(
        source_id="acnc_register",
        name="ACNC Registered Charities",
        jurisdiction="Commonwealth",
        level="national",
        source_type="charity_register_extract",
        url="https://data.gov.au/data/dataset/acnc-register",
        expected_format="html_plus_csv",
        update_frequency="weekly",
        priority="high",
        notes="Registered charities extract for ABN-backed charity identification.",
    ),
    SourceRecord(
        source_id="abn_lookup",
        name="ABN Lookup",
        jurisdiction="Commonwealth",
        level="national",
        source_type="business_register_lookup",
        url="https://abr.business.gov.au/home",
        expected_format="html",
        update_frequency="ongoing",
        priority="medium",
        notes="Public ABR lookup. Public data does not expose all ANZSIC details.",
    ),
    SourceRecord(
        source_id="abs_anzsic",
        name="ABS ANZSIC Classification",
        jurisdiction="Commonwealth",
        level="national",
        source_type="industry_classification",
        url="https://www.abs.gov.au/statistics/classifications/australian-and-new-zealand-standard-industrial-classification-anzsic",
        expected_format="html_plus_downloads",
        update_frequency="rare",
        priority="high",
        notes="Official Australian and New Zealand industry classification.",
    ),
    SourceRecord(
        source_id="abs_indicator_api",
        name="ABS Indicator API",
        jurisdiction="Commonwealth",
        level="national",
        source_type="economic_indicator_api",
        url="https://api.data.abs.gov.au/indicators",
        expected_format="json",
        update_frequency="release_calendar_1130_aest",
        priority="medium",
        notes=(
            "Official public ABS Indicator API for headline market-moving statistics. "
            "Production-suitable; requires `ABS_API_KEY`; rate-limited to 10 calls/sec "
            "per key. Headline indicators are published at 11:30am AEST on release day. "
            "Reuse/licence terms must be re-confirmed against current ABS terms before "
            "public data redistribution."
        ),
    ),
    SourceRecord(
        source_id="abs_data_api",
        name="ABS Data API (SDMX, beta)",
        jurisdiction="Commonwealth",
        level="national",
        source_type="statistical_data_api",
        url="https://data.api.abs.gov.au/rest/",
        expected_format="sdmx_xml_json_csv",
        update_frequency="dataflow_dependent",
        priority="medium",
        notes=(
            "Official ABS Data API serving detailed SDMX statistics. Beta service; "
            "availability not guaranteed; subject to change. Keyless since 29 Nov 2024 "
            "(register-of-interest model). Distinct from the ABS Indicator API: do not "
            "send `ABS_API_KEY` here. Reuse/licence terms must be re-confirmed against "
            "current ABS terms before public data redistribution."
        ),
    ),
    SourceRecord(
        source_id="aec_register_of_entities_politicalparty",
        name="AEC Register of Entities — Political Parties",
        jurisdiction="Commonwealth",
        level="federal",
        source_type="aec_register_of_entities_api",
        url="https://transparency.aec.gov.au/RegisterOfEntities?clientType=politicalparty",
        expected_format="html_with_xhr_json",
        update_frequency="ongoing",
        priority="high",
        notes=(
            "Official public AEC Register of Entities snapshot for registered political "
            "parties. Fetched via GET on the page, anti-forgery token extraction, then "
            "session-scoped POST to /RegisterOfEntities/ClientDetailsRead. Anti-forgery "
            "cookie + token are session-disposable and MUST be redacted from raw archive "
            "metadata before persistence. Public redistribution/licence terms to be recorded before "
            "public data redistribution."
        ),
    ),
    SourceRecord(
        source_id="aec_register_of_entities_associatedentity",
        name="AEC Register of Entities — Associated Entities",
        jurisdiction="Commonwealth",
        level="federal",
        source_type="aec_register_of_entities_api",
        url="https://transparency.aec.gov.au/RegisterOfEntities?clientType=associatedentity",
        expected_format="html_with_xhr_json",
        update_frequency="ongoing",
        priority="high",
        notes=(
            "Official public AEC Register of Entities snapshot for associated entities, "
            "the primary input for source-backed party_entity_link evidence. Each row "
            "may carry an explicit AssociatedParties list; loaders auto-create reviewed "
            "links only when a segment resolves to exactly one party.id under the "
            "documented C-rule. Anti-forgery cookie + token redacted from raw archive."
        ),
    ),
    SourceRecord(
        source_id="aec_register_of_entities_significantthirdparty",
        name="AEC Register of Entities — Significant Third Parties",
        jurisdiction="Commonwealth",
        level="federal",
        source_type="aec_register_of_entities_api",
        url="https://transparency.aec.gov.au/RegisterOfEntities?clientType=significantthirdparty",
        expected_format="html_with_xhr_json",
        update_frequency="ongoing",
        priority="medium",
        notes=(
            "Official public AEC Register of Entities snapshot for significant third "
            "parties. Loaders ingest as entities + identifiers only; no auto party_entity_link "
            "creation per the C-rule, even where AssociatedParties is populated. "
            "Anti-forgery cookie + token redacted from raw archive."
        ),
    ),
    SourceRecord(
        source_id="aec_register_of_entities_thirdparty",
        name="AEC Register of Entities — Third Parties",
        jurisdiction="Commonwealth",
        level="federal",
        source_type="aec_register_of_entities_api",
        url="https://transparency.aec.gov.au/RegisterOfEntities?clientType=thirdparty",
        expected_format="html_with_xhr_json",
        update_frequency="ongoing",
        priority="medium",
        notes=(
            "Official public AEC Register of Entities snapshot for third parties. The "
            "AEC clientType value is 'thirdparty', not 'thirdpartycampaigner' (the latter "
            "returns HTTP 500). Loaders ingest as entities + identifiers only; no auto "
            "party_entity_link. Anti-forgery cookie + token redacted from raw archive."
        ),
    ),
    SourceRecord(
        source_id="nsw_electoral_disclosures",
        name="NSW Electoral Commission Disclosures",
        jurisdiction="New South Wales",
        level="state_council",
        source_type="state_local_financial_disclosure_portal",
        url="https://elections.nsw.gov.au/electoral-funding/disclosures/view-disclosures",
        expected_format="html_plus_search",
        update_frequency="half_yearly_annual_pre_election_plus_amendments",
        priority="high",
        notes=(
            "Official NSW publication surface for disclosed political donations and "
            "electoral expenditure by parties, elected members, candidates, groups, "
            "political donors, third-party campaigners, and associated entities. "
            "Includes state and local-government disclosure coverage; preserve any "
            "redaction caveats from source forms."
        ),
    ),
    SourceRecord(
        source_id="nsw_2023_state_election_pre_election_donations",
        name="NSW 2023 State Election Pre-Election Period Donation Disclosures",
        jurisdiction="New South Wales",
        level="state",
        source_type="state_financial_disclosure_reference",
        url=(
            "https://elections.nsw.gov.au/electoral-funding/disclosures/"
            "pre-election-period-donation-disclosure/"
            "2023-nsw-state-election-donations"
        ),
        expected_format="html",
        update_frequency="event_plus_amendments",
        priority="high",
        notes=(
            "Official NSW Electoral Commission explanatory page for 2023 State "
            "Election pre-election-period reportable donations. Defines the "
            "1 October 2022 to 25 March 2023 reporting window and links to the "
            "official aggregate heatmap."
        ),
    ),
    SourceRecord(
        source_id="nsw_2023_state_election_donation_heatmap",
        name="NSW 2023 State Election Donation Heatmap",
        jurisdiction="New South Wales",
        level="state",
        source_type="state_financial_disclosure_aggregate_context",
        url=(
            "https://elections.nsw.gov.au/getmedia/"
            "2ea29d95-d8a4-45ee-b45b-f9f9150a8446/FDC-heat-map.html"
        ),
        expected_format="html_flexdashboard",
        update_frequency="event_plus_amendments",
        priority="high",
        notes=(
            "Official static NSW Electoral Commission heatmap for 2023 State "
            "Election pre-election-period reportable donations by donor-location "
            "district. Aggregate context only: rows do not identify donation "
            "recipients, donors, candidates, parties, MPs, or councillors. "
            "Preserve NSWEC map exclusion caveats and Creative Commons "
            "Attribution 4.0 licence requirements."
        ),
    ),
    SourceRecord(
        source_id="vic_vec_disclosures",
        name="Victorian Electoral Commission Disclosures",
        jurisdiction="Victoria",
        level="state",
        source_type="state_financial_disclosure_portal",
        url="https://www.vec.vic.gov.au/disclosures/",
        expected_format="html_plus_search",
        update_frequency="near_real_time_plus_annual_returns",
        priority="high",
        notes=(
            "Official Victorian political donation disclosure surface for state "
            "parties, candidates, elected members, associated entities, nominated "
            "entities, and third-party campaigners. Local council donations require "
            "a separate local-government adapter."
        ),
    ),
    SourceRecord(
        source_id="qld_ecq_disclosures",
        name="Electoral Commission of Queensland Disclosure System",
        jurisdiction="Queensland",
        level="state_council",
        source_type="state_local_financial_disclosure_portal",
        url=(
            "https://www.ecq.qld.gov.au/donations-and-expenditure-disclosure/"
            "disclosure-of-political-donations-and-electoral-expenditure"
        ),
        expected_format="html_plus_electronic_disclosure_system",
        update_frequency="real_time_periodic_election",
        priority="high",
        notes=(
            "Official ECQ disclosure entry point for political donations, gifts, loans, "
            "and electoral expenditure. Covers state and local-government disclosure "
            "obligations through the Electronic Disclosure System."
        ),
    ),
    SourceRecord(
        source_id="qld_state_electoral_boundaries_arcgis",
        name="Queensland current state electorate boundaries ArcGIS GeoJSON",
        jurisdiction="Queensland",
        level="state",
        source_type="state_electoral_boundary_geojson",
        url=(
            "https://spatial-gis.information.qld.gov.au/arcgis/rest/services/"
            "Boundaries/AdministrativeBoundaries/MapServer/5/query"
            "?where=1%3D1&outFields=*&returnGeometry=true&f=geojson&outSR=4326"
        ),
        expected_format="arcgis_rest_geojson",
        update_frequency="redistribution",
        priority="high",
        notes=(
            "Official Queensland government spatial service layer for current "
            "state electoral district polygons. ECQ states that state electorate "
            "GIS data are available through QSpatial. These boundaries support "
            "state map drilldown only; they do not by themselves link disclosure "
            "rows to current state MPs."
        ),
    ),
    SourceRecord(
        source_id="qld_local_government_boundaries_arcgis",
        name="Queensland current local government boundaries ArcGIS GeoJSON",
        jurisdiction="Queensland",
        level="council",
        source_type="local_government_boundary_geojson",
        url=(
            "https://spatial-gis.information.qld.gov.au/arcgis/rest/services/"
            "Boundaries/AdministrativeBoundaries/MapServer/1/query"
            "?where=1%3D1&outFields=*&returnGeometry=true&f=geojson&outSR=4326"
        ),
        expected_format="arcgis_rest_geojson",
        update_frequency="administrative_boundary_update",
        priority="high",
        notes=(
            "Official Queensland government spatial service layer for current "
            "local-government area polygons. These boundaries support council "
            "map drilldown only; they do not by themselves link ECQ disclosure "
            "rows to councillors, candidates, councils, state MPs, or federal MPs."
        ),
    ),
    SourceRecord(
        source_id="qld_parliament_members_mail_merge_xlsx",
        name="Queensland Parliament Members Mail Merge List Excel",
        jurisdiction="Queensland",
        level="state",
        source_type="state_current_member_contact_xlsx",
        url="https://documents.parliament.qld.gov.au/Members/mailingLists/MEMMERGEEXCEL.xlsx",
        expected_format="xlsx",
        update_frequency="parliamentary_roster",
        priority="high",
        notes=(
            "Official Queensland Parliament current-member mail-merge XLSX. "
            "Contains electorate names, member names, party abbreviations, "
            "portfolio text, electorate office addresses, and public electorate "
            "office email addresses. Used to join current state representation "
            "to source-backed state electorates; it does not attribute ECQ "
            "disclosure rows to those MPs."
        ),
    ),
    SourceRecord(
        source_id="qld_ecq_eds_public_map",
        name="ECQ Electronic Disclosure System Gift Map",
        jurisdiction="Queensland",
        level="state_council",
        source_type="state_local_financial_disclosure_public_map",
        url="https://disclosures.ecq.qld.gov.au/Map",
        expected_format="html_plus_js",
        update_frequency="real_time_periodic_election",
        priority="high",
        notes=(
            "Public ECQ Electronic Disclosure System map surface for Queensland "
            "state and local gift disclosure records. Use as a discovery surface "
            "for stable public-data requests, not as a geocoding authority."
        ),
    ),
    SourceRecord(
        source_id="qld_ecq_eds_expenditures",
        name="ECQ Electronic Disclosure System Expenditure Table",
        jurisdiction="Queensland",
        level="state_council",
        source_type="state_local_financial_disclosure_expenditure_table",
        url="https://disclosures.ecq.qld.gov.au/Expenditures",
        expected_format="html_plus_js",
        update_frequency="real_time_periodic_election",
        priority="high",
        notes=(
            "Public ECQ Electronic Disclosure System expenditure table for "
            "Queensland state and local electoral expenditure disclosure records."
        ),
    ),
    SourceRecord(
        source_id="qld_ecq_eds_map_export_csv",
        name="ECQ EDS Gift Map CSV Export",
        jurisdiction="Queensland",
        level="state_council",
        source_type="state_local_financial_disclosure_export_csv",
        url="https://disclosures.ecq.qld.gov.au/Map/ExportCsv",
        expected_format="csv_post_form",
        update_frequency="real_time_periodic_election",
        priority="high",
        notes=(
            "CSV export endpoint for ECQ EDS gift-map records. Requires form fields "
            "from the current `/Map` page and must be fetched with a POST request."
        ),
    ),
    SourceRecord(
        source_id="qld_ecq_eds_expenditure_export_csv",
        name="ECQ EDS Expenditure CSV Export",
        jurisdiction="Queensland",
        level="state_council",
        source_type="state_local_financial_disclosure_export_csv",
        url="https://disclosures.ecq.qld.gov.au/Expenditures/ExportCsv",
        expected_format="csv_post_form",
        update_frequency="real_time_periodic_election",
        priority="high",
        notes=(
            "CSV export endpoint for ECQ EDS electoral expenditure records. Requires "
            "form fields from the current `/Expenditures` page and must be fetched "
            "with a POST request."
        ),
    ),
    SourceRecord(
        source_id="qld_ecq_eds_reports",
        name="ECQ Electronic Disclosure System Reports",
        jurisdiction="Queensland",
        level="state_council",
        source_type="state_local_financial_disclosure_reports",
        url="https://disclosures.ecq.qld.gov.au/Report",
        expected_format="html_plus_js",
        update_frequency="real_time_periodic_election",
        priority="high",
        notes=(
            "Public ECQ Electronic Disclosure System reports surface for "
            "Queensland state and local political donation and expenditure data."
        ),
    ),
    SourceRecord(
        source_id="qld_ecq_eds_api_political_electors",
        name="ECQ EDS Political Electors API",
        jurisdiction="Queensland",
        level="state_council",
        source_type="state_local_financial_disclosure_lookup_api",
        url="https://disclosures.ecq.qld.gov.au/api/political/electors",
        expected_format="json",
        update_frequency="real_time_periodic_election",
        priority="high",
        notes=(
            "Public lookup endpoint referenced by ECQ EDS JavaScript for candidate "
            "and elector filters. Supports Queensland state and local disclosure "
            "normalization; not itself a money-flow table."
        ),
    ),
    SourceRecord(
        source_id="qld_ecq_eds_api_political_parties",
        name="ECQ EDS Political Parties API",
        jurisdiction="Queensland",
        level="state_council",
        source_type="state_local_financial_disclosure_lookup_api",
        url="https://disclosures.ecq.qld.gov.au/api/political/political-parties",
        expected_format="json",
        update_frequency="real_time_periodic_election",
        priority="high",
        notes=(
            "Public lookup endpoint referenced by ECQ EDS JavaScript for political "
            "party filters."
        ),
    ),
    SourceRecord(
        source_id="qld_ecq_eds_api_associated_entities",
        name="ECQ EDS Associated Entities API",
        jurisdiction="Queensland",
        level="state_council",
        source_type="state_local_financial_disclosure_lookup_api",
        url=(
            "https://disclosures.ecq.qld.gov.au/api/political/organisations"
            "?DisclosureRole=AssociatedEntity"
        ),
        expected_format="json",
        update_frequency="real_time_periodic_election",
        priority="high",
        notes="Public lookup endpoint referenced by ECQ EDS reports for associated entities.",
    ),
    SourceRecord(
        source_id="qld_ecq_eds_api_political_events",
        name="ECQ EDS Political Events API",
        jurisdiction="Queensland",
        level="state_council",
        source_type="state_local_financial_disclosure_lookup_api",
        url="https://disclosures.ecq.qld.gov.au/api/political/events",
        expected_format="json",
        update_frequency="real_time_periodic_election",
        priority="high",
        notes=(
            "Public lookup endpoint referenced by ECQ EDS JavaScript for election "
            "event filters."
        ),
    ),
    SourceRecord(
        source_id="qld_ecq_eds_api_local_groups",
        name="ECQ EDS Local Groups API",
        jurisdiction="Queensland",
        level="council",
        source_type="state_local_financial_disclosure_lookup_api",
        url="https://disclosures.ecq.qld.gov.au/api/political/local-groups",
        expected_format="json",
        update_frequency="real_time_periodic_election",
        priority="high",
        notes="Public lookup endpoint referenced by ECQ EDS JavaScript for local-government groups.",
    ),
    SourceRecord(
        source_id="qld_ecq_eds_api_local_electorates",
        name="ECQ EDS Local Electorates API",
        jurisdiction="Queensland",
        level="council",
        source_type="state_local_financial_disclosure_lookup_api",
        url="https://disclosures.ecq.qld.gov.au/api/political/local-electorates",
        expected_format="json",
        update_frequency="real_time_periodic_election",
        priority="high",
        notes=(
            "Public lookup endpoint referenced by ECQ EDS expenditure/map pages "
            "for local-government electorate filters."
        ),
    ),
    SourceRecord(
        source_id="qld_ecq_disclosure_return_archives",
        name="ECQ Disclosure Return Archives",
        jurisdiction="Queensland",
        level="state_council",
        source_type="state_local_financial_disclosure_archive",
        url="https://www.ecq.qld.gov.au/disclosurereturnarchives",
        expected_format="html_plus_downloads",
        update_frequency="historical_archive",
        priority="high",
        notes=(
            "Official ECQ historical disclosure archive linked from the Electronic "
            "Disclosure System. Use for historical state and local records that "
            "may not be exposed through current EDS views."
        ),
    ),
    SourceRecord(
        source_id="sa_ecsa_funding_disclosure",
        name="Electoral Commission SA Funding and Disclosure",
        jurisdiction="South Australia",
        level="state",
        source_type="state_financial_disclosure_reference",
        url="https://www.ecsa.sa.gov.au/parties-and-candidates/disclosure-returns",
        expected_format="html_plus_portal_links",
        update_frequency="ongoing",
        priority="high",
        notes=(
            "Official ECSA disclosure-return landing page for political parties, "
            "candidates, associated entities, third parties, donors, and campaign "
            "expenditure returns. Current machine-readable index parsing uses the "
            "sa_ecsa_funding2024_return_records source."
        ),
    ),
    SourceRecord(
        source_id="sa_ecsa_funding2024_return_records",
        name="ECSA Political Participant Return Records 2023 onwards",
        jurisdiction="South Australia",
        level="state",
        source_type="state_financial_disclosure_return_index",
        url="https://www.ecsa.sa.gov.au/html/funding2024/index.php",
        expected_format="paginated_html_return_index",
        update_frequency="ongoing",
        priority="high",
        notes=(
            "Official ECSA current funding portal index. Rows are return-level "
            "summary records with lodged dates, submitters/agents, return subjects, "
            "reporting periods, values, and official report-view links. They are "
            "not individual donor-to-recipient transactions and require detailed "
            "return/PDF parsing plus cross-source deduplication before inclusion in "
            "consolidated reported money totals."
        ),
    ),
    SourceRecord(
        source_id="waec_returns_reports",
        name="Western Australian Electoral Commission Returns and Reports",
        jurisdiction="Western Australia",
        level="state_council",
        source_type="state_local_financial_disclosure_portal",
        url="https://www.elections.wa.gov.au/returns-and-reports",
        expected_format="html_plus_search_pdf",
        update_frequency="annual_election_plus_amendments",
        priority="medium",
        notes=(
            "Official WAEC annual and election return surface for gifts, income, "
            "expenditure, and reimbursements. Local-government disclosure duties are "
            "not fully centralized and may require council-level handling."
        ),
    ),
    SourceRecord(
        source_id="waec_ods_public_dashboard",
        name="WAEC Online Disclosure System Public Dashboard",
        jurisdiction="Western Australia",
        level="state",
        source_type="state_financial_disclosure_portal",
        url="https://disclosures.elections.wa.gov.au/public-dashboard/",
        expected_format="html_plus_power_pages_entity_grid_json",
        update_frequency="ongoing",
        priority="high",
        notes=(
            "Official WAEC Online Disclosure System dashboard. The first adapter "
            "archives this page and its public entity-grid configuration before "
            "fetching published political contribution rows."
        ),
    ),
    SourceRecord(
        source_id="waec_ods_political_contributions",
        name="WAEC ODS Published Political Contributions",
        jurisdiction="Western Australia",
        level="state",
        source_type="state_financial_disclosure_json_grid",
        url="https://disclosures.elections.wa.gov.au/public-dashboard/",
        expected_format="power_pages_entity_grid_json",
        update_frequency="ongoing",
        priority="high",
        notes=(
            "Official WAEC public dashboard grid for published political "
            "contributions. Rows include donor, political entity, contribution "
            "type, amount, financial year, public donor postcode, status, version, "
            "and disclosure-received date. Contribution rows are source-backed "
            "money records, but not personal receipt by a representative; amendment "
            "or other versioned rows are preserved separately pending deduplication."
        ),
    ),
    SourceRecord(
        source_id="tas_tec_disclosure_funding",
        name="Tasmanian Electoral Commission Disclosure and Funding",
        jurisdiction="Tasmania",
        level="state",
        source_type="state_financial_disclosure_portal",
        url="https://www.tec.tas.gov.au/disclosure-and-funding/",
        expected_format="html_plus_registers_returns",
        update_frequency="new_regime_ongoing",
        priority="medium",
        notes=(
            "Official TEC source for the disclosure and funding scheme commencing "
            "2025-07-01. Preserve regime-start dates so pre-regime gaps are not "
            "misread as zero influence."
        ),
    ),
    SourceRecord(
        source_id="tas_tec_donations_monthly_table",
        name="TEC Monthly Reportable Political Donations Table",
        jurisdiction="Tasmania",
        level="state",
        source_type="state_financial_disclosure_donation_table",
        url=(
            "https://www.tec.tas.gov.au/disclosure-and-funding/registers-and-reports/"
            "donations/data/table-monthly-disclosures-m.html"
        ),
        expected_format="html_table_fragment",
        update_frequency="regular",
        priority="high",
        notes=(
            "Official TEC table fragment for monthly reportable political donation "
            "disclosures outside an election period under the disclosure scheme "
            "commencing 2025-07-01. Rows include donation date, amount, donor, "
            "recipient, donor ABN/ACN where published, and declaration-document "
            "status/links."
        ),
    ),
    SourceRecord(
        source_id="tas_tec_donations_seven_day_ha25_table",
        name="TEC Seven-Day Reportable Political Donations 2025 State Election",
        jurisdiction="Tasmania",
        level="state",
        source_type="state_financial_disclosure_donation_table",
        url=(
            "https://www.tec.tas.gov.au/disclosure-and-funding/registers-and-reports/"
            "donations/data/table-seven-day-disclosures-ha25-m.html"
        ),
        expected_format="html_table_fragment",
        update_frequency="event_plus_amendments",
        priority="high",
        notes=(
            "Official TEC table fragment for seven-day reportable political donation "
            "disclosures during the 2025 House of Assembly election campaign period. "
            "Rows are donation or reportable-loan observations, not personal receipt "
            "unless the source recipient itself is an independent candidate/member."
        ),
    ),
    SourceRecord(
        source_id="tas_tec_donations_seven_day_lc26_table",
        name="TEC Seven-Day Reportable Political Donations 2026 Legislative Council",
        jurisdiction="Tasmania",
        level="state",
        source_type="state_financial_disclosure_donation_table",
        url=(
            "https://www.tec.tas.gov.au/disclosure-and-funding/registers-and-reports/"
            "donations/data/table-seven-day-disclosures-lc26-m.html"
        ),
        expected_format="html_table_fragment",
        update_frequency="event_plus_amendments",
        priority="high",
        notes=(
            "Official TEC table fragment for seven-day reportable political donation "
            "disclosures during the 2026 Legislative Council campaign period for "
            "Huon and Rosevears."
        ),
    ),
    SourceRecord(
        source_id="nt_ntec_annual_returns",
        name="Northern Territory Electoral Commission Annual Returns",
        jurisdiction="Northern Territory",
        level="state",
        source_type="state_financial_disclosure_publication",
        url=(
            "https://ntec.nt.gov.au/about-us/media-and-publications/"
            "media-releases/2025/20242025-annual-returns"
        ),
        expected_format="html_plus_return_downloads",
        update_frequency="annual_election",
        priority="medium",
        notes=(
            "Official NTEC publication point for annual gift returns, annual returns, "
            "candidate returns, donor returns, and related election expenditure "
            "disclosure context."
        ),
    ),
    SourceRecord(
        source_id="nt_ntec_annual_returns_2024_2025",
        name="NTEC Annual Returns 2024-2025",
        jurisdiction="Northern Territory",
        level="state",
        source_type="state_financial_disclosure_annual_return_table",
        url=(
            "https://ntec.nt.gov.au/financial-disclosure/published-annual-returns/"
            "2024-2025-annual-returns"
        ),
        expected_format="html_tables",
        update_frequency="annual",
        priority="high",
        notes=(
            "Official NTEC annual return page with party and associated-entity "
            "return summaries, recipient-side receipts and debts over $1,500, "
            "and donor-side donation return tables. Rows can overlap with NTEC "
            "annual gift-return and Commonwealth disclosure records."
        ),
    ),
    SourceRecord(
        source_id="nt_ntec_annual_returns_gifts_2024_2025",
        name="NTEC Annual Returns Gifts 2024-2025",
        jurisdiction="Northern Territory",
        level="state",
        source_type="state_financial_disclosure_gift_return_table",
        url=(
            "https://ntec.nt.gov.au/financial-disclosure/published-annual-returns/"
            "2024-2025-annual-returns-gifts"
        ),
        expected_format="html_tables",
        update_frequency="annual",
        priority="high",
        notes=(
            "Official NTEC annual gift-return page with recipient-side tables of "
            "gifts received over the threshold in the 2024-2025 annual disclosure "
            "period. Per-row gift dates are not published in these tables; the "
            "return received date is context only."
        ),
    ),
    SourceRecord(
        source_id="act_elections_funding_disclosure",
        name="Elections ACT Funding and Disclosure Obligations",
        jurisdiction="Australian Capital Territory",
        level="state",
        source_type="state_financial_disclosure_portal",
        url=(
            "https://www.elections.act.gov.au/"
            "funding-disclosures-and-registers/funding-and-disclosure-obligations"
        ),
        expected_format="html_plus_xlsx_pdf",
        update_frequency="regular_gifts_annual_election",
        priority="medium",
        notes=(
            "Official ACT source for gift returns, annual financial disclosure returns, "
            "election returns, expenditure caps, public funding, receipts, gifts, "
            "payments, and debts. Party-endorsed candidate expenditure can sit in "
            "party grouping returns and must be labelled as campaign context."
        ),
    ),
    SourceRecord(
        source_id="act_gift_returns_2025_2026",
        name="Elections ACT Gift Returns 2025-2026",
        jurisdiction="Australian Capital Territory",
        level="state",
        source_type="state_financial_disclosure_gift_return_table",
        url=(
            "https://www.elections.act.gov.au/funding-disclosures-and-registers/"
            "gift-returns/gift-returns-2025-2026"
        ),
        expected_format="html_tables",
        update_frequency="regular_gifts",
        priority="high",
        notes=(
            "Official Elections ACT current gift-return table for gifts received "
            "when a party grouping or non-party candidate grouping receives a gift, "
            "or cumulative gifts from one donor, totalling $1,000 or more. Rows "
            "include money gifts and gift-in-kind values such as event tickets or "
            "services, and individual row amounts may be below $1,000 when the "
            "threshold is cumulative. Individual home addresses are not fully "
            "published online; only the public address surface should be stored."
        ),
    ),
    SourceRecord(
        source_id="act_annual_returns_2024_2025",
        name="Elections ACT Annual Returns 2024-2025",
        jurisdiction="Australian Capital Territory",
        level="state",
        source_type="state_financial_disclosure_annual_return_tables",
        url=(
            "https://www.elections.act.gov.au/funding-disclosures-and-registers/"
            "annual-returns/20242025-annual-returns"
        ),
        expected_format="html_tables",
        update_frequency="annual",
        priority="high",
        notes=(
            "Official Elections ACT annual-return table page. Current adapter "
            "normalizes receipt detail rows totalling $1,000 or more for political "
            "parties, MLAs, non-party MLAs, and associated entities. Rows can "
            "include gifts of money, gifts-in-kind, free facilities use, and "
            "other receipts; they should be displayed as source-backed disclosure "
            "observations, not claims of wrongdoing or personal income."
        ),
    ),
    SourceRecord(
        source_id="vic_vec_funding_register",
        name="VEC Funding Register",
        jurisdiction="Victoria",
        level="state",
        source_type="state_public_funding_register",
        url="https://www.vec.vic.gov.au/candidates-and-parties/funding/funding-register",
        expected_format="html_plus_docx",
        update_frequency="quarterly_or_as_updated",
        priority="high",
        notes=(
            "Official VEC register of public money paid to eligible political parties, "
            "independent members, and candidates. The source is public funding/admin/"
            "policy funding context, not private donations or personal receipt. The "
            "VEC says affected funding/disclosure pages are under review after Hopper "
            "& Anor v State of Victoria [2026] HCA 11 and may not be accurate."
        ),
    ),
    SourceRecord(
        source_id="nacc_corrupt_conduct",
        name="NACC What is Corrupt Conduct",
        jurisdiction="Commonwealth",
        level="national",
        source_type="integrity_reference",
        url="https://www.nacc.gov.au/reporting-and-investigating-corruption/what-corrupt-conduct",
        expected_format="html",
        update_frequency="as_needed",
        priority="medium",
        notes="Reference for careful integrity language and corruption definitions.",
    ),
    # ---- Federal-spending transparency sources (Batch X registration) ----
    # These are publicly-published Commonwealth government-spending and
    # influence-disclosure registers that significantly expand the
    # project's federal coverage beyond the AEC/APH disclosure scope.
    # Each is registered here with verified URL + licence; the loader
    # adapter for each lands in a follow-up batch as it's ready.
    SourceRecord(
        source_id="austender_contract_notices_current",
        name="AusTender Contract Notices (current)",
        jurisdiction="Commonwealth",
        level="national",
        source_type="government_contract_register",
        url="https://www.tenders.gov.au/cn/search",
        expected_format="csv_or_xml_via_search_export",
        update_frequency="continuous",
        priority="high",
        notes=(
            "Every Commonwealth contract notice ≥ $10k published by "
            "agencies on AusTender. Current data lives at tenders.gov.au; "
            "the live search/export endpoints CloudFront-block plain "
            "HTTP user-agents, so a polite UA (with project URL) is "
            "required. Each contract row carries: agency, contract ID, "
            "publish/start/end/amendment dates, value, description, "
            "UNSPSC code + title (industry classification), "
            "procurement method, supplier name + ABN + address. "
            "Supplier ABN is the natural join key into the project's "
            "existing entity table; UNSPSC enables industry-classified "
            "spending analysis. IMPORTANT: contract spending is NOT a "
            "personal receipt by an MP and must be surfaced as "
            "government-spending evidence family, not money or campaign "
            "support."
        ),
    ),
    SourceRecord(
        source_id="austender_contract_notices_historical",
        name="AusTender Contract Notices (historical CSV bulk)",
        jurisdiction="Commonwealth",
        level="national",
        source_type="government_contract_register",
        url="https://data.gov.au/data/dataset/historical-australian-government-contract-notice-data",
        expected_format="csv",
        update_frequency="annual_bulk",
        priority="high",
        notes=(
            "Historical (1998 onward) AusTender contract data published "
            "as yearly CSVs on data.gov.au under CC-BY 3.0 Australia. "
            "Most-recent yearly file at time of registration is "
            "'2017-18 Australian Government Contract Data' (75,478 rows, "
            "31 MB). Preferred path for bulk historical ingestion "
            "because the data.gov.au mirror has clean static CSV URLs, "
            "verified CC-BY licence, and is not behind CloudFront. "
            "Same column shape as the current AusTender export "
            "(agency, supplier, value, dates, UNSPSC, ABN). CKAN dataset "
            "id: 5c7fa69b-b0e9-4553-b8df-2a022dd2e982."
        ),
    ),
    SourceRecord(
        source_id="grantconnect_grants",
        name="GrantConnect — Commonwealth grants awarded",
        jurisdiction="Commonwealth",
        level="national",
        source_type="government_grant_register",
        url="https://www.grants.gov.au/Ga/Search",
        expected_format="csv_via_search_export",
        update_frequency="continuous",
        priority="high",
        notes=(
            "Every Commonwealth grant awarded under reportable programs. "
            "Per the Commonwealth Grants Rules and Guidelines (CGRGs) "
            "every grant > $0 must appear here within 21 calendar days "
            "of the grant agreement taking effect. Each grant row "
            "carries: grant ID, program, agency, recipient name + ABN, "
            "value, start/end dates, location (postcode), purpose. "
            "Grants are NOT personal receipts by MPs — they're public "
            "money flowing to recipient organisations under specific "
            "programs. Surface as a government-spending evidence "
            "family. Recipient ABN joins to the project's entity table; "
            "this lets the app surface 'this entity received $X in "
            "Commonwealth grants over the same period it appeared as "
            "a donor in AEC returns', strictly as labelled context."
        ),
    ),
    SourceRecord(
        source_id="fits_register",
        name="Foreign Influence Transparency Scheme (FITS) public register",
        jurisdiction="Commonwealth",
        level="national",
        source_type="influence_disclosure_register",
        url="https://transparency.ag.gov.au/FITS/SearchResults",
        expected_format="html_search_results",
        update_frequency="continuous",
        priority="high",
        notes=(
            "AGD-administered public register of registrants who act on "
            "behalf of foreign principals. Each registrant row "
            "discloses: registrant name + ABN, foreign principal "
            "name + country, activity type (general political activity, "
            "communications activity, parliamentary lobbying, "
            "disbursement activity), and registration date. CRITICAL "
            "transparency surface for analysing foreign-aligned "
            "influence on Australian democracy. Records are public "
            "by design under the Foreign Influence Transparency "
            "Scheme Act 2018 (Cth). Surface as its own evidence "
            "family `foreign_influence_disclosure` with a strong "
            "claim-discipline caveat: registration is a legal "
            "compliance act, NOT an allegation of wrongdoing."
        ),
    ),
    SourceRecord(
        source_id="senate_order_contracts",
        name="Senate Order on Departmental and Agency Contracts",
        jurisdiction="Commonwealth",
        level="national",
        source_type="government_contract_supplementary_register",
        url="https://www.aph.gov.au/Parliamentary_Business/Committees/Senate/Finance_and_Public_Administration/SeOrder",
        expected_format="html_per_agency_returns",
        update_frequency="biannual",
        priority="medium",
        notes=(
            "Twice-yearly Senate-ordered listing where each Commonwealth "
            "department/agency must list contracts ≥ $100k (or with "
            "confidentiality provisions). Useful supplementary surface "
            "to AusTender for high-value contracts and for "
            "confidentiality-clause flags that AusTender doesn't "
            "always expose at the row level. Per-portfolio HTML "
            "tables linked from the APH Senate FAPA committee page. "
            "Consolidates by responsible Senator (Manager of "
            "Government Business)."
        ),
    ),
    SourceRecord(
        source_id="anao_performance_audits",
        name="ANAO Auditor-General Performance Audit Reports",
        jurisdiction="Commonwealth",
        level="national",
        source_type="audit_authority_report_register",
        url="https://www.anao.gov.au/work/performance-audit",
        expected_format="html_index_with_pdf_reports",
        update_frequency="continuous",
        priority="medium",
        notes=(
            "Australian National Audit Office's program of "
            "performance audits — per-portfolio audits of how "
            "Commonwealth programs are administered. Each report "
            "carries: audit number, portfolio/agency, audit topic, "
            "tabling date, full PDF report, summary findings, "
            "recommendations. Useful evidentiary surface for "
            "'how is this portfolio's spending actually administered' "
            "queries that pair with AusTender / GrantConnect data."
        ),
    ),
    SourceRecord(
        source_id="federal_register_of_legislation",
        name="Federal Register of Legislation",
        jurisdiction="Commonwealth",
        level="national",
        source_type="legislation_register",
        url="https://www.legislation.gov.au/",
        expected_format="json_search_api_plus_html_pages",
        update_frequency="continuous",
        priority="medium",
        notes=(
            "Authoritative register of every Commonwealth Act, "
            "subordinate legislation, gazette, and explanatory "
            "memorandum. Free-text searchable; supports machine-"
            "readable URLs per legislative instrument. Pairs with "
            "the APH Bills Search to link MP voting records (TVFY) "
            "and Hansard speech context to specific legislative "
            "instruments. Public domain (Commonwealth-published "
            "primary legislation)."
        ),
    ),
    SourceRecord(
        source_id="aph_bills_search",
        name="APH Bills Search",
        jurisdiction="Commonwealth",
        level="national",
        source_type="bills_progress_register",
        url="https://www.aph.gov.au/Parliamentary_Business/Bills_Legislation/Bills_Search_Results",
        expected_format="html_search_with_per_bill_pages",
        update_frequency="continuous",
        priority="medium",
        notes=(
            "Per-Bill progress through both Houses, second-reading "
            "speeches, committee referrals, amendments, and final "
            "outcome. Each Bill page links to: full Bill text, "
            "Explanatory Memorandum, Bills Digest (Parliamentary "
            "Library analysis), Hansard for second reading speech, "
            "and (where applicable) the relevant House Vote / "
            "Senate Journal entry. Pairs with TVFY divisions to "
            "give a complete legislative-decision picture per MP."
        ),
    ),
    SourceRecord(
        source_id="aph_committee_inquiries",
        name="APH Parliamentary Committee Inquiries — submissions and transcripts",
        jurisdiction="Commonwealth",
        level="national",
        source_type="parliamentary_committee_register",
        url="https://www.aph.gov.au/Parliamentary_Business/Committees",
        expected_format="html_per_inquiry_with_pdf_submissions",
        update_frequency="continuous",
        priority="medium",
        notes=(
            "Every parliamentary committee inquiry's public "
            "submissions, transcripts, and final reports. Excellent "
            "lobbying-by-public-record surface — when a corporate "
            "entity makes a public submission to an inquiry on a "
            "policy that affects them, that is a documented "
            "influence event with date, topic, and verbatim text. "
            "Submissions are PDF-attached to the inquiry index page. "
            "Public domain content (Commonwealth-published)."
        ),
    ),
    SourceRecord(
        source_id="grants_gov_au_open_grants",
        name="GrantConnect — Open Grants and Forecast Opportunities",
        jurisdiction="Commonwealth",
        level="national",
        source_type="government_grant_opportunity_register",
        url="https://www.grants.gov.au/Go/List",
        expected_format="html_search_with_per_opportunity_pages",
        update_frequency="continuous",
        priority="low",
        notes=(
            "Companion register to the awarded-grants endpoint: "
            "lists currently-open grant opportunities and "
            "forecast opportunities. Useful for forward-looking "
            "transparency (which programs are about to award "
            "money), but NOT a money-flow surface — these are "
            "forecasts, not awards. Don't surface as influence "
            "evidence."
        ),
    ),
    SourceRecord(
        source_id="modern_slavery_register",
        name="Modern Slavery Statements register",
        jurisdiction="Commonwealth",
        level="national",
        source_type="corporate_compliance_register",
        url="https://modernslaveryregister.gov.au/",
        expected_format="html_search_with_per_statement_pdfs",
        update_frequency="annual",
        priority="low",
        notes=(
            "Mandatory register of modern-slavery statements by "
            "entities with ≥ $100M annual consolidated turnover, "
            "per the Modern Slavery Act 2018 (Cth). Each statement "
            "includes the entity ABN, the reporting period, and a "
            "PDF of the statement. Cross-references usefully with "
            "the entity table for sector-level supply-chain "
            "context. Public domain (Commonwealth-published)."
        ),
    ),
    SourceRecord(
        source_id="aph_hansard_full_text_proquest",
        name="APH Hansard full-text (ParlInfo Search)",
        jurisdiction="Commonwealth",
        level="national",
        source_type="parliamentary_speech_text",
        url="https://parlinfo.aph.gov.au/parlInfo/search/search.w3p;query=Dataset%3Ahansardr",
        expected_format="html_search_with_per_speech_pages",
        update_frequency="continuous",
        priority="medium",
        notes=(
            "Speech-level Hansard text via the ParlInfo search "
            "endpoint. Currently the project ingests divisions "
            "(via House Votes & Proceedings + Senate Journals) "
            "but NOT the speech text — extending to speeches "
            "would let the app pair every TVFY division with "
            "speaker-attributed text. ParlInfo supports per-speech "
            "permalinks so each row is reproducibly citable."
        ),
    ),
)


def all_sources() -> tuple[SourceRecord, ...]:
    return SOURCES


def get_source(source_id: str) -> SourceRecord:
    for source in SOURCES:
        if source.source_id == source_id:
            return source
    known = ", ".join(source.source_id for source in SOURCES)
    raise KeyError(f"Unknown source_id {source_id!r}. Known sources: {known}")
