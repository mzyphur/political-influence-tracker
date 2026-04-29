from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ServingDatabaseQualityConfig:
    boundary_set: str = "aec_federal_2025_current"
    expected_house_boundary_count: int = 150
    max_official_unmatched_votes: int = 25


FORM_NOISE_DESCRIPTIONS = (
    "HOUSE OF REPRESENTATIVES",
    "PARLIAMENT OF AUSTRALIA",
    "Signed: Date:",
)


def _scalar(conn, sql: str, params: tuple[Any, ...] = ()) -> int:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        value = cur.fetchone()[0]
    return int(value or 0)


def _check(
    checks: list[dict[str, Any]],
    *,
    check_id: str,
    status: str,
    metric: int,
    message: str,
) -> None:
    checks.append(
        {
            "id": check_id,
            "status": status,
            "metric": metric,
            "message": message,
        }
    )


def run_serving_database_quality_checks(
    conn,
    config: ServingDatabaseQualityConfig | None = None,
) -> dict[str, Any]:
    cfg = config or ServingDatabaseQualityConfig()
    checks: list[dict[str, Any]] = []

    boundary_count = _scalar(
        conn,
        "SELECT count(*) FROM electorate_boundary WHERE boundary_set = %s",
        (cfg.boundary_set,),
    )
    _check(
        checks,
        check_id="house_boundary_count",
        status="pass" if boundary_count == cfg.expected_house_boundary_count else "fail",
        metric=boundary_count,
        message=(
            f"{cfg.boundary_set} has {boundary_count} House boundaries; "
            f"expected {cfg.expected_house_boundary_count}."
        ),
    )

    current_house_terms_without_boundary = _scalar(
        conn,
        """
        SELECT count(*)
        FROM office_term
        WHERE chamber = 'house'
          AND term_end IS NULL
          AND electorate_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM electorate_boundary
              WHERE electorate_boundary.electorate_id = office_term.electorate_id
                AND electorate_boundary.boundary_set = %s
          )
        """,
        (cfg.boundary_set,),
    )
    _check(
        checks,
        check_id="current_house_terms_have_boundaries",
        status="pass" if current_house_terms_without_boundary == 0 else "fail",
        metric=current_house_terms_without_boundary,
        message=(
            f"{current_house_terms_without_boundary} current House office terms lack "
            f"a {cfg.boundary_set} boundary."
        ),
    )

    active_events_from_non_current_rows = _scalar(
        conn,
        """
        SELECT count(*)
        FROM influence_event
        WHERE review_status <> 'rejected'
          AND (
              EXISTS (
                  SELECT 1
                  FROM money_flow
                  WHERE money_flow.id = influence_event.money_flow_id
                    AND money_flow.is_current = FALSE
              )
              OR EXISTS (
                  SELECT 1
                  FROM gift_interest
                  WHERE gift_interest.id = influence_event.gift_interest_id
                    AND gift_interest.is_current = FALSE
              )
          )
        """,
    )
    _check(
        checks,
        check_id="no_public_events_from_non_current_source_rows",
        status="pass" if active_events_from_non_current_rows == 0 else "fail",
        metric=active_events_from_non_current_rows,
        message=(
            f"{active_events_from_non_current_rows} non-rejected influence events "
            "still point at non-current source rows."
        ),
    )

    active_form_noise_events = _scalar(
        conn,
        """
        SELECT count(*)
        FROM influence_event
        WHERE review_status <> 'rejected'
          AND description = ANY(%s)
        """,
        (list(FORM_NOISE_DESCRIPTIONS),),
    )
    _check(
        checks,
        check_id="no_obvious_form_noise_events",
        status="pass" if active_form_noise_events == 0 else "fail",
        metric=active_form_noise_events,
        message=(
            f"{active_form_noise_events} active influence events look like known "
            "House form/OCR boilerplate."
        ),
    )

    official_division_count_mismatches = _scalar(
        conn,
        """
        SELECT count(*)
        FROM vote_division
        WHERE metadata->>'source' = 'aph_official_decision_record'
          AND metadata->>'vote_count_matches' = 'false'
        """,
    )
    _check(
        checks,
        check_id="official_aph_division_vote_counts_match",
        status="pass" if official_division_count_mismatches == 0 else "fail",
        metric=official_division_count_mismatches,
        message=(
            f"{official_division_count_mismatches} official APH divisions have "
            "parsed vote-count mismatches."
        ),
    )

    official_unmatched_votes = _scalar(
        conn,
        """
        SELECT COALESCE(sum((metadata->>'unmatched_roster_vote_count')::integer), 0)
        FROM vote_division
        WHERE metadata->>'source' = 'aph_official_decision_record'
          AND metadata ? 'unmatched_roster_vote_count'
        """,
    )
    _check(
        checks,
        check_id="official_aph_unmatched_roster_votes",
        status=(
            "pass" if official_unmatched_votes <= cfg.max_official_unmatched_votes else "fail"
        ),
        metric=official_unmatched_votes,
        message=(
            f"{official_unmatched_votes} official APH votes are unmatched to the "
            f"current roster; allowed maximum is {cfg.max_official_unmatched_votes}."
        ),
    )

    failed = [check for check in checks if check["status"] == "fail"]
    return {
        "status": "pass" if not failed else "fail",
        "failed_count": len(failed),
        "checks": checks,
    }
