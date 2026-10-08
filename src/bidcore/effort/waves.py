"""Per-wave effort: which wave delivers which person-days, and the per-pass weights the rebalance uses.

Replaces the old heuristic attribution (wave_attribution_layer4.build_attribution: ISO ownership,
template-vs-rollout factors, technical-wave rules). The wave-planner agent now DECIDES the split, in
the ledger (wave_plan.allocations / item_tags); this module only does the arithmetic, keeping the old
module's two guarantees:
  * conservation - every workstream is split by largest remainder at the policy grain (0.01 PD), so
    its waves sum to its total exactly; no person-day is unassigned;
  * graceful fallback - a workstream with effort but no usable allocation is spread by implementation
    weeks (the old _duration_weights / resource_grid_layer4._split_approved_by_wave rule) and flagged.
Precedence: (a) a catalogue line tagged to a wave goes wholly to it; (b) each workstream's remaining
effort follows its allocation's shares (normalised; unknown waves ignored and flagged); (c) no
allocation -> implementation-week share, flagged; (d) a single wave takes everything.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from pydantic import BaseModel, Field

from bidcore.effort.models import EffortModel
from bidcore.effort.workstreams import workstream_totals
from bidcore.ledger.sections_effort import WavePlan
from bidcore.policy import Policy, get_policy
from bidcore.resourcing.models import PassWeights
from bidcore.timeline.model import ResolvedTimeline, ResolvedWave

LOB_PREFIX = "lob:"
CATEGORY_WORKSTREAMS = ("data_migration", "basis", "security", "analytics")


class WaveEffort(BaseModel):
    """Person-days per wave; every list is in timeline wave order. Dicts hold positive amounts only.

    lob:      LOB -> PD                      pools:    pool title (policy resourcing.pools) -> PD
    tech_dev: Tech Dev PD excluding the third-party rows (those are the 'Third Party Integrations' pool)
    category: category-consultant title (policy resourcing.category_consultants) -> PD
    source:   wave -> 'plan' | 'tagged' | 'duration' (how its figures were decided)
    """
    wave_names: list[str] = Field(default_factory=list)
    lob: list[dict[str, float]] = Field(default_factory=list)
    pools: list[dict[str, float]] = Field(default_factory=list)
    tech_dev: list[float] = Field(default_factory=list)
    category: list[dict[str, float]] = Field(default_factory=list)
    source: dict[str, str] = Field(default_factory=dict)
    flags: list[str] = Field(default_factory=list)

    def wave_total(self, i: int) -> float:
        return round(sum(self.lob[i].values()) + sum(self.pools[i].values()) + self.tech_dev[i]
                     + sum(self.category[i].values()), 2)


def allocate(total: float, weights: Sequence[float], grain: float = 0.01) -> list[float]:
    """Split `total` across `weights` so the parts sum to `total` exactly (largest remainder at `grain`)."""
    if not weights:
        return []
    weight_total = sum(w for w in weights if w > 0)
    if total <= 0 or weight_total <= 0:
        return [0.0] * len(weights)
    grains_total = int(round(total / grain))
    exact = [(max(w, 0.0) / weight_total) * grains_total for w in weights]
    floors = [int(value) for value in exact]
    remainder = grains_total - sum(floors)
    if remainder > 0:
        order = sorted(range(len(weights)), key=lambda i: (exact[i] - floors[i], weights[i]), reverse=True)
        for i in order[:remainder]:
            floors[i] += 1
    return [round(grains * grain, 2) for grains in floors]


def normalise(weights: Sequence[float]) -> list[float]:
    """Shares summing to 1; all-zero -> equal shares."""
    total = sum(w for w in weights if w > 0)
    if total <= 0:
        return [1.0 / len(weights)] * len(weights) if weights else []
    return [max(w, 0.0) / total for w in weights]


def duration_weights(waves: Sequence[ResolvedWave]) -> list[float]:
    """Each wave's share of the implementation weeks (hypercare is a support tail, not build capacity)."""
    return normalise([w.implementation_weeks for w in waves])


def sizing_effort(effort: EffortModel) -> float:
    """Implementation-scope person-days the programme is sized on (old prepare_timeline): catalogue +
    non-catalogue tools + third-party integrations; hypercare and programme roles are excluded."""
    return round(effort.core_bp_effort + effort.non_catalogue_effort + effort.third_party_effort, 2)


def workstream_effort_totals(effort: EffortModel, policy: Policy | None = None) -> dict[str, float]:
    """Person-days per wave-plan workstream key ('lob:<LOB>', integrations, non_catalogue, tech_dev, ...)."""
    totals = {f"{LOB_PREFIX}{lob}": module.total_effort for lob, module in effort.modules.items()}
    totals["integrations"] = effort.third_party_effort
    totals["non_catalogue"] = effort.non_catalogue_effort
    totals["tech_dev"] = round(sum(r.total for r in effort.tech_dev if r.source != "third_party"), 2)
    totals.update({k: round(v, 2) for k, v in workstream_totals(effort.workstreams, policy).items()})
    return totals


def _fold(name: object) -> str:
    return str(name or "").strip().casefold()


def _fold_workstream(key: object) -> str:
    prefix, sep, rest = str(key or "").partition(":")
    return f"{prefix.strip().lower()}:{rest.strip().casefold()}" if sep else prefix.strip().lower()


