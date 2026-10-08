"""Resolved programme timeline: the ledger's waves with every duration settled (contract type).

Built by bidcore.timeline.resolve from ledger.timeline + ledger.wave_plan + policy. Month arithmetic
ported from project_timeline_extraction_layer.py (WaveDefinition / ProjectTimeline).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

WEEKS_PER_MONTH = 4.345


def months_for(weeks: float, weeks_per_month: float = WEEKS_PER_MONTH) -> int:
    """Map a week-stated duration onto whole month columns."""
    try:
        weeks = float(weeks)
    except (TypeError, ValueError):
        return 0
    if weeks <= 0:
        return 0
    return max(1, int(round(weeks / weeks_per_month)))


def weeks_for(months: float, weeks_per_month: float = WEEKS_PER_MONTH) -> float:
    try:
        return round(float(months) * weeks_per_month, 1)
    except (TypeError, ValueError):
        return 0.0


class ResolvedWave(BaseModel):
    name: str
    sequence: int = 1
    total_weeks: float = 0.0
    hypercare_weeks: float = 0.0
    duration_source: str = ""             # rfp | agent | derived
    phase_split: dict[str, float] = Field(default_factory=dict)
    countries: list[str] = Field(default_factory=list)
    lobs: list[str] = Field(default_factory=list)
    kind: str = ""
    partition_axis: str = ""
    go_live: str = ""
    start: str = ""
    unit_ids: list[str] = Field(default_factory=list)

    @property
    def implementation_weeks(self) -> float:
        return max(round(self.total_weeks - self.hypercare_weeks, 2), 0.0)

    @property
    def total_months(self) -> int:
        return months_for(self.total_weeks)

    @property
    def hypercare_months(self) -> int:
        """Trailing PGLS months: >= 1 whenever hypercare was stated, never the whole wave."""
        if self.hypercare_weeks <= 0 or self.total_months <= 1:
            return 0
        return max(1, min(months_for(self.hypercare_weeks), self.total_months - 1))

    @property
    def implementation_months(self) -> int:
        return max(self.total_months - self.hypercare_months, 1)


class ResolvedTimeline(BaseModel):
    waves: list[ResolvedWave] = Field(default_factory=list)
    sequencing: str = "parallel"          # sequential | parallel | staggered
    hypercare_mode: str = "none"
    source: str = "rfp"                   # rfp | derived
    shape: str = ""                       # 1C1W | 1CNW | NC1W | NCNW
    notes: list[str] = Field(default_factory=list)

    @property
    def is_sequential(self) -> bool:
        return self.sequencing == "sequential"

    @property
    def total_weeks(self) -> float:
        return round(sum(w.total_weeks for w in self.waves), 2)

    @property
    def programme_weeks(self) -> float:
        """Elapsed duration: the sum of waves only when they run back to back."""
        if not self.waves:
            return 0.0
        if self.is_sequential:
            return round(sum(w.total_weeks for w in self.waves), 2)
        return round(max(w.total_weeks for w in self.waves), 2)

    @property
    def programme_months(self) -> int:
        if self.is_sequential:
            return sum(w.total_months for w in self.waves) or months_for(self.programme_weeks)
        return max((w.total_months for w in self.waves), default=0) or months_for(self.programme_weeks)

    def wave_start_month(self, wave: ResolvedWave) -> int:
        """0-based start month on the combined grid: sequential waves stack, others start at M1."""
        if not self.is_sequential:
            return 0
        offset = 0
        for candidate in self.waves:
            if candidate.name == wave.name:
                return offset
            offset += candidate.total_months
        return offset
