"""Resource plan models (ported from resource_grid_layer4.py) and the inputs the plan is built from.

Every row carries a `contribution`:
  * distributive - redistributes effort the catalogue already approved (consultants, leads of a LOB);
    changes no total;
  * additive     - a role the rate card does not price at all (programme roles, specialist category
    consultants); its man-months enter the totals.
Hypercare (the trailing PGLS months of each wave) is priced at its own onsite/offshore rates.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

ONSITE = "Onsite"
OFFSHORE = "Offshore"
PGLS = "PGLS"


class GridCell(BaseModel):
    month_index: int                  # 1-based within the wave
    phase: str                        # Prepare | Explore | Realize | Deploy | PGLS
    fte: float = 0.0


class GridRow(BaseModel):
    role_title: str
    location: str = ONSITE
    entity_kind: str = "programme"    # programme|lob|submodule|non_catalogue|third_party|technical
    entity_name: str = ""
    contribution: str = "additive"    # additive | distributive
    cells: list[GridCell] = Field(default_factory=list)
    total_man_months: float = 0.0

    def recompute_total(self) -> float:
        self.total_man_months = round(sum(c.fte for c in self.cells), 2)
        return self.total_man_months

    def fte_at(self, month_index: int) -> float:
        for cell in self.cells:
            if cell.month_index == month_index:
                return cell.fte
        return 0.0


class WaveResourceGrid(BaseModel):
    wave_name: str = "Wave 1"
    months: int = 0
    start_month: int = 0              # 0-based month on the programme calendar
    phase_bands: list[str] = Field(default_factory=list)
    rows: list[GridRow] = Field(default_factory=list)
    onsite_total_by_month: list[float] = Field(default_factory=list)
    offshore_total_by_month: list[float] = Field(default_factory=list)
    grand_total_by_month: list[float] = Field(default_factory=list)
    onsite_total_mm: float = 0.0
    offshore_total_mm: float = 0.0
    grand_total_mm: float = 0.0

    def recompute_totals(self) -> None:
        onsite = [0.0] * self.months
        offshore = [0.0] * self.months
        for row in self.rows:
            row.recompute_total()
            bucket = onsite if row.location == ONSITE else offshore
            for cell in row.cells:
                if 1 <= cell.month_index <= self.months:
                    bucket[cell.month_index - 1] += cell.fte
        self.onsite_total_by_month = [round(v, 2) for v in onsite]
        self.offshore_total_by_month = [round(v, 2) for v in offshore]
        self.grand_total_by_month = [round(a + b, 2) for a, b in zip(onsite, offshore)]
        self.onsite_total_mm = round(sum(onsite), 2)
        self.offshore_total_mm = round(sum(offshore), 2)
        self.grand_total_mm = round(self.onsite_total_mm + self.offshore_total_mm, 2)


class ResourcePlan(BaseModel):
    grids: list[WaveResourceGrid] = Field(default_factory=list)
    additive_effort_days: float = 0.0
    additive_cost_usd: float = 0.0
    hypercare_effort_days: float = 0.0
    hypercare_onsite_cost_usd: float = 0.0
    hypercare_offshore_cost_usd: float = 0.0
    source: str = "derived"

    @property
    def hypercare_cost_usd(self) -> float:
        return round(self.hypercare_onsite_cost_usd + self.hypercare_offshore_cost_usd, 2)

    @property
    def grand_total_mm(self) -> float:
        return round(sum(g.grand_total_mm for g in self.grids), 2)

    @property
    def programme_months(self) -> int:
        return max((g.start_month + g.months for g in self.grids), default=0)

    @property
    def combined_by_month(self) -> list[float]:
        """Total FTE on the programme in each calendar month, across all waves."""
        span = self.programme_months
        combined = [0.0] * span
        for grid in self.grids:
            for index, value in enumerate(grid.grand_total_by_month):
                slot = grid.start_month + index
                if 0 <= slot < span:
                    combined[slot] += value
        return [round(v, 2) for v in combined]

    @property
    def peak_fte(self) -> float:
        return max(self.combined_by_month, default=0.0)


class RoleSpec(BaseModel):
    """One role a grid must contain (deterministic roster)."""
    role_title: str
    location: str = ONSITE
    entity_kind: str = "programme"
    entity_name: str = ""
    contribution: str = "additive"
    fte: float = 1.0
    window: tuple[float, float] = (0.0, 1.0)
    entity_effort_days: float = 0.0

    @property
    def key(self) -> str:
        return f"{self.role_title}||{self.location}"


# ---------------------------------------------------------------------------- inputs (contract)
class WaveSpec(BaseModel):
    """What resourcing needs to know about one wave (built by bidcore.timeline from the ledger)."""
    name: str
    total_months: int
    hypercare_months: int
    start_month: int = 0
    phase_split: dict[str, float] = Field(default_factory=dict)   # relative Prepare/Explore/Realize/Deploy


class PassWeights(BaseModel):
    """Per-wave shares (wave order) for each rebalance pass, from the wave plan. Each list sums to 1."""
    build: list[float] = Field(default_factory=list)
    mgmt: list[float] = Field(default_factory=list)
    fp_gl: list[float] = Field(default_factory=list)
    hypercare: list[float] = Field(default_factory=list)
    category: dict[str, list[float]] = Field(default_factory=dict)   # category consultant title -> shares
