"""Resolve the programme timeline: every wave gets a duration, a hypercare tail and a phase split.

Ported from project_timeline_extraction_layer.py (sanitiser clamps, derive_timeline_from_effort,
_deterministic_wave_weeks, _apply_wave_weeks, estimate_duration_months, classify_programme_shape).
The LLM duration call is gone: the wave-planner agent may size an undated wave in the ledger
(wave_plan.phases), with a reason. Precedence per wave:
  1. RFP-stated duration (ledger total_weeks > 0)                              -> 'rfp'
  2. wave_plan.phases[wave].total_weeks (+ its hypercare_weeks when given)     -> 'agent'
  3. band sizing on the programme's effort                                     -> 'derived'
     sequential waves share ONE programme-length band in proportion to their effort; parallel waves
     are each sized from their own effort (the programme is as long as the longest). Only the build
     is sized; the wave's hypercare tail is appended; the build never drops below min implementation
     weeks. A wave's effort share is its share in the wave-plan allocations - each allocation's shares
     normalised over the known waves, then averaged weighted by that workstream's person-days when
     `workstream_effort` is given (equally otherwise) - else an equal share.
Agent and derived durations are clamped to [min_wave_weeks, max_wave_weeks]; a sized total too short
to hold its hypercare is raised to hypercare + min_wave_weeks. Every fallback is one line in `notes`.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from bidcore.ledger.sections_effort import Timeline, Wave, WavePhasePlan, WavePlan
from bidcore.policy import Policy, get_policy
from bidcore.timeline.model import ResolvedTimeline, ResolvedWave, weeks_for

SHAPE_1C1W, SHAPE_1CNW, SHAPE_NC1W, SHAPE_NCNW = "1C1W", "1CNW", "NC1W", "NCNW"
SEQUENCINGS = ("sequential", "parallel", "staggered")
# The wave a wave-less timeline gets; the wave_plan validator resolves the same default name.
DERIVED_WAVE_NAME: str = Wave.model_fields["name"].default


def classify_programme_shape(country_count: int, wave_count: int) -> str:
    """1C1W | 1CNW | NC1W | NCNW from the two counts that define the shape."""
    multi_country = (country_count or 0) > 1
    multi_wave = (wave_count or 0) > 1
    if multi_country:
        return SHAPE_NCNW if multi_wave else SHAPE_NC1W
    return SHAPE_1CNW if multi_wave else SHAPE_1C1W


def estimate_duration_months(total_effort: float, policy: Policy | None = None) -> int:
    """Banded end-to-end duration (months) from approved person-days; indicative only."""
    t = (policy or get_policy()).timeline
    if not total_effort:
        return int(t.duration_no_effort_months)
    for threshold, months in t.duration_bands:
        if total_effort < threshold:
            return int(months)
    return int(t.duration_above_bands_months)


def _fold(name: object) -> str:
    return str(name or "").strip().casefold()


def _fold_workstream(key: object) -> str:
    prefix, sep, rest = str(key or "").partition(":")
    return f"{prefix.strip().lower()}:{rest.strip().casefold()}" if sep else prefix.strip().lower()


def _ledger_waves(timeline: Timeline | None, max_waves: int, notes: list[str]) -> list[Wave]:
    waves = list(timeline.waves) if timeline else []
    if len(waves) > max_waves:
        notes.append(f"{len(waves)} waves in the ledger; only the first {max_waves} are kept")
        waves = waves[:max_waves]
    return sorted(waves, key=lambda w: w.sequence)            # stable: ties keep ledger order


def _unique_names(waves: list[Wave], notes: list[str]) -> list[str]:
    names: list[str] = []
    for i, wave in enumerate(waves):
        name = wave.name.strip() or f"Wave {i + 1}"
        base, n = name, 2
        while _fold(name) in {_fold(x) for x in names}:
            name, n = f"{base} ({n})", n + 1
        if name != wave.name:
            notes.append(f"wave '{wave.name}' renamed '{name}' (names must be present and unique)")
        names.append(name)
    return names


def _effort_shares(names: list[str], wave_plan: WavePlan | None,
                   workstream_effort: Mapping[str, float] | None, notes: list[str]) -> list[float] | None:
    """Each wave's share of the programme effort per the wave-plan allocations, or None."""
    allocations = list(wave_plan.allocations) if wave_plan else []
    index = {_fold(n): i for i, n in enumerate(names)}
    efforts = None if workstream_effort is None else {
        _fold_workstream(k): float(v or 0.0) for k, v in workstream_effort.items()}
    acc, weight_total, used = [0.0] * len(names), 0.0, 0
    for allocation in allocations:
        shares = [0.0] * len(names)
        for wave, share in allocation.shares.items():
            i = index.get(_fold(wave))
            if i is not None and share and share > 0:
                shares[i] += float(share)
        weight = 1.0 if efforts is None else max(efforts.get(_fold_workstream(allocation.workstream), 0.0), 0.0)
        if sum(shares) <= 0 or weight <= 0:
            continue
        used += 1
        weight_total += weight
        acc = [a + weight * s / sum(shares) for a, s in zip(acc, shares)]
    if weight_total <= 0:
        return None
    basis = "weighted by workstream effort" if efforts is not None else "weighted equally"
    notes.append(f"undated waves sized on effort shares from {used} wave-plan allocation(s), {basis}")
    return [a / weight_total for a in acc]


