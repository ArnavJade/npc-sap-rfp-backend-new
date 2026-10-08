"""Workbook table layouts shared by the writer (filler.py) and the edit reader (manifest.py).

The sheet layouts follow the old writers (effort_calculator_layer4.write_effort_workbook and the
*_scope.py sheet writers) cell for cell; the only additions are a hidden row-id column after each
table and the hidden `_bid` sheet. Call 2 reads the reviewer's edits back by row id and column, so the
column a field is written to and the column it is read from must never drift apart - every editable
table is declared once here.

Column kinds:
  input   - a value the reviewer may change; the change becomes a ledger edit or an override
  label   - descriptive text; changes are ignored (except on added rows, where it is the row's data)
  derived - a computed value written as a constant; a change is a conflict
  formula - a live formula; overwriting it with a constant is a conflict
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from openpyxl.utils import get_column_letter

INPUT, LABEL, DERIVED, FORMULA = "input", "label", "derived", "formula"


@dataclass(frozen=True)
class Column:
    header: str
    field: str = ""
    kind: str = LABEL
    width: float = 14
    number_format: str = ""


@dataclass(frozen=True)
class TableLayout:
    key: str                  # catalogue | non_catalogue | tech_dev | data_migration | basis | security | analytics
    section: str              # ledger section the rows view
    columns: tuple[Column, ...]
    header_row: int = 1       # row of the column headers (single-table sheets)
    label_col: int = 1        # column holding the Total label (and a row's identifying text)
    total_label: str = "Total"
    total_cols: tuple[int, ...] = ()               # columns summed on the Total row
    row_formulas: dict[int, str] = field(default_factory=dict)   # column -> formula template with {r}
    skip_labels: tuple[str, ...] = ()              # band rows inside the table (not data, not added rows)

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


def _from_yaml(headers: list[str], specs: list[tuple[str, str, float, str]]) -> tuple[Column, ...]:
    """Pair the policy's header texts (presales-owned wording) with field/kind/width/format specs."""
    if len(headers) != len(specs):
        raise ValueError(f"workbook.yaml headers ({len(headers)}) do not match the layout ({len(specs)} columns)")
    return tuple(Column(h, f, k, w, n) for h, (f, k, w, n) in zip(headers, specs))


