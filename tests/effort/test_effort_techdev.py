"""compute_tech_dev: RICEFW rows / lump split, Fiori floor, third-party split, residual interfaces.

Fiori floor and third-party expectations are ported from the old unit tests
(test_third_party_tech_dev_structuring: 20 apps x (10,2,2,2) h -> 500/100/100/100 = 800 PD;
20 apps x (336,48,48,48) h -> 1200 PD; integration rows keep their system name and 1 object).
"""

from __future__ import annotations

import pytest

from bidcore.effort.techdev import compute_tech_dev, norm_complexity, split_counts
from bidcore.ledger.sections_effort import Fiori, Integration, Ricefw, RicefwRow

COLS = ("development", "configuration", "unit_testing", "qa_testing")


def _cells(row):
    return tuple(getattr(row, c) for c in COLS)


def test_split_counts_last_bucket_absorbs_the_remainder():
    assert split_counts(350, [40, 30, 30]) == [140, 105, 105]
    assert split_counts(10, [33, 33, 34]) == [3, 3, 4]
    assert split_counts(10, [50, 20, 10]) == [5, 2, 3]          # split short of 100%: last bucket fills
    assert split_counts(7, [0, 100, 0]) == [0, 7, 0]


def test_norm_complexity_spellings():
    assert [norm_complexity(x) for x in ("Simple", "l", "COMPLEX", "h", "", None, "odd")] == [
        "Low", "Low", "High", "High", "Medium", "Medium", "Medium"]


def test_explicit_rows_use_stated_hours_else_per_object_hours():
    ricefw = Ricefw(rows=[
        RicefwRow(object_type="Form", no_of_objects=10, complexity="Low", development=80.0),
        RicefwRow(object_type="", no_of_objects=4, complexity="High"),
        RicefwRow(object_type="Report", no_of_objects=0),                 # no objects -> no row
    ], development_objects_total=999)                                    # ignored: rows win
    rows = compute_tech_dev(ricefw, None, [])
    assert [r.row_id for r in rows] == ["ricefw-1", "ricefw-2"]
    form, high = rows
    # stated 80 h for the row; the rest is Low per-object hours x 10 objects; all / 8 h per day
    assert (form.object_name, form.object_type, form.complexity) == ("RICEFW", "Form", "Low")
    assert _cells(form) == (10.0, round(0.25 * 10 / 8, 2), 0.62, 0.62)
    assert (high.object_type, high.no_of_objects) == ("WRICEF", 4)
    assert _cells(high) == (3.0, 0.5, 0.75, 0.75) and high.total == 5.0


def test_lump_total_is_split_by_complexity_with_cycling_object_types():
    rows = compute_tech_dev(Ricefw(development_objects_total=350,
                                   complexity_split_pct={"Complex": 40, "medium": 30, "simple": 30}), None, [])
    assert [(r.object_type, r.no_of_objects, r.complexity) for r in rows] == [
        ("Report", 140, "High"), ("Enhancement", 105, "Medium"), ("Form", 105, "Low")]
    assert _cells(rows[0]) == (105.0, 17.5, 26.25, 26.25) and rows[0].total == 175.0
    assert all(r.source == "ricefw" for r in rows)


def test_lump_total_without_a_split_is_all_medium_and_named_type_is_kept():
    rows = compute_tech_dev(Ricefw(development_objects_total=16, development_object_type="Interface"), None, [])
    assert [(r.object_type, r.no_of_objects, r.complexity) for r in rows] == [("Interface", 16, "Medium")]
    assert _cells(rows[0]) == (8.0, 1.0, 2.0, 2.0)


@pytest.mark.parametrize("per_app,expected,total", [
    ({"development": 10, "configuration": 2, "unit_testing": 2, "qa_testing": 2}, (500.0, 100.0, 100.0, 100.0), 800.0),
    ({"development": 336, "configuration": 48, "unit_testing": 48, "qa_testing": 48}, (840.0, 120.0, 120.0, 120.0), 1200.0),
])
def test_fiori_hours_are_floored_at_40_mandays_per_app(per_app, expected, total):
    (row,) = compute_tech_dev(None, Fiori(app_count=20, per_app_hours=per_app), [])
    assert _cells(row) == expected and row.total == total
    assert (row.row_id, row.source, row.object_name, row.object_type, row.complexity) == (
        "fiori", "fiori", "Custom Fiori Applications", "FIORI", "High")


def test_fiori_count_is_the_larger_of_count_and_names_and_defaults_to_40_pd_per_app():
    (row,) = compute_tech_dev(None, Fiori(app_count=1, app_names=["A", "B", "C"]), [])
    assert row.no_of_objects == 3 and row.total == 120.0
    assert compute_tech_dev(None, Fiori(), []) == []


def test_third_party_rows_split_person_days_without_dividing_by_eight():
    integrations = [
        Integration(row_id="int-1", system="Kronos", effort_days=280, middleware="SAP PI/PO (SOAP)",
                    source_system="Kronos", target_system="SAP S/4HANA", complexity="High"),
        Integration(row_id="int-2", system="", effort_days=40),
    ]
    kronos, unnamed = compute_tech_dev(None, None, integrations)
    assert (kronos.row_id, kronos.source, kronos.object_name, kronos.object_type) == (
        "int:int-1", "third_party", "Kronos", "Interface")
    assert (kronos.middleware, kronos.source_system, kronos.target_system) == (
        "SAP PI/PO (SOAP)", "Kronos", "SAP S/4HANA")
    assert (kronos.no_of_objects, kronos.complexity) == (1, "High")
    assert _cells(kronos) == (168.0, 28.0, 42.0, 42.0) and kronos.total == 280.0
    assert unnamed.object_name == "3rd Party Integration Module 2" and unnamed.total == 40.0


def test_interface_row_is_the_rfp_total_minus_the_integrations():
    integrations = [Integration(row_id=f"int-{i}", system=f"S{i}", effort_days=10) for i in range(2)]
    rows = compute_tech_dev(Ricefw(interface_total_count=10), None, integrations)
    interface = rows[-1]
    assert (interface.row_id, interface.source, interface.no_of_objects) == ("interface", "interface", 8)
    assert _cells(interface) == (4.0, 0.5, 1.0, 1.0) and interface.total == 6.5
    assert [r.row_id for r in compute_tech_dev(Ricefw(interface_total_count=1), None, integrations)] == [
        "int:int-0", "int:int-1"]                               # never negative


def test_sheet_order_and_sources():
    rows = compute_tech_dev(Ricefw(development_objects_total=2, interface_total_count=3), Fiori(app_count=1),
                            [Integration(row_id="int-1", system="Coupa", effort_days=5)])
    assert [r.source for r in rows] == ["ricefw", "fiori", "third_party", "interface"]
    assert all(r.module == "All" for r in rows)