def _phase_split(given: Mapping[str, float] | None, default: Mapping[str, float], name: str,
                 notes: list[str]) -> dict[str, float]:
    """The plan's split over the policy phases, normalised. Unknown keys are ignored; a phase missing
    or non-positive takes its policy default, rescaled to the plan's own scale (percent or fraction)."""
    lookup = {_fold(k): v for k, v in (given or {}).items()}
    picked = {ph: float(lookup[_fold(ph)]) for ph in default
              if isinstance(lookup.get(_fold(ph)), (int, float)) and lookup[_fold(ph)] > 0}
    if not picked:
        if given:
            notes.append(f"{name}: wave-plan phase split has no usable phase; policy default used")
        weights = dict(default)
    else:
        scale = sum(picked.values()) / (sum(default[ph] for ph in picked) or 1.0)
        missing = [ph for ph in default if ph not in picked]
        if missing:
            notes.append(f"{name}: phase split misses {', '.join(missing)}; policy default weight used")
        weights = {ph: picked.get(ph, default[ph] * scale) for ph in default}
    total = sum(weights.values())
    return {ph: (w / total if total > 0 else 1.0 / len(weights)) for ph, w in weights.items()}


def _clamp_sized(total: float, hypercare: float, name: str, t, notes: list[str], what: str) -> float:
    """_apply_wave_weeks: clamp a proposed (agent / derived) total; hypercare sits inside it."""
    clamped = round(min(max(float(total), t.min_wave_weeks), t.max_wave_weeks), 2)
    if what == "wave plan" and clamped != round(float(total), 2):
        notes.append(f"{name}: wave-plan duration {total:g} weeks clamped to {clamped:g}")
    if hypercare > clamped:
        clamped = round(hypercare + t.min_wave_weeks, 2)
        notes.append(f"{name}: {what} duration cannot hold {hypercare:g} weeks hypercare; raised to {clamped:g}")
    return clamped


