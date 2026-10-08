"""RateCard: the EffortIndex lookup order (exact -> global -> another country's row, relabelled)."""

from __future__ import annotations

import logging

import pytest

from bidcore.effort.models import PHASE_FIELDS
from bidcore.effort.rate_card import BORROWED, EXACT, GLOBAL, RateCard


def test_exact_country_row_wins(card):
    row = card.get("A1", "de")
    assert (row.country_key, row.match, row.total) == ("DE", EXACT, 14.0)


def test_global_row_when_the_country_has_none(card):
    row = card.get("A1", "FR")
    assert (row.country_key, row.match, row.total) == ("", GLOBAL, 10.0)


def test_no_country_prefers_the_global_row(card):
    assert card.get("A1").match == GLOBAL
    assert card.get("C3", None).total == 10.0


def test_another_countrys_row_is_borrowed_and_relabelled(card, caplog):
    with caplog.at_level(logging.WARNING):
        row = card.get("B2", "FR")
        card.get("B2", "FR")                                   # warned once per (scope, country)
    assert row.match == BORROWED
    assert row.country_key == "FR"                             # relabelled to the requested country
    assert row.total == 10.0 and row.comments == "US only"     # the FIRST row the card lists
    assert sum("B2" in r.message and "FR" in r.message for r in caplog.records) == 1


def test_borrowing_without_a_country_keeps_the_source_label(card):
    row = card.get("B2")
    assert (row.match, row.country_key) == (BORROWED, "US")


def test_unknown_scope_item_returns_none(card):
    assert card.get("NOPE", "DE") is None
    assert "NOPE" not in card and "A1" in card


def test_repeated_key_keeps_the_last_row(card):
    assert card.get("D4", "DE").total == 15.0
    assert card.countries("D4") == ["DE"]


def test_zero_effort_row_is_returned_as_is(card):
    row = card.get("Z0", "DE")
    assert row.total == 0.0 and row.has_effort is False and row.comments == "priced at zero"


def test_sheets_are_separate_and_unknown_sheet_raises(rate_card_path):
    assert RateCard("YASH BP", rate_card_path).get("A1", "DE").total == 99.0
    with pytest.raises(ValueError, match="available sheets"):
        RateCard("Nope", rate_card_path)


def test_total_sums_all_five_phases_including_uat():
    """The source sheet's own Total formula omitted UAT; the agent sums all five (as the old one did)."""
    card = RateCard("SAP BP")                                  # the real policy/rate_cards parquet
    assert len(card) > 300
    row = next(r for sid in ("J58", "J59", "J60") if (r := card.get(sid, "US")) and r.user_acceptance_testing)
    assert row.total == round(sum(getattr(row, f) for f in PHASE_FIELDS), 2)
    assert row.total > round(row.total - row.user_acceptance_testing, 2)
