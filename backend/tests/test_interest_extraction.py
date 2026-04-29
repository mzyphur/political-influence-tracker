from au_politics_money.ingest.interest_extraction import extract_provider


def test_extract_provider_skips_travel_class_change_from_phrase() -> None:
    provider = extract_provider(
        "An upgrade from Economy to Business on Drukair (KB153) from Bangkok "
        "to Paro, Bhutan on 25 September 2025"
    )

    assert provider["value"] == ""
    assert provider["method"] == ""


def test_extract_provider_preserves_parenthetical_acronym() -> None:
    provider = extract_provider(
        "Foxtel subscription from the Australian Subscription Television and "
        "Radio Association (ASTRA) for Electorate Office"
    )

    assert provider["value"] == "the Australian Subscription Television and Radio Association (ASTRA)"
    assert provider["method"] == "explicit_provider_phrase:from"


def test_extract_provider_skips_travel_route_then_uses_explicit_provider() -> None:
    provider = extract_provider(
        "Flight from Sydney to Melbourne provided by Qantas on 12 April 2025"
    )

    assert provider["value"] == "Qantas"
    assert provider["method"] == "explicit_provider_phrase:provided by"
