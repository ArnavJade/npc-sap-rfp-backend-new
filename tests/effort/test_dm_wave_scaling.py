"""Data Migration: one table per wave, each the base table scaled to what that wave migrates."""

from __future__ import annotations

from bidcore.ledger.sections_effort import DataMigrationWave
from bidcore.render.workbook.manifest import apply_overrides
from bidcore.ledger.sections_proposal import Override
from bidcore.sizing import compute_effort, size_bid
from tests.fixtures_bid import build_ledger

KEYS = ("func_spec", "program_dev", "iteration_1", "iteration_2", "iteration_3", "cutover")


def _table_days(table):
    return sum(float(r[k]) for r in table for k in KEYS)


def test_fallback_scales_by_allocation_share():
    ledger = build_ledger()                       # data_migration shares 0.7 / 0.3, no data_migration_waves
    w1, w2 = size_bid(ledger).effort.workstreams.data_migration
    base = {r.row_id: r for r in ledger.data_migration.rows}
    for row in w2:                                # 0.3 / 0.7 of the base, snapped to the grid
        assert row["iteration_1"] <= base[row["row_id"]].iteration_1
    assert _table_days(w2) < _table_days(w1)


def test_wave_plan_scale_key_scale_and_objects():
    ledger = build_ledger()
    first = ledger.data_migration.rows[0]
    ledger.wave_plan.data.data_migration_waves = [
        DataMigrationWave(wave="Wave 1", scale=1.0),
        DataMigrationWave(wave="Wave 2", scale=2.0, key_scale={"func_spec": 0.5, "program_dev": 0.5},
                          objects=[first.row_id], rationale="two entities; programs reused"),
    ]
    effort = compute_effort(ledger, 2, None, ["Wave 1", "Wave 2"])     # before scope sync
    w1, w2 = effort.workstreams.data_migration
    assert len(w1) == len(ledger.data_migration.rows) and [r["row_id"] for r in w2] == [first.row_id]
    assert w2[0]["iteration_1"] == min(first.iteration_1 * 2, 4.0)
    assert w2[0]["func_spec"] == max(first.func_spec * 0.5, 0.5)
    assert any("scale 2" in n for n in effort.workstreams.notes)
    # the Data Migration person-days are split across the waves exactly as the two tables split them
    from bidcore.effort.waves import allocate_waves
    from bidcore.timeline.resolve import resolve_timeline

    timeline = resolve_timeline(ledger.timeline.data, ledger.wave_plan.data, 100.0, ["SA", "AE"])
    wave_effort, _ = allocate_waves(effort, timeline, ledger.wave_plan.data)
    title = next(k for k in wave_effort.category[0] if "Migration" in k)
    assert [round(c.get(title, 0.0), 2) for c in wave_effort.category] == [_table_days(w1), _table_days(w2)]
    assert any("scale 2" in n for n in size_bid(ledger).notes)


def test_later_wave_edit_changes_that_wave_only():
    ledger = build_ledger()
    rid = ledger.data_migration.rows[0].row_id
    apply_overrides(ledger, [Override(sheet="Data Migration Scope", section="data_migration", row_id=f"{rid}#2",
                                      field="cutover", new=4.0, kind="edit")])
    assert ledger.data_migration.rows[0].cutover == 1.0              # the base row is untouched
    assert any(o.section == "data_migration_wave" for o in ledger.overrides)
    w1, w2 = size_bid(ledger).effort.workstreams.data_migration
    assert next(r for r in w2 if r["row_id"] == rid)["cutover"] == 4.0


def test_wave_plan_validation_of_data_migration_waves():
    from bidcore.catalogue.store import get_catalogue
    from bidcore.ledger.validate import ValidationContext, validate
    from bidcore.policy import get_policy

    ledger = build_ledger()
    ctx = ValidationContext(get_policy(), get_catalogue(), None, ledger)
    plan = ledger.wave_plan.data.model_dump()
    plan["data_migration_waves"] = [{"wave": "Wave 9", "scale": 0}, {"wave": "Wave 2", "key_scale": {"bogus": 1},
                                                                       "objects": ["dm-99"]}]
    [v] = validate("wave_plan", [plan], ctx)
    text = " ".join(v.errors)
    assert "unknown wave 'Wave 9'" in text and "scale 0" in text and "bogus" in text and "dm-99" in text
