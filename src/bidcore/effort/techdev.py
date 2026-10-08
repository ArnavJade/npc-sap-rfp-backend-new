"""Tech Dev Scope lines (RICEFW, custom Fiori, third-party integrations, residual interfaces) in PERSON-DAYS.

Ported from effort_calculator_layer4._write_tech_dev_scope_sheet, minus the sheet writing. The agents
supply counts (and, where the RFP states them, man-hours); every number on the sheet is derived here:
  * RICEFW - the RFP's own per-component rows when it lists them (stated hours per column, otherwise
    per-object policy hours x count), else the lump total split by the complexity percentages (the
    last bucket absorbs the rounding remainder); hours / hours_per_day;
  * Fiori - one aggregate row, always High complexity, per-app hours floored at the policy man-day
    minimum (scaled proportionally, keeping the column split);
  * third-party integrations - one row each; the agent's person-day total split by policy shares
    (already person-days: NOT divided by hours_per_day);
  * Interface - the RFP's interface total minus the integrations already priced above.
Each column is stored rounded to 2 dp, exactly as the sheet cell is written, so TechDevRow.total equals
the sheet's =SUM of the four cells.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from bidcore.effort.models import TechDevRow
from bidcore.ledger.sections_effort import Fiori, Integration, Ricefw
from bidcore.policy import Policy, get_policy

COLUMNS = ("development", "configuration", "unit_testing", "qa_testing")

_DEFAULT_LABELS = {
    "module": "All", "ricefw_name": "RICEFW", "ricefw_type": "WRICEF",
    "fiori_name": "Custom Fiori Applications", "fiori_type": "FIORI", "third_party_type": "Interface",
    "third_party_name": "3rd Party Integration Module {n}", "interface_name": "Interface",
    "interface_type": "Interface", "interface_complexity": "Medium",
}


def norm_complexity(raw: str | None) -> str:
    """Low / Medium / High from any spelling the RFP uses (Simple -> Low, Complex -> High); else Medium."""
    value = (raw or "").strip().lower()
    if value in ("simple", "low", "s", "l"):
        return "Low"
    if value in ("complex", "high", "c", "h"):
        return "High"
    return "Medium"


def split_counts(total: int, pcts: list[float]) -> list[int]:
    """`total` split by percentages; the last bucket absorbs the rounding remainder so counts sum to total."""
    counts: list[int] = []
    for i, pct in enumerate(pcts):
        if i < len(pcts) - 1:
            counts.append(int(round(total * (pct or 0.0) / 100.0)))
        else:
            counts.append(max(total - sum(counts), 0))
    return counts


def _num(value: object, default: float = 0.0) -> float:
    if value is None or (isinstance(value, str) and not value.strip()):
        return default
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _keyed(values: Mapping[str, float] | None) -> dict[str, float]:
    """Case/space-insensitive keys: {'Unit Testing': 4} -> {'unit_testing': 4}."""
    return {str(k).strip().lower().replace(" ", "_"): v for k, v in (values or {}).items()}


class _Rows:
    """Accumulates TechDevRows with the old writer's _emit arithmetic."""

    def __init__(self, labels: Mapping[str, str]):
        self.labels = labels
        self.rows: list[TechDevRow] = []

    def emit(self, row_id: str, source: str, name: str, object_type: str, count: int, complexity: str,
             efforts: Mapping[str, float], scale: float = 1.0, **interface: str) -> None:
        cells = {c: round(efforts[c] * scale, 2) for c in COLUMNS}
        self.rows.append(TechDevRow(row_id=row_id, source=source, module=self.labels["module"],
                                    object_name=name, object_type=object_type, no_of_objects=count,
                                    complexity=complexity, **cells, **interface))


