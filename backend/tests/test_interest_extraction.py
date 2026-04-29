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


def test_extract_provider_reads_leading_benefit_provider_before_dash() -> None:
    provider = extract_provider("Cricket Australia - 2 x tickets - Ashes")

    assert provider["value"] == "Cricket Australia"
    assert provider["method"] == "leading_provider_benefit_phrase"


def test_extract_provider_reads_leading_benefit_provider_before_covering_clause() -> None:
    provider = extract_provider(
        "McKinnon Institute, covering the costs of tuition, induction, residential intensive "
        "and workshop accommodation"
    )

    assert provider["value"] == "McKinnon Institute"
    assert provider["method"] == "leading_provider_benefit_phrase"


def test_extract_provider_infers_virgin_club_variants() -> None:
    provider = extract_provider("Virgin The Club Membership")

    assert provider["value"] == "Virgin Australia"
    assert provider["method"] == "known_brand_provider:virgin_australia"


def test_extract_provider_does_not_treat_event_title_as_leading_provider() -> None:
    provider = extract_provider("Melbourne Cup - 2 x tickets")

    assert provider["value"] == ""
    assert provider["method"] == ""


def test_extract_provider_does_not_treat_generic_occasion_as_leading_provider() -> None:
    provider = extract_provider("State of Origin - hospitality")

    assert provider["value"] == ""
    assert provider["method"] == ""


def test_extract_provider_does_not_treat_route_as_leading_provider() -> None:
    provider = extract_provider("Sydney to Melbourne - flights")

    assert provider["value"] == ""
    assert provider["method"] == ""