def resolve_timeline(timeline: Timeline | None, wave_plan: WavePlan | None, sizing_effort: float,
                     countries: Iterable[str], policy: Policy | None = None, *,
                     workstream_effort: Mapping[str, float] | None = None) -> ResolvedTimeline:
    """Every wave dated, with hypercare and phase split settled (see module docstring for precedence).

    `sizing_effort` is the implementation-scope person-days (catalogue + non-catalogue + third-party
    integrations, the old prepare_timeline rule). `workstream_effort` (optional, keys as in
    WaveAllocation.workstream) weights the allocations when deriving undated waves.
    """
    p = policy or get_policy()
    t = p.timeline
    notes: list[str] = []
    ledger_waves = _ledger_waves(timeline, int(t.max_waves), notes)
    derived_programme = not ledger_waves
    if derived_programme:
        notes.append("no waves in the ledger timeline" if timeline else "no ledger timeline")
        ledger_waves = [Wave(name=DERIVED_WAVE_NAME)]
    # A missing timeline section falls back like the old derived timeline: hypercare appended.
    hypercare_required = timeline.hypercare_required if timeline else True
    names = _unique_names(ledger_waves, notes)
    n = len(ledger_waves)

    sequencing = timeline.sequencing if timeline and timeline.sequencing in SEQUENCINGS else t.default_sequencing
    if not timeline:
        notes.append(f"sequencing not stated; policy default '{sequencing}'")
    if n == 1 and sequencing != "parallel":
        notes.append(f"single wave: sequencing '{sequencing}' treated as parallel")
        sequencing = "parallel"

    plans: dict[str, WavePhasePlan] = {}
    for plan in (wave_plan.phases if wave_plan else []):
        if _fold(plan.wave) in {_fold(x) for x in names}:
            plans[_fold(plan.wave)] = plan
        else:
            notes.append(f"wave-plan phases name unknown wave '{plan.wave}'; ignored")

    default_split = dict(p.resourcing.default_phase_split)
    shares: list[float] | None = None
    shares_ready = False
    resolved: list[ResolvedWave] = []
    for i, (wave, name) in enumerate(zip(ledger_waves, names)):
        plan = plans.get(_fold(name))
        stated = float(wave.total_weeks or 0.0)
        if stated > t.max_plausible_weeks or stated < 0:
            notes.append(f"{name}: stated {stated:g} weeks is outside 0-{t.max_plausible_weeks:g}; treated as undated")
            stated = 0.0
        ledger_hc = max(float(wave.hypercare_weeks or 0.0), 0.0)

        if stated > 0:                                           # 1. the RFP dates it
            source, total, hypercare = "rfp", round(stated, 2), ledger_hc
            if hypercare > total:
                notes.append(f"{name}: hypercare {hypercare:g} weeks exceeds the stated {total:g}; clamped")
                hypercare = total
            if plan and (plan.total_weeks or plan.hypercare_weeks is not None):
                notes.append(f"{name}: wave-plan duration/hypercare ignored; the RFP states {total:g} weeks")
        else:
            if plan and plan.hypercare_weeks is not None:
                hypercare = max(float(plan.hypercare_weeks), 0.0)
            elif ledger_hc > 0:
                hypercare = ledger_hc
            elif hypercare_required:
                hypercare = float(t.default_hypercare_weeks)
                notes.append(f"{name}: hypercare required but not stated; policy default {hypercare:g} weeks")
            else:
                hypercare = 0.0
            if plan and plan.total_weeks and plan.total_weeks > 0:   # 2. the wave-planner sized it
                source = "agent"
                total = _clamp_sized(plan.total_weeks, hypercare, name, t, notes, "wave plan")
            else:                                                # 3. band sizing
                if not shares_ready and n > 1:
                    shares = _effort_shares(names, wave_plan, workstream_effort, notes)
                    if shares is None:
                        notes.append("no usable wave-plan allocations; undated waves take equal effort shares")
                shares_ready = True
                source = "derived"
                build = _derived_build_weeks(i, n, shares, sizing_effort, sequencing == "sequential", p)
                total = _clamp_sized(round(build + hypercare, 1), hypercare, name, t, notes, "derived")
                notes.append(f"{name}: no stated or planned duration; derived {total:g} weeks "
                             f"({build:.1f} build + {hypercare:g} hypercare) from {sizing_effort:g} PD")

        resolved.append(ResolvedWave(
            name=name, sequence=wave.sequence, total_weeks=total, hypercare_weeks=round(hypercare, 2),
            duration_source=source,
            phase_split=_phase_split(plan.phase_split if plan else None, default_split, name, notes),
            countries=list(wave.countries), lobs=list(wave.lobs), kind=wave.kind,
            partition_axis=wave.partition_axis, go_live=wave.go_live, start=wave.start,
            unit_ids=list(wave.unit_ids),
        ))

    distinct = {_fold(c) for c in countries or () if str(c or "").strip()}
    shape = classify_programme_shape(len(distinct), n) if distinct else ""
    if not distinct:
        notes.append("no countries given; programme shape left unset")
    mode = timeline.hypercare_mode if timeline else "none"
    if not any(w.hypercare_weeks > 0 for w in resolved):
        mode = "none"
    elif mode == "none":
        mode = "appended"                  # hypercare the RFP did not state was added to a sized build
    return ResolvedTimeline(
        waves=resolved, sequencing=sequencing, hypercare_mode=mode,
        source="derived" if derived_programme else (timeline.source if timeline else "derived"),
        shape=shape, notes=notes,
    )


def _derived_build_weeks(index: int, count: int, shares: list[float] | None, sizing_effort: float,
                         sequential: bool, policy: Policy) -> float:
    """_deterministic_wave_weeks for one undated wave: its BUILD weeks (hypercare is added by the caller)."""
    t = policy.timeline
    share = shares[index] if shares else 1.0 / max(count, 1)
    if sequential:
        programme = weeks_for(estimate_duration_months(sizing_effort, policy), t.weeks_per_month)
        build = programme * share
    else:
        effort = (share * sizing_effort if shares else 0.0) or (sizing_effort / max(count, 1) if sizing_effort else 0.0)
        build = weeks_for(estimate_duration_months(effort, policy), t.weeks_per_month)
    return max(build, t.min_implementation_weeks)
