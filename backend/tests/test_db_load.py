from datetime import date

from au_politics_money.db.load import (
    _can_create_house_interest_person,
    apply_schema,
    normalize_electorate_name,
    normalize_name,
    parse_date,
    senate_api_name_to_canonical,
)


class RecordingCursor:
    def __init__(self) -> None:
        self.executed_sql = ""

    def __enter__(self) -> "RecordingCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute(self, sql: str) -> None:
        self.executed_sql = sql


class RecordingConnection:
    def __init__(self) -> None:
        self.cursor_instance = RecordingCursor()
        self.committed = False

    def cursor(self) -> RecordingCursor:
        return self.cursor_instance

    def commit(self) -> None:
        self.committed = True


def test_normalize_name_is_stable_for_entity_matching() -> None:
    assert normalize_name("Example Pty. Ltd.") == "example pty ltd"
    assert normalize_name("  A.B.C.  Holdings  ") == "a b c holdings"


def test_parse_date_accepts_aec_common_formats() -> None:
    assert parse_date("31/12/2025") == date(2025, 12, 31)
    assert parse_date("2025-12-31") == date(2025, 12, 31)
    assert parse_date("8/14/2025 1:31:50 PM") == date(2025, 8, 14)
    assert parse_date("") is None
    assert parse_date("not supplied") is None


def test_senate_api_name_to_canonical() -> None:
    assert senate_api_name_to_canonical("Allman-Payne, Penny") == "Penny Allman-Payne"
    assert senate_api_name_to_canonical("Alex Antic") == "Alex Antic"


def test_normalize_electorate_name_strips_ocr_old_suffix() -> None:
    assert normalize_electorate_name("KENNEDY OLD") == "kennedy"
    assert normalize_electorate_name("Farrer") == "farrer"


def test_house_interest_person_fallback_requires_real_electorate() -> None:
    assert _can_create_house_interest_person(
        {
            "member_name": "Sussan Ley",
            "given_names": "Sussan",
            "family_name": "Ley",
            "electorate": "Farrer",
            "state": "New South Wales",
        }
    )
    assert not _can_create_house_interest_person(
        {
            "member_name": "= ANTHONY ALBANESE |",
            "given_names": "= ANTHONY",
            "family_name": "ALBANESE |",
            "electorate": "I",
            "state": "NSW",
        }
    )


def test_apply_schema_loads_backend_schema() -> None:
    conn = RecordingConnection()

    apply_schema(conn)

    assert "CREATE TABLE source_document" in conn.cursor_instance.executed_sql
    assert conn.committed is True