def _ricefw_rows(out: _Rows, ricefw: Ricefw, td, scale: float) -> None:
    labels, hours = out.labels, td.per_object_hours
    number = 0
    if ricefw.rows:                                   # (a) the RFP's own component rows win outright
        for row in ricefw.rows:
            count = int(round(_num(row.no_of_objects)))
            if count <= 0:
                continue
            complexity = norm_complexity(row.complexity)
            stated = {c: getattr(row, c) for c in COLUMNS}
            efforts = {c: _num(stated[c]) if stated[c] is not None else hours[complexity][c] * count
                       for c in COLUMNS}
            number += 1
            out.emit(f"ricefw-{number}", "ricefw", labels["ricefw_name"],
                     row.object_type.strip() or labels["ricefw_type"], count, complexity, efforts, scale)
        return
    total = int(round(_num(ricefw.development_objects_total)))   # (b) lump total + complexity split
    if total <= 0:
        return
    buckets = td.ricefw_buckets
    split = _keyed(ricefw.complexity_split_pct)
    pcts = [_num(split.get(b["key"])) for b in buckets]
    if sum(pcts) <= 0:                                # a total with no usable split -> all Medium
        pcts = [100.0 if b["complexity"] == "Medium" else 0.0 for b in buckets]
    provided = ricefw.development_object_type.strip()
    types = list(td.default_object_types)
    for bucket, count in zip(buckets, split_counts(total, pcts)):
        if count <= 0:
            continue
        complexity = bucket["complexity"]
        efforts = {c: hours[complexity][c] * count for c in COLUMNS}
        object_type = provided or types[number % len(types)]     # cycle so rows read distinctly
        number += 1
        out.emit(f"ricefw-{number}", "ricefw", labels["ricefw_name"], object_type, count, complexity,
                 efforts, scale)


def _fiori_row(out: _Rows, fiori: Fiori, td, scale: float) -> None:
    count = max(int(round(_num(fiori.app_count))), len(fiori.app_names))
    if count <= 0:
        return
    default = td.per_object_hours["Fiori"]
    given = _keyed(fiori.per_app_hours)
    per_app = {c: _num(given.get(c), default[c]) for c in COLUMNS}
    per_app_hours = sum(per_app.values())
    floor = float(td.fiori["min_mandays_per_app"]) * td.hours_per_day
    if per_app_hours < floor:
        per_app = ({c: v * floor / per_app_hours for c, v in per_app.items()} if per_app_hours > 0
                   else {c: float(default[c]) for c in COLUMNS})
    out.emit("fiori", "fiori", out.labels["fiori_name"], out.labels["fiori_type"], count,
             td.fiori["complexity"], {c: per_app[c] * count for c in COLUMNS}, scale)


def compute_tech_dev(ricefw: Ricefw | None, fiori: Fiori | None, integrations: Iterable[Integration],
                     policy: Policy | None = None) -> list[TechDevRow]:
    """Tech Dev Scope rows in sheet order: RICEFW, Fiori, one per integration, Interface."""
    p = policy or get_policy()
    td = p.effort.tech_dev
    labels = {**_DEFAULT_LABELS, **(getattr(td, "labels", None) or {})}
    scale = 1.0 / float(td.hours_per_day)
    out = _Rows(labels)
    integrations = list(integrations or [])

    if ricefw is not None:
        _ricefw_rows(out, ricefw, td, scale)
    if fiori is not None:
        _fiori_row(out, fiori, td, scale)

    split = td.third_party_split
    for n, integration in enumerate(integrations, start=1):
        days = _num(integration.effort_days)
        out.emit(f"int:{integration.row_id}", "third_party",
                 integration.system.strip() or labels["third_party_name"].format(n=n),
                 labels["third_party_type"], 1, norm_complexity(integration.complexity),
                 {c: days * split[c] for c in COLUMNS},
                 middleware=integration.middleware.strip(), source_system=integration.source_system.strip(),
                 target_system=integration.target_system.strip())

    stated_interfaces = int(round(_num(ricefw.interface_total_count))) if ricefw is not None else 0
    residual = max(stated_interfaces - len(integrations), 0)
    if residual > 0:
        hours = td.per_object_hours["Interface"]
        out.emit("interface", "interface", labels["interface_name"], labels["interface_type"], residual,
                 labels["interface_complexity"], {c: hours[c] * residual for c in COLUMNS}, scale)
    return out.rows
