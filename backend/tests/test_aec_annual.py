from au_politics_money.ingest.aec_annual import parse_money


def test_parse_money_handles_currency_formatting() -> None:
    assert parse_money("$1,234.50") == "1234.50"
    assert parse_money("17300") == "17300"
    assert parse_money("") == ""
    assert parse_money("not stated") == ""

