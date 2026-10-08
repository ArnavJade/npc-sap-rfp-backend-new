"""One wave's deterministic FTE grid (ported from resource_grid_layer4.py; the LLM grid is dropped).

Why it works this way:

* Phase bands. The wave's phase split (an input: the wave-planner agent decides it, the policy SAP
  Activate weights Prepare .08 / Explore .18 / Realize .50 / Deploy .14 are the default) is a set of
  RELATIVE weights laid over the wave's implementation months with a cursor, so a wave of any length
  gets the same shape. The trailing hypercare months are labelled with the policy hypercare phase
  (PGLS). The arithmetic is the old PHASE_WEIGHTS code, including Python's half-to-even `round`.
* Additive rows (programme roles, named PM-system leads) are staffed at their profile FTE across
  their activity window - a fraction of the implementation months.
* Distributive rows carry approved person-days of their entity (a LOB or a pooled block), spread by
  the same phase weights, so they reconcile to the approved figure by construction. Several rows
  sharing one entity split its days in proportion to their profile FTE (a 1.0-FTE consultants row
  and two 0.5-FTE sub-module leads: the consultants carry half), never giving each the whole.
* Every row keeps a reduced tail through the hypercare months (policy PGLS retention), because the
  team ramps down at go-live rather than vanishing.
* Rounding to the FTE grain happens LAST, after every cell is sized, so a rounded figure is never
  scaled again and pushed off-grain.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Mapping, Sequence

from bidcore.policy import Policy, get_policy
from bidcore.resourcing.models import GridCell, GridRow, RoleSpec, WaveResourceGrid, WaveSpec
from bidcore.resourcing.roles import sort_rows
from bidcore.resourcing.rounding import quantize_grid

logger = logging.getLogger(__name__)


def implementation_months(wave: WaveSpec) -> int:
    """Implementation months of a wave: at least one, hypercare never takes the whole wave."""
    total = max(int(wave.total_months or 0), 1)
    return total - min(max(int(wave.hypercare_months or 0), 0), total - 1)


def phase_weights(wave: WaveSpec | None = None, policy: Policy | None = None) -> list[tuple[str, float]]:
    """(phase, relative weight) in policy phase order.

    The wave's own split when it carries a usable one (keys matched case-insensitively, phases it
    omits weigh 0, negatives count as 0); otherwise - empty, unknown phases only, or nothing positive
    - the policy default. Weights are NOT normalised here: the cursor divides by their sum, exactly
    as the old PHASE_WEIGHTS (which summed to 0.90) were used."""
    default = (policy or get_policy()).resourcing.default_phase_split
    given = dict(wave.phase_split) if wave is not None else {}
    if given:
        by_key = {str(k).strip().casefold(): v for k, v in given.items()}
        unknown = set(by_key) - {phase.casefold() for phase in default}
        if unknown:
            logger.warning("resourcing: %s phase split names unknown phase(s) %s; ignored",
                           getattr(wave, "name", "?"), sorted(unknown))
        custom = [(phase, max(float(by_key.get(phase.casefold(), 0.0) or 0.0), 0.0)) for phase in default]
        if sum(weight for _, weight in custom) > 0:
            return custom
        logger.warning("resourcing: %s phase split has no positive weight; using the policy default",
                       getattr(wave, "name", "?"))
    return [(phase, float(weight)) for phase, weight in default.items()]


def phase_bands_for_wave(wave: WaveSpec, policy: Policy | None = None) -> list[str]:
    """One phase label per month of the wave; the trailing hypercare months carry the PGLS label."""
    policy = policy or get_policy()
    total_months = max(int(wave.total_months or 0), 1)
    impl_months = implementation_months(wave)
    weights = phase_weights(wave, policy)
    weight_sum = sum(weight for _, weight in weights) or 1.0

    bands: list[str] = []
    cursor = 0.0
    for name, weight in weights:
        cursor += impl_months * (weight / weight_sum)
        while len(bands) < min(round(cursor), impl_months):
            bands.append(name)
    while len(bands) < impl_months:
        bands.append(weights[-1][0])
    bands = bands[:impl_months]
    bands.extend([policy.resourcing.hypercare_phase] * (total_months - impl_months))
    return bands


def window_months(bands: Sequence[str], window: tuple[float, float], policy: Policy | None = None) -> list[int]:
    """1-based implementation months inside a role's activity window (fractions of the implementation
    months, start inclusive). Hypercare months are excluded: retention handles them."""
    hypercare = (policy or get_policy()).resourcing.hypercare_phase
    impl = [i + 1 for i, band in enumerate(bands) if band != hypercare]
    if not impl:
        return []
    start_fraction, end_fraction = window
    count = len(impl)
    start = int(start_fraction * count)
    end = max(int(round(end_fraction * count)), start + 1)
    return impl[start:end]


def distributive_month_weights(
    bands: Sequence[str],
    phase_split: Mapping[str, float] | Sequence[tuple[str, float]],
    policy: Policy | None = None,
) -> dict[int, float]:
    """Normalised per-month share of a distributive row's man-months: each implementation month gets
    its phase's weight divided by that phase's month count (flat spread when nothing weighs)."""
    hypercare = (policy or get_policy()).resourcing.hypercare_phase
    per_phase = dict(phase_split)
    counts = Counter(band for band in bands if band != hypercare)
    raw = {index: per_phase.get(band, 0.0) / counts.get(band, 1)
           for index, band in enumerate(bands, start=1) if band != hypercare}
    total = sum(raw.values())
    if total <= 0:
        return {index: 1.0 / len(raw) for index in raw} if raw else {}
    return {index: value / total for index, value in raw.items()}


def implementation_man_months(row: GridRow, policy: Policy | None = None) -> float:
    """A row's man-months excluding its hypercare months: the figure that ties to approved effort."""
    hypercare = (policy or get_policy()).resourcing.hypercare_phase
    return sum(cell.fte for cell in row.cells if cell.phase != hypercare)