def table_layouts(workbook_policy: dict) -> dict[str, TableLayout]:
    sheets = workbook_policy["sheets"]
    lob = TableLayout("catalogue", "scope_items", _from_yaml(sheets["lob"]["headers"], [
        ("lob", LABEL, 0, ""), ("business_area", LABEL, 0, ""), ("country", LABEL, 0, ""),
        ("scope_id", LABEL, 0, ""), ("description", LABEL, 0, ""), ("complexity", LABEL, 0, ""),
        ("workshops_configuration", INPUT, 0, ""), ("unit_testing", INPUT, 0, ""),
        ("integration_testing", INPUT, 0, ""), ("documentation_training", INPUT, 0, ""),
        ("user_acceptance_testing", INPUT, 0, ""), ("multiplication_factor", INPUT, 0, ""),
        ("total", FORMULA, 0, ""), ("wave", INPUT, 0, "")]),
        label_col=5, total_label="TOTAL", total_cols=(13,), row_formulas={13: sheets["lob"]["row_formula"]["M"]})
    non_catalogue = TableLayout("non_catalogue", "non_catalogue", _from_yaml(sheets["non_catalogue"]["headers"], [
        ("name", LABEL, 0, ""), ("description", LABEL, 0, ""), ("bp_id_count", LABEL, 0, ""),
        ("effort_days", INPUT, 0, "")]),
        total_label="Total Non-Catalogue SAP Tools", total_cols=(4,), skip_labels=("Non-Catalogue SAP Tools",))
    tech_dev = TableLayout("tech_dev", "tech_dev", _from_yaml(sheets["tech_dev"]["headers"], [
        ("module", LABEL, 0, ""), ("object_name", LABEL, 0, ""), ("object_type", LABEL, 0, ""),
        ("middleware", LABEL, 0, ""), ("source_system", LABEL, 0, ""), ("target_system", LABEL, 0, ""),
        ("no_of_objects", INPUT, 0, ""), ("complexity", LABEL, 0, ""), ("development", INPUT, 0, ""),
        ("configuration", INPUT, 0, ""), ("unit_testing", INPUT, 0, ""), ("qa_testing", INPUT, 0, ""),
        ("total", FORMULA, 0, "")]),
        label_col=2, total_cols=(13,), row_formulas={13: sheets["tech_dev"]["row_formula"]["M"]})
    data_migration = TableLayout("data_migration", "data_migration", _from_yaml(
        sheets["data_migration"]["headers"], [
            ("object", LABEL, 55.36, ""), ("status", INPUT, 17.63, ""), ("func_spec", INPUT, 34.82, ""),
            ("program_dev", INPUT, 21.18, ""), ("iteration_1", INPUT, 13.54, ""),
            ("iteration_2", INPUT, 15.18, ""), ("iteration_3", INPUT, 12.82, ""), ("cutover", INPUT, 12.82, ""),
            ("total", FORMULA, 13.82, "")]),
        total_cols=(3, 4, 5, 6, 7, 8, 9), row_formulas={9: sheets["data_migration"]["row_formula"]["I"]},
        skip_labels=("Master Data",))
    basis = TableLayout("basis", "basis", _from_yaml(sheets["basis"]["headers"], [
        ("activity", LABEL, 55.36, ""), ("status", INPUT, 17.63, ""), ("dev", INPUT, 34.82, ""),
        ("qa", INPUT, 21.18, ""), ("prd", INPUT, 13.54, ""), ("total", FORMULA, 15.18, "")]),
        header_row=2, total_cols=(3, 4, 5, 6), row_formulas={6: sheets["basis"]["row_formula"]["F"]})
    security = TableLayout("security", "security", _from_yaml(sheets["security"]["headers"], [
        ("activity", LABEL, 60, ""), ("status", INPUT, 20, ""), ("complexity", INPUT, 14, ""),
        ("effort_days", INPUT, 20, ""), ("total", FORMULA, 14, "")]),
        header_row=2, total_cols=(4, 5), row_formulas={5: sheets["security"]["row_formula"]["E"]})
    analytics = TableLayout("analytics", "analytics", _from_yaml(sheets["analytics"]["headers"], [
        ("object", LABEL, 50, ""), ("object_type", INPUT, 13, ""), ("build", INPUT, 16, ""),
        ("no_of_objects", INPUT, 14, ""), ("status", INPUT, 20, ""), ("complexity", INPUT, 12, ""),
        ("devlp", FORMULA, 10, ""), ("unit_testing", FORMULA, 13, ""), ("qa_testing", FORMULA, 12, ""),
        ("total", FORMULA, 11, "")]),
        header_row=2, total_label="Total Days of Estimation", total_cols=(7, 8, 9, 10),
        row_formulas={10: "=SUM(G{r}:I{r})"})
    return {t.key: t for t in (lob, non_catalogue, tech_dev, data_migration, basis, security, analytics)}


# Resource-plan grid (Project Timeline): Skill | Location | M1..Mn | Total Man-months.
GRID_FIRST_MONTH_COL = 3
GRID_SKIP_LABELS = ("Phase", "Onsite Total", "Offshore Total")
GRID_TOTAL_LABEL = "Grand Total"

# Summary of Project Effort side table (D/E from row 2): label -> settings key. The first four are
# the old template's own inputs (labels verbatim, typos included); the two rates are added so a
# reviewer can change them too.
SUMMARY_PARAMETERS = (
    ("Final preparation phase - %", "final_prep_pct"),
    ("Go-Live Effort - %", "go_live_pct"),
    ("Project Mangement Effort - %", "project_mgmt_pct"),
    ("Project Risk Factor", "risk_factor"),
    ("Daily Rate (USD)", "daily_rate_usd"),
    ("Hypercare Rate (USD per day)", "hypercare_rate_usd"),
)
HYPERCARE_LABEL = "Hypercare"
HYPERCARE_SETTING = "hypercare_effort_days"

_INVALID_SHEET_CHARS = re.compile(r"[\\/*?:\[\]]")


def module_sheet_name(lob: str, used: set[str]) -> str:
    """Old _module_sheet_names: invalid characters -> '_', 31 characters, '_<n>' on collision."""
    name = _INVALID_SHEET_CHARS.sub("_", lob or "Module")[:31]
    base, suffix = name, 1
    while name in used:
        tail = f"_{suffix}"
        name, suffix = base[:31 - len(tail)] + tail, suffix + 1
    used.add(name)
    return name


def quote_sheet(title: str) -> str:
    return "'" + title.replace("'", "''") + "'"


def xl_criteria(text: str) -> str:
    """Exact-match COUNTIF/SUMIF criteria literal (old _xl_criteria)."""
    escaped = text.replace("~", "~~").replace("*", "~*").replace("?", "~?").replace('"', '""')
    return f'"={escaped}"'