def _plan_weights(wave_plan: WavePlan | None, totals: Mapping[str, float], index: Mapping[str, int],
                  flags: list[str]) -> dict[str, list[float]]:
    """Workstream -> normalised per-wave shares from the plan's allocations (the last one wins)."""
    keys = {_fold_workstream(k): k for k in totals}
    out: dict[str, list[float]] = {}
    for allocation in (wave_plan.allocations if wave_plan else []):
        key = keys.get(_fold_workstream(allocation.workstream))
        if key is None:
            flags.append(f"allocation for unknown workstream '{allocation.workstream}' ignored")
            continue
        weights, unknown = [0.0] * len(index), []
        for wave, share in allocation.shares.items():
            i = index.get(_fold(wave))
            if i is None:
                unknown.append(str(wave))
            elif share and share > 0:
                weights[i] += float(share)
        if unknown:
            flags.append(f"{key}: allocation names unknown wave(s) {', '.join(unknown)}; ignored")
        total = sum(weights)
        if total <= 0:
            flags.append(f"{key}: allocation has no positive share for a known wave; ignored")
            continue
        if abs(total - 1.0) > 0.01:
            flags.append(f"{key}: allocation shares sum to {total:.2f}; normalised")
        if key in out:
            flags.append(f"{key}: allocated more than once; the last allocation is used")
        out[key] = [w / total for w in weights]
    return out


def allocate_waves(effort: EffortModel, timeline: ResolvedTimeline, wave_plan: WavePlan | None,
                   policy: Policy | None = None) -> tuple[WaveEffort, PassWeights]:
    """Split every workstream's effort across the waves and derive the rebalance's per-pass weights."""
    p = policy or get_policy()
    waves = list(timeline.waves)
    names, n = [w.name for w in waves], len(waves)
    if n == 0:
        return WaveEffort(flags=["the timeline has no waves; nothing allocated"]), PassWeights()
    grain = float((getattr(p.effort, "wave_allocation", None) or {}).get("grain_days", 0.01))
    pools, titles = p.resourcing.pools, p.resourcing.category_consultants
    index = {_fold(name): i for i, name in enumerate(names)}
    flags: list[str] = []
    totals = workstream_effort_totals(effort, p)

    # (a) catalogue lines tagged to a wave (agent item tags or reviewer edits)
    tagged: dict[str, list[float]] = {}
    unknown_tags: dict[str, int] = {}
    for lob, module in effort.modules.items():
        for row in module.rows:
            tag = row.wave.strip()
            if not tag:
                continue
            i = index.get(_fold(tag))
            if i is None:
                unknown_tags[tag] = unknown_tags.get(tag, 0) + 1
                continue
            bucket = tagged.setdefault(f"{LOB_PREFIX}{lob}", [0.0] * n)
            bucket[i] += row.total
    for tag, count in unknown_tags.items():
        flags.append(f"{count} line(s) tagged to unknown wave '{tag}'; spread with their LOB instead")

    plan = _plan_weights(wave_plan, totals, index, flags) if n > 1 else {}
    if n > 1 and not plan:
        flags.append("no usable wave-plan allocations; every workstream spread by implementation weeks")
    by_duration = duration_weights(waves)

    per_ws: dict[str, list[float]] = {}
    got: dict[str, set[int]] = {"plan": set(), "tagged": set(), "duration": set()}
    for ws, total in totals.items():
        direct = [round(x, 2) for x in tagged.get(ws, [0.0] * n)]
        remaining = max(round(total - sum(direct), 2), 0.0)
        if n == 1:                                           # (d)
            weights, how = [1.0], "plan"
        elif ws in plan:                                     # (b)
            weights, how = plan[ws], "plan"
        else:                                                # (c)
            weights, how = by_duration, "duration"
            if remaining > 0 and plan:
                flags.append(f"{ws}: {remaining:g} PD has no wave-plan allocation; spread by implementation weeks")
        parts = allocate(remaining, weights, grain)
        per_ws[ws] = [round(d + q, 2) for d, q in zip(direct, parts)]
        got["tagged"].update(i for i in range(n) if direct[i] > 0)
        got[how].update(i for i in range(n) if parts[i] > 0)

    lob_keys = [(lob, f"{LOB_PREFIX}{lob}") for lob in effort.modules]
    pool_keys = [(pools["third_party"], "integrations"), (pools["non_catalogue"], "non_catalogue")]
    category_keys = [(titles[k], k) for k in CATEGORY_WORKSTREAMS]

    def positive(pairs: list[tuple[str, str]], i: int) -> dict[str, float]:
        return {label: per_ws[key][i] for label, key in pairs if per_ws[key][i] > 0}

    result = WaveEffort(
        wave_names=names,
        lob=[positive(lob_keys, i) for i in range(n)],
        pools=[positive(pool_keys, i) for i in range(n)],
        tech_dev=list(per_ws["tech_dev"]),
        category=[positive(category_keys, i) for i in range(n)],
        source={name: next((s for s in ("duration", "plan", "tagged") if i in got[s]), "plan")
                for i, name in enumerate(names)},
        flags=flags,
    )

    build = normalise([result.wave_total(i) for i in range(n)])
    in_hypercare = [b if w.hypercare_weeks > 0 else 0.0 for b, w in zip(build, waves)]
    weights = PassWeights(
        build=build, mgmt=list(build), fp_gl=list(build),
        hypercare=normalise(in_hypercare) if sum(in_hypercare) > 0 else list(build),
        category={titles[k]: normalise(per_ws[k]) for k in CATEGORY_WORKSTREAMS},
    )
    return result, weights
