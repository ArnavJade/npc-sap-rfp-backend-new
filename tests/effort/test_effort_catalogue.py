"""compute_catalogue_effort: per-country fan-out vs one line, zero-effort lines, exclusions, overrides."""

from __future__ import annotations

import pytest

from bidcore.effort.catalogue_effort import compute_catalogue_effort, line_countries, wave_tags_from_item_tags
from bidcore.ledger.sections_effort import ItemTag, ScopeItem
from bidcore.policy import get_policy


def _item(row_id: str, scope_id: str, countries=(), **kw) -> ScopeItem:
    return ScopeItem(row_id=row_id, scope_item_id=scope_id, countries=list(countries), **kw)


def _rows(modules):
    return {r.row_id: r for m in modules.values() for r in m.rows}


def test_multi_country_bid_fans_out_one_line_per_country(card):
    modules = compute_catalogue_effort([_item("si-1", "A1", ["FR", "DE"])], ["DE", "FR"], "SAP BP", rate_card=card)
    rows = _rows(modules)
    assert list(rows) == ["si-1@DE", "si-1@FR"]                # sorted country order
    assert rows["si-1@DE"].total == 14.0                       # DE's own row
    assert rows["si-1@FR"].total == 10.0                       # global row, stamped FR
    assert rows["si-1@FR"].country == "FR" and rows["si-1@FR"].item_row_id == "si-1"
    assert modules["Finance"].total_effort == 24.0 and modules["Finance"].bp_id_count == 2


def test_single_country_bid_gets_one_line_with_that_country(card):
    modules = compute_catalogue_effort([_item("si-1", "A1", ["DE", "FR"])], ["DE"], "SAP BP", rate_card=card)
    assert list(_rows(modules)) == ["si-1@DE"]
    assert _rows(modules)["si-1@DE"].total == 14.0


def test_item_without_countries_on_a_multi_country_bid_gets_one_global_line(card):
    rows = _rows(compute_catalogue_effort([_item("si-1", "A1")], ["DE", "FR"], "SAP BP", rate_card=card))
    assert list(rows) == ["si-1@ALL"]
    assert rows["si-1@ALL"].country == "" and rows["si-1@ALL"].total == 10.0


def test_fan_out_can_be_switched_off_in_policy(card):
    p = get_policy()
    p = p.model_copy(update={"effort": p.effort.model_copy(update={
        "rate_card": p.effort.rate_card.model_copy(update={"per_country_fan_out": False})})})
    rows = _rows(compute_catalogue_effort([_item("si-1", "A1", ["DE", "FR"])], ["DE", "FR"], "SAP BP",
                                          policy=p, rate_card=card))
    assert list(rows) == ["si-1@ALL"]


def test_unpriced_item_keeps_zero_effort_lines(card):
    modules = compute_catalogue_effort([_item("si-9", "XX9", ["DE", "FR"], lob="Finance")], ["DE", "FR"],
                                       "SAP BP", rate_card=card)
    rows = _rows(modules)
    assert set(rows) == {"si-9@DE", "si-9@FR"}
    zero = rows["si-9@DE"]
    rc = get_policy().effort.rate_card
    assert zero.total == 0.0 and zero.comments == rc.zero_effort_comment
    assert zero.business_area == "General" and zero.description == "Scope Item XX9"
    assert modules["Finance"].unmatched_scope_ids == ["XX9"]


def test_rate_card_row_with_zero_effort_is_kept_as_is(card):
    modules = compute_catalogue_effort([_item("si-1", "Z0", lob="Finance")], ["DE"], "SAP BP", rate_card=card)
    row = _rows(modules)["si-1@DE"]
    assert row.total == 0.0 and row.comments == "priced at zero"
    assert modules["Finance"].unmatched_scope_ids == []


def test_existing_no_change_items_are_not_costed(card):
    items = [_item("si-1", "A1", ["DE"]), _item("si-2", "C3", ["DE"], status="excluded_existing")]
    modules = compute_catalogue_effort(items, ["DE"], "SAP BP", rate_card=card)
    assert modules["Sales"].rows == [] and modules["Sales"].excluded_scope_ids == ["C3"]
    assert [r.scope_id for r in modules["Finance"].rows] == ["A1"]


def test_ledger_labels_win_over_the_rate_card(card):
    item = _item("si-1", "C3", ["DE"], lob="Finance", business_area="Treasury", description="Cash ops")
    rows = _rows(compute_catalogue_effort([item], ["DE"], "SAP BP", rate_card=card))
    row = rows["si-1@DE"]
    assert (row.lob, row.business_area, row.description) == ("Finance", "Treasury", "Cash ops")
    blank = _rows(compute_catalogue_effort([_item("si-2", "C3", ["DE"])], ["DE"], "SAP BP", rate_card=card))
    assert (blank["si-2@DE"].lob, blank["si-2@DE"].business_area) == ("Sales", "Order to Cash")


def test_factors_and_wave_tags_key_on_the_line_id(card):
    items = [_item("si-1", "A1", ["DE", "FR"], submodule="General Ledger (FI)"),
             _item("si-2", "A1", ["DE"], submodule="Controlling (CO)"),
             _item("si-3", "A1", ["DE"], submodule="General Ledger (FI)")]
    modules = compute_catalogue_effort(items, ["DE", "FR"], "SAP BP", factors={"si-1@DE": 1.5},
                                       wave_tags={"si-1@FR": " Wave 2 "}, rate_card=card)
    rows = _rows(modules)
    assert rows["si-1@DE"].multiplication_factor == 1.5 and rows["si-1@DE"].total == 21.0
    assert rows["si-1@FR"].multiplication_factor == 1.0 and rows["si-1@FR"].wave == "Wave 2"
    assert rows["si-1@DE"].wave == ""
    assert modules["Finance"].submodules == ["Controlling (CO)", "General Ledger (FI)"]


def test_negative_factor_is_rejected(card):
    with pytest.raises(ValueError, match="si-1@DE"):
        compute_catalogue_effort([_item("si-1", "A1", ["DE"])], ["DE"], "SAP BP", factors={"si-1@DE": -1},
                                 rate_card=card)


def test_line_countries_rules():
    item = _item("si-1", "A1", ["fr", "DE", "FR"])
    assert line_countries(item, ["DE", "FR"]) == ["DE", "FR"]
    assert line_countries(item, ["DE"]) == ["DE"]
    assert line_countries(item, []) == [""]
    assert line_countries(_item("si-2", "A1"), ["DE", "FR"]) == [""]


def test_item_tags_map_to_line_ids_and_country_tags_win():
    items = [_item("si-1", "A1", ["DE", "FR"]), _item("si-2", "B2", ["DE"])]
    tags = [ItemTag(row_id="si-1", country="FR", wave="Wave 2"), ItemTag(row_id="si-1", wave="Wave 1"),
            ItemTag(row_id="si-2", wave="Wave 3"), ItemTag(row_id="si-404", wave="Wave 1")]
    assert wave_tags_from_item_tags(items, ["DE", "FR"], tags) == {
        "si-1@DE": "Wave 1", "si-1@FR": "Wave 2", "si-2@DE": "Wave 3"}
