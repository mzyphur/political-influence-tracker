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
        "aec_federal_boundaries_gis",
    }
    known = {source.source_id for source in all_sources()}
    assert required <= known


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
