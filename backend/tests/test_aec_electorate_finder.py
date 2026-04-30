from __future__ import annotations

import pytest

from au_politics_money.ingest.aec_electorate_finder import (
    POSTCODE_CAVEAT,
    parse_aec_electorate_finder_postcode_html,
)


def test_parse_aec_electorate_finder_postcode_preserves_ambiguity() -> None:
    html = """
    <html>
      <body>
        <div class="alerts alerts--info">
          <p>Electorate results below reflect electorates that will be in place at the next federal election.</p>
          <p>Despite electorate changes, your local member remains the person elected on the electorates in place at the previous federal election or subsequent by-election.</p>
        </div>
        <table id="ContentPlaceHolderBody_gridViewLocalities">
          <tr>
            <th>State</th>
            <th>Locality/Suburb</th>
            <th>Postcode</th>
            <th>Electorate(s)</th>
            <th>Redistributed Electorate(s)</th>
            <th>Other Locality(s)</th>
          </tr>
          <tr><td>ACT</td><td>BARTON</td><td>2600</td><td><a href="LocalitySearchResults.aspx?filter=Canberra&amp;filterby=Electorate&amp;divid=101">Canberra</a></td><td></td><td></td></tr>
          <tr><td>ACT</td><td>HMAS HARMAN</td><td>2600</td><td><a href="LocalitySearchResults.aspx?filter=Bean&amp;filterby=Electorate&amp;divid=318">Bean</a></td><td></td><td></td></tr>
          <tr><td>ACT</td><td>PARKES</td><td>2600</td><td><a href="LocalitySearchResults.aspx?filter=Canberra&amp;filterby=Electorate&amp;divid=101">Canberra</a></td><td></td><td></td></tr>
        </table>
        <p>This page last updated 11 September 2025</p>
      </body>
    </html>
    """

    records, summary = parse_aec_electorate_finder_postcode_html(html, postcode="2600")

    assert summary["electorate_count"] == 2
    assert summary["records"] == 2
    assert summary["page_updated_text"] == "11 September 2025"
    assert {record["electorate_name"] for record in records} == {"Bean", "Canberra"}
    assert {record["ambiguity"] for record in records} == {"ambiguous_postcode"}
    assert {record["confidence"] for record in records} == {0.5}
    canberra = next(record for record in records if record["electorate_name"] == "Canberra")
    assert canberra["localities"] == ["BARTON", "PARKES"]
    assert canberra["locality_count"] == 2
    assert canberra["aec_division_ids"] == [101]
    assert canberra["source_boundary_context"] == "next_federal_election_electorates"
    assert canberra["current_member_context"] == (
        "previous_election_or_subsequent_by_election_member"
    )
    assert "next federal election" in str(canberra["aec_boundary_note"])
    assert canberra["caveat"] == POSTCODE_CAVEAT


def test_parse_aec_electorate_finder_postcode_rejects_non_postcode() -> None:
    with pytest.raises(ValueError, match="four-digit"):
        parse_aec_electorate_finder_postcode_html("<html></html>", postcode="300")


def test_parse_aec_electorate_finder_postcode_skips_pagination_footer() -> None:
    """The AEC GridView appends a pagination footer that historically
    parsed as a junk data row (`{State='1 2', Postcode='2'}`) and broke
    the entire normalize step on postcodes that span multiple result
    pages (e.g. 2800 / 2480 / 0820 / 4350 / 3350 / 6330). The parser
    must silently skip those rows.
    """
    html = """
    <html>
      <body>
        <table id="ContentPlaceHolderBody_gridViewLocalities">
          <tr>
            <th>State</th>
            <th>Locality/Suburb</th>
            <th>Postcode</th>
            <th>Electorate(s)</th>
            <th>Redistributed Electorate(s)</th>
            <th>Other Locality(s)</th>
          </tr>
          <tr><td>NSW</td><td>ORANGE</td><td>2800</td>
            <td><a href="LocalitySearchResults.aspx?filter=Calare&amp;filterby=Electorate&amp;divid=131">Calare</a></td>
            <td></td><td></td>
          </tr>
          <tr>
            <td><a href="?page=1">1</a> <a href="?page=2">2</a></td>
            <td><a href="?page=1">1</a></td>
            <td><a href="?page=2">2</a></td>
          </tr>
        </table>
      </body>
    </html>
    """
    records, summary = parse_aec_electorate_finder_postcode_html(html, postcode="2800")
    assert summary["records"] == 1
    assert records[0]["electorate_name"] == "Calare"
    assert records[0]["postcode"] == "2800"
