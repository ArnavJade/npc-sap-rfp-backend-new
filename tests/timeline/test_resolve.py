"""Timeline resolution precedence: RFP-stated > wave-plan (agent) > derived bands; programme length."""

from __future__ import annotations

from bidcore.ledger.sections_effort import Timeline, Wave, WaveAllocation, WavePhasePlan, WavePlan
from bidcore.timeline.resolve import estimate_duration_months, resolve_timeline


def _waves(*specs):
    return [Wave(name=n, sequence=i + 1, total_weeks=w, hypercare_weeks=h) for i, (n, w, h) in enumerate(specs)]


def test_rfp_durations_are_kept_and_sequential_waves_add_up():
    t = Timeline(waves=_waves(("Wave 1", 44, 12), ("Wave 2", 30, 8)), sequencing="sequential")
    r = resolve_timeline(t, None, 3000, ["SA", "AE"])
    assert [w.total_weeks for w in r.waves] == [44, 30]
    assert [w.duration_source for w in r.waves] == ["rfp", "rfp"]
    assert r.programme_weeks == 74 and r.is_sequential
    assert r.wave_start_month(r.waves[1]) == r.waves[0].total_months


def test_parallel_programme_is_as_long_as_the_longest_wave():
    t = Timeline(waves=_waves(("A", 40, 8), ("B", 30, 8)), sequencing="parallel")
    r = resolve_timeline(t, None, 3000, ["SA", "AE"])
    assert r.programme_weeks == 40 and all(r.wave_start_month(w) == 0 for w in r.waves)


def test_agent_sizes_only_undated_waves_and_is_clamped():
    t = Timeline(waves=_waves(("Wave 1", 44, 12), ("Wave 2", 0, 0)), sequencing="sequential",
                 hypercare_required=True)
    plan = WavePlan(phases=[WavePhasePlan(wave="Wave 1", phase_split={"Realize": 1}, total_weeks=10),
                            WavePhasePlan(wave="Wave 2", phase_split={}, total_weeks=500, hypercare_weeks=8)])
    r = resolve_timeline(t, plan, 3000, ["SA"])
    assert r.waves[0].total_weeks == 44 and r.waves[0].duration_source == "rfp"     # RFP wins
    assert r.waves[1].duration_source == "agent" and r.waves[1].total_weeks == 156   # clamped to max
    assert any("clamped" in n for n in r.notes)


def test_undated_programme_is_derived_from_effort_bands():
    r = resolve_timeline(None, None, 3500, ["SA"])
    assert len(r.waves) == 1 and r.waves[0].duration_source == "derived"
    assert r.waves[0].total_months >= estimate_duration_months(3500)
    assert r.waves[0].hypercare_weeks > 0                     # hypercare appended by default


def test_phase_split_from_the_plan_is_normalised():
    t = Timeline(waves=_waves(("Wave 1", 40, 8)))
    plan = WavePlan(phases=[WavePhasePlan(wave="Wave 1", phase_split={"Prepare": 10, "Explore": 20,
                                                                      "Realize": 50, "Deploy": 20})])
    r = resolve_timeline(t, plan, 1000, ["SA"])
    assert abs(sum(r.waves[0].phase_split.values()) - 1) < 1e-9 and r.waves[0].phase_split["Realize"] == 0.5


def test_effort_shares_from_allocations_size_derived_waves():
    t = Timeline(waves=_waves(("Wave 1", 0, 0), ("Wave 2", 0, 0)), sequencing="sequential")
    plan = WavePlan(allocations=[WaveAllocation(workstream="lob:Finance", shares={"Wave 1": 0.8, "Wave 2": 0.2})])
    r = resolve_timeline(t, plan, 9000, ["SA"])
    assert r.waves[0].total_weeks > r.waves[1].total_weeks
