"""Workbook table layouts shared by the writer (filler.py) and the edit reader (manifest.py).

WHY one module: call 2 reads the reviewer's edits back by row id and column, so the column a field is
written to and the column it is read from must never drift apart. Every editable table is declared
once here: which ledger section it views, the field and kind of each column, where the hidden row-id
column sits and which label closes the table.

Column kinds:
  input   - a value the reviewer may change; the change becomes a ledger edit or an override
  label   - descriptive text; changes are ignored (except on added rows, where it is the row's data)
  derived - a computed value written as a constant (e.g. analytics man-days); a change is a conflict
  formula - a live formula; overwriting it with a constant is a conflict
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from openpyxl.utils import get_column_letter

INPUT, LABEL, DERIVED, FORMULA = "input", "label", "derived", "formula"
TOTAL_LABEL = "Total"
HEADER_ROW = 3            # every single-table sheet: title band row 1, blank row 2, header row 3
FIRST_DATA_ROW = 4


@dataclass(frozen=True)
class Column:
    header: str
    field: str = ""
    kind: str = LABEL
    width: float = 14
    number_format: str = ""


@dataclass(frozen=True)
class TableLayout:
    key: str                  # catalogue | non_catalogue | tech_dev | data_migration | basis | security | analytics | grid
    section: str              # ledger section the rows view (grid: resource plan)
    columns: tuple[Column, ...]
    label_col: int = 1        # column whose text identifies a row (and the Total row)
    total_col: int = 0        # column holding the table total (formula); 0 = none
    total_label: str = TOTAL_LABEL
    row_formulas: dict[int, str] = field(default_factory=dict)   # column index -> formula template with {r}

    @property
    def row_id_col(self) -> int:
        return len(self.columns) + 1

    def col_of(self, field_name: str) -> int:
        for index, column in enumerate(self.columns, start=1):
            if column.field == field_name:
                return index
        raise KeyError(field_name)

    def letter(self, field_name: str) -> str:
        return get_column_letter(self.col_of(field_name))


NUM = "0.00"
INT = "0"


def _from_yaml(headers: list[str], specs: list[tuple[str, str, float, str]]) -> tuple[Column, ...]:
    """Pair the policy's header texts (presales-owned wording) with field/kind/width/format specs."""
    if len(headers) != len(specs):
        raise ValueError(f"workbook.yaml headers ({len(headers)}) do not match the layout ({len(specs)} columns)")
    return tuple(Column(h, f, k, w, n) for h, (f, k, w, n) in zip(headers, specs))


