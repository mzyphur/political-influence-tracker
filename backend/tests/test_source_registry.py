from au_politics_money.ingest.discovered_sources import (
    child_source_id,
    source_from_discovered_link,
)
from au_politics_money.ingest.discovery import discover_links_from_html
from au_politics_money.ingest.sources import all_sources, get_source
from au_politics_money.models import DiscoveredLink


def test_source_ids_are_unique() -> None:
    source_ids = [source.source_id for source in all_sources()]
    assert len(source_ids) == len(set(source_ids))


def test_core_federal_sources_exist() -> None:
    required = {
        "aec_transparency_downloads",
        "aph_members_interests_48",
        "aph_senators_interests",
        "aph_contacts_csv",
        "aph_members_contact_list_pdf",
        "aph_senators_contact_list_pdf",
        "aec_federal_boundaries_gis",
        "aph_house_votes_and_proceedings",
        "aph_senate_journals",
    }
    known = {source.source_id for source in all_sources()}
    assert required <= known


def test_subnational_seed_sources_exist() -> None:
    required = {
        "nsw_electoral_disclosures",
        "vic_vec_disclosures",
        "qld_ecq_disclosures",
        "sa_ecsa_funding_disclosure",
        "waec_returns_reports",
        "tas_tec_disclosure_funding",
        "nt_ntec_annual_returns",
        "act_elections_funding_disclosure",
    }
    sources = {source.source_id: source for source in all_sources()}

    assert required <= set(sources)
    assert sources["nsw_electoral_disclosures"].level == "state_council"
    assert sources["qld_ecq_disclosures"].level == "state_council"
    assert "campaign context" in sources["act_elections_funding_disclosure"].notes


def test_get_source_returns_record() -> None:
    source = get_source("aec_transparency_downloads")
    assert source.name == "AEC Download All Disclosure Data"
    assert source.priority == "core"


def test_discover_aec_download_links() -> None:
    source = get_source("aec_transparency_downloads")
    html = """
    <html>
      <body>
        <a href="/Download/AllElectionsData">Download all Election Data</a>
        <a href="/Download/AllAnnualData">Download all Annual Data</a>
        <a href="/Download/AllReferendumData">Download all Referendum Data</a>
        <a href="/AnnualDetailedReceipts">Detailed Receipts</a>
      </body>
    </html>
    """
    links = discover_links_from_html(source, html)
    urls = {link.url for link in links}
    assert urls == {
        "https://transparency.aec.gov.au/Download/AllElectionsData",
        "https://transparency.aec.gov.au/Download/AllAnnualData",
        "https://transparency.aec.gov.au/Download/AllReferendumData",
    }


def test_discover_senate_interests_env_asset() -> None:
    source = get_source("aph_senators_interests")
    html = """
    <html>
      <body>
        <script src="/js/apps/senators-interests-register/build/env.js?v=123"></script>
        <script src="/unrelated.js"></script>
      </body>
    </html>
    """
    links = discover_links_from_html(source, html)

    assert len(links) == 1
    assert links[0].link_type == "js"
    assert links[0].url == "https://www.aph.gov.au/js/apps/senators-interests-register/build/env.js?v=123"


def test_discover_aph_contact_csv_and_pdf_links() -> None:
    source = get_source("aph_contacts_csv")
    html = """
    <html>
      <body>
        <a href="/-/media/03_Senators_and_Members/32_Members/Lists/Members_List.pdf">
          Members List PDF
        </a>
        <a href="/-/media/03_Senators_and_Members/Address_Labels_and_CSV_files/Senators/allsenstate.csv">
          All Senators by State CSV
        </a>
        <a href="/unrelated.html">Unrelated</a>
      </body>
    </html>
    """
    links = discover_links_from_html(source, html)

    assert {link.link_type for link in links} == {"csv", "pdf"}
    assert len(links) == 2


def test_discover_nsw_disclosure_links() -> None:
    source = get_source("nsw_electoral_disclosures")
    html = """
    <html>
      <body>
        <a href="https://efadisclosures.elections.nsw.gov.au/">Search and view disclosures</a>
        <a href="/funding-and-disclosure/disclosures/pre-election-period-donation-disclosure/2023-nsw-state-election-donations">
          View donations by district
        </a>
        <a href="/electoral-funding/public-register-and-lists/register-of-third-party-lobbyists">
          Register of third-party lobbyists
        </a>
        <a href="/media-centre/news">General news</a>
      </body>
    </html>
    """
    links = discover_links_from_html(source, html)

    assert {link.title for link in links} == {
        "Search and view disclosures",
        "View donations by district",
        "Register of third-party lobbyists",
    }
    assert all("news" not in link.url for link in links)


def test_discover_vic_disclosure_links() -> None:
    source = get_source("vic_vec_disclosures")
    html = """
    <html>
      <body>
        <a href="https://disclosures.vec.vic.gov.au/public-donations/">VEC Disclosures</a>
        <a href="/candidates-and-parties/funding/funding-register">Funding register</a>
        <a href="/candidates-and-parties/annual-returns/associated-entities">
          Associated entities annual returns
        </a>
        <a href="https://lgi.vic.gov.au/council-election-campaign-donation-returns">
          Council election campaign donation returns
        </a>
        <a href="/about-us">About us</a>
      </body>
    </html>
    """
    links = discover_links_from_html(source, html)

    assert {link.url for link in links} == {
        "https://disclosures.vec.vic.gov.au/public-donations/",
        "https://www.vec.vic.gov.au/candidates-and-parties/funding/funding-register",
        "https://www.vec.vic.gov.au/candidates-and-parties/annual-returns/associated-entities",
        "https://lgi.vic.gov.au/council-election-campaign-donation-returns",
    }


def test_discover_qld_disclosure_links() -> None:
    source = get_source("qld_ecq_disclosures")
    html = """
    <html>
      <body>
        <a href="https://disclosures.ecq.qld.gov.au/">Electronic Disclosure System</a>
        <a href="/donations-and-expenditure-disclosure/disclosure-of-political-donations-and-electoral-expenditure/published-disclosure-returns">
          Published disclosure returns
        </a>
        <a href="/election-participants/local-election-participants">Local election participants</a>
        <a href="https://legislation.qld.gov.au/view/html/inforce/current/act-1992-028">
          Electoral Act 1992
        </a>
        <a href="/contact-us">Contact us</a>
      </body>
    </html>
    """
    links = discover_links_from_html(source, html)

    assert {link.title for link in links} == {
        "Electronic Disclosure System",
        "Published disclosure returns",
        "Local election participants",
        "Electoral Act 1992",
    }
    assert all("contact-us" not in link.url for link in links)


def test_discovered_source_ids_are_stable() -> None:
    parent = get_source("aph_contacts_csv")
    link = DiscoveredLink(
        parent_source_id=parent.source_id,
        url=(
            "https://www.aph.gov.au/-/media/03_Senators_and_Members/"
            "Address_Labels_and_CSV_files/Senators/allsenstate.csv"
        ),
        title="All senators by state",
        link_type="csv",
        notes="test",
    )

    child = source_from_discovered_link(parent, link)

    assert child.source_id == child_source_id(parent.source_id, link)
    assert child.source_id == "aph_contacts_csv__allsenstate_csv__4e37f23f84"
    assert child.url == link.url