def derive_resource_grid(
    wave: WaveSpec,
    roles: Sequence[RoleSpec],
    approved: Mapping[str, float] | None = None,
    policy: Policy | None = None,
) -> WaveResourceGrid:
    """The deterministic FTE grid for one wave. Always succeeds.

    `approved` maps a distributive entity (cleaned LOB name or pool name) to the person-days this wave
    delivers for it. A distributive role whose entity has no approved days contributes no row."""
    policy = policy or get_policy()
    res = policy.resourcing
    days_per_month = policy.commercials.working_days_per_month
    approved = approved or {}
    bands = phase_bands_for_wave(wave, policy)
    grid = WaveResourceGrid(wave_name=wave.name, months=len(bands), start_month=wave.start_month,
                            phase_bands=bands)

    impl_indices = [i + 1 for i, band in enumerate(bands) if band != res.hypercare_phase]
    pgls_indices = [i + 1 for i, band in enumerate(bands) if band == res.hypercare_phase]
    month_weights = distributive_month_weights(bands, phase_weights(wave, policy), policy)

    # Rows sharing one entity's approved days divide them by profile FTE.
    carriers: Counter[str] = Counter()
    carrier_fte: dict[str, float] = {}
    for spec in roles:
        if spec.contribution == "distributive":
            carriers[spec.entity_name] += 1
            carrier_fte[spec.entity_name] = carrier_fte.get(spec.entity_name, 0.0) + max(spec.fte, 0.0)

    def carrier_share(spec: RoleSpec) -> float:
        total_fte = carrier_fte.get(spec.entity_name, 0.0)
        if total_fte <= 0:
            return 1.0 / max(carriers.get(spec.entity_name, 1), 1)
        return max(spec.fte, 0.0) / total_fte

    for spec in roles:
        cells: list[GridCell] = []
        if spec.contribution == "distributive":
            days = float(approved.get(spec.entity_name, 0.0) or 0.0) * carrier_share(spec)
            man_months = days / days_per_month if days_per_month else 0.0
            if man_months <= 0:
                logger.debug("resourcing: %s has no approved effort in %s; row omitted", spec.role_title, wave.name)
                continue
            for index in impl_indices:
                share = month_weights.get(index, 0.0)
                if share > 0:
                    cells.append(GridCell(month_index=index, phase=bands[index - 1], fte=round(man_months * share, 3)))
            retention = res.pgls_retention["distributive"]
        else:
            for index in window_months(bands, spec.window, policy):
                cells.append(GridCell(month_index=index, phase=bands[index - 1], fte=round(spec.fte, 3)))
            retention = res.pgls_retention["additive"]

        if pgls_indices and cells:
            tail_fte = max(cell.fte for cell in cells) * retention
            if tail_fte > 0:
                cells.extend(GridCell(month_index=index, phase=res.hypercare_phase, fte=round(tail_fte, 3))
                             for index in pgls_indices)
        if not cells:
            continue
        row = GridRow(role_title=spec.role_title, location=spec.location, entity_kind=spec.entity_kind,
                      entity_name=spec.entity_name, contribution=spec.contribution, cells=cells)
        row.recompute_total()
        grid.rows.append(row)

    sort_rows(grid)
    quantize_grid(grid, res.fte_grain)
    logger.info("resourcing: grid for %s -> %d row(s) over %d month(s), %.2f man-months",
                wave.name, len(grid.rows), grid.months, grid.grand_total_mm)
    return grid