def table_layouts(workbook_policy: dict) -> dict[str, TableLayout]:
    sheets = workbook_policy["sheets"]
    lob = TableLayout("catalogue", "scope_items", _from_yaml(sheets["lob"]["headers"], [
        ("lob", LABEL, 22, ""), ("business_area", LABEL, 30, ""), ("country", LABEL, 10, ""),
        ("scope_id", LABEL, 10, ""), ("description", LABEL, 42, ""), ("complexity", LABEL, 11, ""),
        ("workshops_configuration", INPUT, 14, NUM), ("unit_testing", INPUT, 12, NUM),
        ("integration_testing", INPUT, 13, NUM), ("documentation_training", INPUT, 15, NUM),
        ("user_acceptance_testing", INPUT, 14, NUM), ("multiplication_factor", INPUT, 13, NUM),
        ("total", FORMULA, 12, NUM), ("wave", INPUT, 12, "")]),
        label_col=4, total_col=13, row_formulas={13: sheets["lob"]["row_formula"]["M"]})
    non_catalogue = TableLayout("non_catalogue", "non_catalogue", _from_yaml(sheets["non_catalogue"]["headers"], [
        ("name", LABEL, 36, ""), ("description", LABEL, 60, ""), ("bp_id_count", LABEL, 12, INT),
        ("effort_days", INPUT, 18, NUM)]), total_col=4)
    tech_dev = TableLayout("tech_dev", "tech_dev", _from_yaml(sheets["tech_dev"]["headers"], [
        ("module", LABEL, 10, ""), ("object_name", LABEL, 34, ""), ("object_type", LABEL, 14, ""),
        ("middleware", LABEL, 16, ""), ("source_system", LABEL, 16, ""), ("target_system", LABEL, 16, ""),
        ("no_of_objects", INPUT, 11, INT), ("complexity", LABEL, 11, ""), ("development", INPUT, 13, NUM),
        ("configuration", INPUT, 13, NUM), ("unit_testing", INPUT, 12, NUM), ("qa_testing", INPUT, 12, NUM),
        ("total", FORMULA, 12, NUM)]),
        label_col=2, total_col=13, row_formulas={13: sheets["tech_dev"]["row_formula"]["M"]})
    data_migration = TableLayout("data_migration", "data_migration", _from_yaml(
        sheets["data_migration"]["headers"], [
            ("object", LABEL, 40, ""), ("status", INPUT, 14, ""), ("func_spec", INPUT, 16, NUM),
            ("program_dev", INPUT, 16, NUM), ("iteration_1", INPUT, 16, NUM), ("iteration_2", INPUT, 16, NUM),
            ("iteration_3", INPUT, 16, NUM), ("cutover", INPUT, 14, NUM), ("total", FORMULA, 12, NUM)]),
        total_col=9, row_formulas={9: sheets["data_migration"]["row_formula"]["I"]})
    basis = TableLayout("basis", "basis", _from_yaml(sheets["basis"]["headers"], [
        ("activity", LABEL, 50, ""), ("status", INPUT, 16, ""), ("dev", INPUT, 11, INT), ("qa", INPUT, 11, INT),
        ("prd", INPUT, 11, INT), ("total", FORMULA, 11, NUM)]),
        total_col=6, row_formulas={6: sheets["basis"]["row_formula"]["F"]})
    security = TableLayout("security", "security", _from_yaml(sheets["security"]["headers"], [
        ("activity", LABEL, 55, ""), ("status", INPUT, 16, ""), ("complexity", INPUT, 12, ""),
        ("effort_days", INPUT, 16, INT), ("total", FORMULA, 11, NUM)]),
        total_col=5, row_formulas={5: sheets["security"]["row_formula"]["E"]})
    analytics = TableLayout("analytics", "analytics", _from_yaml(sheets["analytics"]["headers"], [
        ("object", LABEL, 40, ""), ("object_type", INPUT, 13, ""), ("build", INPUT, 14, ""),
        ("no_of_objects", INPUT, 11, INT), ("status", INPUT, 16, ""), ("complexity", INPUT, 12, ""),
        ("devlp", DERIVED, 10, NUM), ("unit_testing", DERIVED, 12, NUM), ("qa_testing", DERIVED, 11, NUM),
        ("total", FORMULA, 11, NUM)]),
        total_col=10, row_formulas={10: "=SUM(G{r}:I{r})"})
    return {t.key: t for t in (lob, non_catalogue, tech_dev, data_migration, basis, security, analytics)}


# Resource-plan grid: Role | Location | Contribution | M.. | Total; month columns vary per wave.
GRID_FIXED = ("Role", "Location", "Contribution")
GRID_FIRST_MONTH_COL = len(GRID_FIXED) + 1
GRID_TOTAL_LABELS = ("Onsite Total", "Offshore Total", "Grand Total")

# Summary of Project Effort side table: parameter label -> settings key (reviewer-editable inputs).
SUMMARY_PARAMETERS = (
    ("Final Preparation %", "final_prep_pct"),
    ("Go-Live %", "go_live_pct"),
    ("Project Management %", "project_mgmt_pct"),
    ("Risk Contingency Factor", "risk_factor"),
    ("Daily Rate (USD)", "daily_rate_usd"),
    ("Hypercare Rate (USD per day)", "hypercare_rate_usd"),
)
HYPERCARE_LABEL = "Hypercare"
HYPERCARE_SETTING = "hypercare_effort_days"

_INVALID_SHEET_CHARS = re.compile(r"[\[\]:*?/\\]")


def sheet_title(name: str, taken: set[str]) -> str:
    """A valid, unique (case-insensitive) Excel sheet title of at most 31 characters."""
    base = _INVALID_SHEET_CHARS.sub("-", name).strip("' ") or "Sheet"
    title, n = base[:31], 2
    while title.lower() in taken:
        suffix = f" ({n})"
        title, n = base[:31 - len(suffix)] + suffix, n + 1
    taken.add(title.lower())
    return title


def quote_sheet(title: str) -> str:
    return "'" + title.replace("'", "''") + "'"
