"""Fill the effort workbook from the ledger + sizing result (no agent ever edits the file).

Sheets (tab order from policy/workbook.yaml): Summary of Project Effort, Functional Scope Estimation,
Project Timeline, one sheet per LOB, Non Catalogue SAP Tools, Tech Dev Scope, Data Migration Scope,
Basis Scope, Security Scope, Analytics Scope, and the hidden `_bid` sheet.

Totals are live formulas (each table's Total, the Functional Scope roll-up, the Summary ladder), so a
reviewer's edit in Excel re-totals the workbook; the values written are the sizing result's, so the
formulas evaluate to exactly the figures bidcore computed. Every table row carries its ledger row id
in a hidden column and is recorded in the render manifest, which is how call 2 reads the edits back.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from bidcore.ledger.models import Ledger
from bidcore.paths import templates_dir
from bidcore.policy import Policy, get_policy
from bidcore.render.workbook import styles as st
from bidcore.render.workbook.layout import (
    FIRST_DATA_ROW, FORMULA, GRID_FIRST_MONTH_COL, GRID_FIXED, HEADER_ROW, HYPERCARE_LABEL, HYPERCARE_SETTING,
    INPUT, SUMMARY_PARAMETERS, TableLayout, quote_sheet, sheet_title, table_layouts,
)
from bidcore.render.workbook.manifest import BID_SHEET, ColumnRef, RenderManifest, TableManifest, save_manifest
from bidcore.render.workbook.template_builder import LOB_PROTOTYPE, PROTO_ROW, PROTO_TOTAL_ROW, build_template
from bidcore.sizing import SizingResult

TEMPLATE_NAME = "template.xlsx"


def _load_template(policy: Policy) -> Workbook:
    path = templates_dir() / TEMPLATE_NAME
    return load_workbook(path) if path.is_file() else build_template(policy)


def _round(value: Any) -> Any:
    return round(float(value), 2) if isinstance(value, (int, float)) and not isinstance(value, bool) else value


class _Table:
    """Writes one table (rows + Total) into a sheet using the sheet's prototype row styles."""

    def __init__(self, ws: Worksheet, layout: TableLayout, proto: list, proto_total: list,
                 manifest: RenderManifest, header_row: int, wave: str = ""):
        self.ws, self.layout, self.proto, self.proto_total = ws, layout, proto, proto_total
        self.header_row, self.row = header_row, header_row + 1
        self.first = self.row
        self.entry = TableManifest(
            key=layout.key, section=layout.section, sheet=ws.title, header_row=header_row,
            label_col=layout.label_col, total_label=layout.total_label, row_id_col=layout.row_id_col,
            columns={i: ColumnRef(field=c.field, kind=c.kind) for i, c in enumerate(layout.columns, start=1)},
            wave=wave)
        manifest.tables.append(self.entry)

    def add(self, row_id: str, values: dict[str, Any]) -> int:
        r = self.row
        st.apply_row_styles(self.ws, r, self.proto)
        recorded: dict[str, Any] = {}
        for c, column in enumerate(self.layout.columns, start=1):
            if c in self.layout.row_formulas:
                self.ws.cell(row=r, column=c, value=self.layout.row_formulas[c].format(r=r))
                continue
            value = _round(values.get(column.field))
            self.ws.cell(row=r, column=c, value=value)
            if column.kind != FORMULA:
                recorded[column.field] = value
        self.ws.cell(row=r, column=self.layout.row_id_col, value=row_id)
        self.entry.rows[row_id] = recorded
        self.row += 1
        return r

    def close(self, label: str | None = None) -> int:
        """Write the Total row; returns its row number."""
        r = self.row
        st.apply_row_styles(self.ws, r, self.proto_total)
        self.ws.cell(row=r, column=self.layout.label_col, value=label or self.layout.total_label)
        if self.layout.total_col:
            letter = get_column_letter(self.layout.total_col)
            last = max(r - 1, self.first)
            self.ws.cell(row=r, column=self.layout.total_col, value=f"=ROUND(SUM({letter}{self.first}:{letter}{last}),2)")
        self.row += 1
        return r


def _protos(ws: Worksheet, width: int) -> tuple[list, list, list]:
    header = st.row_styles(ws, HEADER_ROW, width)
    proto, proto_total = st.row_styles(ws, PROTO_ROW, width), st.row_styles(ws, PROTO_TOTAL_ROW, width)
    st.clear_rows(ws, PROTO_ROW, PROTO_TOTAL_ROW, width)
    return header, proto, proto_total


def _simple_table(ws: Worksheet, layout: TableLayout, manifest: RenderManifest,
                  rows: list[tuple[str, dict[str, Any]]]) -> int:
    _, proto, proto_total = _protos(ws, layout.row_id_col)
    table = _Table(ws, layout, proto, proto_total, manifest, HEADER_ROW)
    for row_id, values in rows:
        table.add(row_id, values)
    return table.close()


# --------------------------------------------------------------------------- sheets

def _lob_sheets(wb: Workbook, layout: TableLayout, ledger: Ledger, sizing: SizingResult,
                manifest: RenderManifest, taken: set[str]) -> dict[str, tuple[str, int]]:
    """One sheet per LOB; returns LOB -> (sheet title, total row)."""
    proto_ws = wb[LOB_PROTOTYPE]
    out: dict[str, tuple[str, int]] = {}
    for lob, module in sizing.effort.modules.items():
        if not module.rows and not module.excluded_scope_ids:
            continue
        ws = wb.copy_worksheet(proto_ws)
        ws.title = sheet_title(lob, taken)
        ws.cell(row=1, column=1, value=lob)
        rows = sorted(module.rows, key=lambda r: (r.business_area, r.scope_id, r.country))
        total_row = _simple_table(ws, layout, manifest, [(r.row_id, r.model_dump()) for r in rows])
        if module.excluded_scope_ids:
            note = ws.cell(row=total_row + 2, column=1,
                           value="Existing, no change (not costed): " + ", ".join(module.excluded_scope_ids))
            note.font = st.ESTIMATE_FONT
        manifest.lob_sheets[ws.title] = lob
        out[lob] = (ws.title, total_row)
    wb.remove(proto_ws)
    return out


def _functional_scope(ws: Worksheet, lob_sheets: dict[str, tuple[str, int]], sizing: SizingResult,
                      non_catalogue: tuple[str, int], lob_layout: TableLayout) -> int:
    lob_col, ba_col = lob_layout.letter("business_area"), lob_layout.letter("business_area")
    total_col = lob_layout.letter("total")
    r = FIRST_DATA_ROW
    for lob, (title, _) in lob_sheets.items():
        areas = sorted({row.business_area for row in sizing.effort.modules[lob].rows})
        ref = quote_sheet(title)
        for area in areas:
            ws.cell(row=r, column=1, value=lob)
            ws.cell(row=r, column=2, value=area)
            ws.cell(row=r, column=3, value=f"=COUNTIFS({ref}!${ba_col}:${ba_col},B{r})")
            ws.cell(row=r, column=4, value=f"=ROUND(SUMIFS({ref}!${total_col}:${total_col},{ref}!${ba_col}:${ba_col},B{r}),2)")
            for c in range(1, 5):
                ws.cell(row=r, column=c).border = st.BORDER
            ws.cell(row=r, column=4).number_format = "0.00"
            r += 1
    del lob_col
    nc_title, nc_total = non_catalogue
    ref = quote_sheet(nc_title)
    ws.cell(row=r, column=1, value=nc_title)
    ws.cell(row=r, column=2, value="SAP tools / modules without Best Practice content")
    ws.cell(row=r, column=3, value=f"=SUM({ref}!C{FIRST_DATA_ROW}:C{max(nc_total - 1, FIRST_DATA_ROW)})")
    ws.cell(row=r, column=4, value=f"={ref}!D{nc_total}")
    for c in range(1, 5):
        cell = ws.cell(row=r, column=c)
        cell.border, cell.fill = st.BORDER, st.TOOLS_FILL
    r += 1
    total = r
    ws.cell(row=total, column=1, value="Total")
    ws.cell(row=total, column=3, value=f"=SUM(C{FIRST_DATA_ROW}:C{total - 1})")
    ws.cell(row=total, column=4, value=f"=ROUND(SUM(D{FIRST_DATA_ROW}:D{total - 1}),2)")
    for c in range(1, 5):
        cell = ws.cell(row=total, column=c)
        cell.border, cell.font, cell.fill = st.BORDER, st.BOLD, st.GREEN_FILL
    ws.cell(row=total, column=4).number_format = "0.00"
    return total


def _data_migration(ws: Worksheet, layout: TableLayout, sizing: SizingResult, manifest: RenderManifest,
                    policy: Policy) -> int:
    spec = policy.workbook["sheets"]["data_migration"]
    width = layout.row_id_col
    header_styles, proto, proto_total = _protos(ws, width)
    headers = [c.header for c in layout.columns]
    # Delivery-wave context table (read-only) above the per-wave conversion tables.
    st.header_row(ws, HEADER_ROW, spec["wave_headers"] + [""] * (len(headers) - len(spec["wave_headers"])),
                  st.NAVY_FILL, st.HEADER_FONT, bordered=False, centered=True)
    r = HEADER_ROW + 1
    for w in sizing.timeline.waves:
        values = [w.name, w.sequence, w.partition_axis or "-", w.total_weeks, w.hypercare_weeks, ", ".join(w.countries)]
        for c, value in enumerate(values, start=1):
            cell = ws.cell(row=r, column=c, value=value)
            cell.fill, cell.border = st.WAVE_FILL, st.BORDER
        r += 1
    totals: list[int] = []
    tables = sizing.effort.workstreams.data_migration
    for index, rows in enumerate(tables):
        wave = sizing.timeline.waves[index].name if index < len(sizing.timeline.waves) else f"Wave {index + 1}"
        r += 1
        title = ws.cell(row=r, column=1, value=f"{spec['table_title']} - {wave}")
        title.font, title.fill = st.BOLD, st.TITLE_FILL
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=len(headers))
        r += 1
        for c, text in enumerate(headers, start=1):
            ws.cell(row=r, column=c, value=text)._style = header_styles[c - 1]
        table = _Table(ws, layout, proto, proto_total, manifest, r, wave=wave)
        for row in rows:
            table.add(f"{row['row_id']}#{index + 1}", {**row, "object": row.get("label") or row["object"]})
        totals.append(table.close(f"Total - {wave}"))
        r = table.row
    r += 1
    letter = get_column_letter(layout.total_col)
    ws.cell(row=r, column=1, value="Total Data Migration Effort")
    ws.cell(row=r, column=layout.total_col,
            value="=ROUND(" + ("+".join(f"{letter}{t}" for t in totals) or "0") + ",2)")
    for c in range(1, len(headers) + 1):
        cell = ws.cell(row=r, column=c)
        cell.font, cell.fill, cell.border = st.BOLD, st.GREEN_FILL, st.BORDER
    ws.cell(row=r, column=layout.total_col).number_format = "0.00"
    return r


def _project_timeline(ws: Worksheet, sizing: SizingResult, manifest: RenderManifest, summary_ref: str,
                      policy: Policy) -> None:
    t, plan = sizing.timeline, sizing.plan
    headers = ["Wave", "Sequence", "Start Month", "Duration (weeks)", "Hypercare (weeks)", "Months",
               "Countries", "Duration Source"]
    st.header_row(ws, HEADER_ROW, headers, st.NAVY_FILL, st.HEADER_FONT, bordered=True, centered=True)
    r = HEADER_ROW + 1
    for w in t.waves:
        values = [w.name, w.sequence, f"M{t.wave_start_month(w) + 1}", w.total_weeks, w.hypercare_weeks,
                  w.total_months, ", ".join(w.countries), w.duration_source or "-"]
        for c, value in enumerate(values, start=1):
            cell = ws.cell(row=r, column=c, value=value)
            cell.fill, cell.border = st.WAVE_FILL, st.BORDER
        r += 1
    ws.cell(row=r, column=1, value=f"Sequencing: {t.sequencing}; programme {t.programme_weeks:g} weeks "
                                   f"({t.programme_months} months)").font = st.ESTIMATE_FONT
    r += 2
    grand_cells: list[str] = []
    for grid in plan.grids:
        months = grid.months
        first_m = GRID_FIRST_MONTH_COL
        total_c = first_m + months
        rid_c = total_c + 1
        title = ws.cell(row=r, column=1, value=f"Resource Plan - {grid.wave_name} (FTE per month)")
        title.font, title.fill = st.BOLD, st.GRID_FILL
        r += 1
        header = [*GRID_FIXED, *(f"M{grid.start_month + i + 1}" for i in range(months)), "Total (MM)"]
        st.header_row(ws, r, header, st.HEADER_FILL, st.HEADER_FONT, bordered=True, centered=True)
        header_r = r
        r += 1
        for c, band in enumerate(grid.phase_bands, start=first_m):
            cell = ws.cell(row=r, column=c, value=band)
            cell.font, cell.alignment, cell.fill = st.BOLD, st.CENTER, st.WAVE_FILL
        ws.cell(row=r, column=1, value="Phase").font = st.BOLD
        r += 1
        columns = {1: ColumnRef(field="role_title", kind="label"), 2: ColumnRef(field="location", kind="label"),
                   3: ColumnRef(field="contribution", kind="label"),
                   **{first_m + i: ColumnRef(field=f"M{i + 1}", kind=INPUT) for i in range(months)},
                   total_c: ColumnRef(field="total", kind=FORMULA)}
        entry = TableManifest(key="grid", section="grid", sheet=ws.title, header_row=r - 1, label_col=1,
                              total_label="Onsite Total", row_id_col=rid_c, columns=columns, wave=grid.wave_name)
        manifest.tables.append(entry)
        first_row = r
        for row in grid.rows:
            row_id = f"{grid.wave_name}||{row.role_title}||{row.location}"
            ws.cell(row=r, column=1, value=row.role_title)
            ws.cell(row=r, column=2, value=row.location)
            ws.cell(row=r, column=3, value=row.contribution)
            recorded: dict[str, Any] = {}
            for i in range(months):
                fte = round(row.fte_at(i + 1), 2)
                cell = ws.cell(row=r, column=first_m + i, value=fte or None)
                cell.number_format, cell.border = "0.0#", st.BORDER
                recorded[f"M{i + 1}"] = fte or None
            last_m = get_column_letter(total_c - 1)
            ws.cell(row=r, column=total_c, value=f"=SUM({get_column_letter(first_m)}{r}:{last_m}{r})").font = st.BOLD
            ws.cell(row=r, column=rid_c, value=row_id)
            entry.rows[row_id] = recorded
            r += 1
        last_row = max(r - 1, first_row)
        for label, location in (("Onsite Total", "Onsite"), ("Offshore Total", "Offshore"), ("Grand Total", None)):
            ws.cell(row=r, column=1, value=label)
            for c in range(first_m, total_c + 1):
                col = get_column_letter(c)
                formula = (f"=SUMIF($B${first_row}:$B${last_row},\"{location}\",{col}{first_row}:{col}{last_row})"
                           if location else f"=SUM({col}{r - 2}:{col}{r - 1})")
                cell = ws.cell(row=r, column=c, value=formula)
                cell.number_format = "0.0#"
            for c in range(1, total_c + 1):
                cell = ws.cell(row=r, column=c)
                cell.font, cell.fill, cell.border = st.BOLD, st.GREEN_FILL, st.BORDER
            r += 1
        grand_cells.append(f"{get_column_letter(total_c)}{r - 1}")
        ws.column_dimensions[get_column_letter(rid_c)].hidden = True
        del header_r
        r += 1
    # Reconciliation: the grid's man-months against the Summary of Project Effort.
    days = policy.commercials.working_days_per_month
    ws.cell(row=r, column=1, value="Resource Reconciliation").font = st.BOLD
    ws.cell(row=r, column=1).fill = st.GRID_FILL
    r += 1
    mm = "=" + ("+".join(grand_cells) or "0")
    rows = [("Total man-months (all waves)", mm),
            ("Total person-days (man-months x %d)" % days, f"=ROUND(B{r}*{days},2)"),
            ("Total Project Effort (Summary of Project Effort)", f"={summary_ref}"),
            ("Peak FTE (all waves, any month)", plan.peak_fte)]
    for label, value in rows:
        ws.cell(row=r, column=1, value=label).border = st.BORDER
        cell = ws.cell(row=r, column=2, value=value)
        cell.border, cell.number_format = st.BORDER, "0.00"
        r += 1
    if sizing.notes:
        r += 1
        ws.cell(row=r, column=1, value="Sizing notes").font = st.BOLD
        for note in sizing.notes[:40]:
            r += 1
            ws.cell(row=r, column=1, value=note).font = st.ESTIMATE_FONT


def _summary(ws: Worksheet, links: dict[str, str], sizing: SizingResult, manifest: RenderManifest,
             policy: Policy) -> int:
    s = sizing.summary
    rows = policy.workbook["project_summary_rows"]
    r = 3
    for spec in rows:
        ws.cell(row=spec["row"], column=1, value=spec["label"])
        ws.cell(row=spec["row"], column=2, value=f"={links[spec['source']]}")
        r = max(r, spec["row"] + 1)
    first, last = rows[0]["row"], rows[-1]["row"]
    params = {key: 3 + i for i, (_, key) in enumerate(SUMMARY_PARAMETERS)}
    for (label, key), row in zip(SUMMARY_PARAMETERS, params.values()):
        ws.cell(row=row, column=4, value=label).border = st.BORDER
        value = getattr(s, key)
        cell = ws.cell(row=row, column=5, value=value)
        cell.border, cell.fill = st.BORDER, st.TOOLS_FILL
        manifest.settings[key] = value
    e = {key: f"$E${row}" for key, row in params.items()}
    build = r
    ladder = [
        ("Total Build Effort (Upto Realization Phase)", f"=ROUND(SUM(B{first}:B{last}),2)", True),
        ("Final Preparation", f"=ROUND(B{build}*{e['final_prep_pct']}/100,2)", False),
        ("Go-Live", f"=ROUND(B{build}*{e['go_live_pct']}/100,2)", False),
        ("Project Management", f"=ROUND(B{build}*{e['project_mgmt_pct']}/100,2)", False),
        (HYPERCARE_LABEL, s.hypercare, False),
        ("Summary of Implementation Effort", f"=ROUND(SUM(B{build}:B{build + 4}),2)", True),
        ("Risk Contingency", f"=ROUND(B{build + 5}*({e['risk_factor']}-1),2)", False),
        ("Total Project Effort", f"=ROUND(B{build + 5}+B{build + 6},2)", True),
        ("Total Project Cost (USD)",
         f"=ROUND((B{build + 7}-B{build + 4})*{e['daily_rate_usd']}+B{build + 4}*{e['hypercare_rate_usd']},2)", True),
    ]
    manifest.settings[HYPERCARE_SETTING] = s.hypercare
    for offset, (label, value, strong) in enumerate(ladder):
        row = build + offset
        ws.cell(row=row, column=1, value=label)
        ws.cell(row=row, column=2, value=value)
        for c in (1, 2):
            cell = ws.cell(row=row, column=c)
            cell.border = st.BORDER
            if strong:
                cell.font, cell.fill = st.BOLD, st.GREEN_FILL
        ws.cell(row=row, column=2).number_format = '#,##0.00'
    for row in range(first, last + 1):
        ws.cell(row=row, column=1).fill, ws.cell(row=row, column=1).font = st.NAVY_FILL, st.HEADER_FONT
        ws.cell(row=row, column=1).border = ws.cell(row=row, column=2).border = st.BORDER
        ws.cell(row=row, column=2).number_format = '#,##0.00'
    ws.cell(row=build + 4, column=2).fill = st.TOOLS_FILL       # Hypercare: reviewer-editable input
    return build + 7                                            # Total Project Effort row


def _bid_sheet(ws: Worksheet, manifest: RenderManifest, ledger: Ledger) -> None:
    rows = [("bid_id", manifest.bid_id), ("render_id", manifest.render_id),
            ("ledger_version", manifest.ledger_version), ("policy_version", manifest.policy_version),
            ("rendered_at", manifest.rendered_at), ("client", ledger.meta.client_name),
            ("rate_card_sheet", ledger.meta.rate_card_sheet),
            ("note", "Do not edit or delete this sheet: it links the workbook to its bid for the proposal step.")]
    for r, (key, value) in enumerate(rows, start=1):
        ws.cell(row=r, column=1, value=key)
        ws.cell(row=r, column=2, value=value)


def render_workbook(ledger: Ledger, sizing: SizingResult, path: Path, policy: Policy | None = None,
                    manifest_dir: Path | None = None) -> Path:
    """Write the effort workbook to `path`; the render manifest goes to `manifest_dir` when given."""
    policy = policy or get_policy()
    spec = policy.workbook["sheets"]
    layouts = table_layouts(policy.workbook)
    manifest = RenderManifest(render_id=uuid.uuid4().hex[:12], bid_id=ledger.meta.bid_id,
                              ledger_version=ledger.meta.version, policy_version=policy.version,
                              rendered_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                              file_name=path.name, summary_sheet=spec["project_summary"]["title"])
    wb = _load_template(policy)
    taken = {name.lower() for name in wb.sheetnames}
    lob_sheets = _lob_sheets(wb, layouts["catalogue"], ledger, sizing, manifest, taken)

    nc_ws = wb[spec["non_catalogue"]["title"]]
    nc_rows = [(n.row_id, {"name": n.name, "description": n.description or n.rationale, "bp_id_count": 1,
                           "effort_days": n.effort_days}) for n in sizing.effort.non_catalogue]
    nc_total = _simple_table(nc_ws, layouts["non_catalogue"], manifest, nc_rows)

    td_ws = wb[spec["tech_dev"]["title"]]
    td_total = _simple_table(td_ws, layouts["tech_dev"], manifest,
                             [(r.row_id, r.model_dump()) for r in sizing.effort.tech_dev])

    tables = sizing.effort.workstreams
    dm_ws = wb[spec["data_migration"]["title"]]
    dm_total = _data_migration(dm_ws, layouts["data_migration"], sizing, manifest, policy)
    basis_ws = wb[spec["basis"]["title"]]
    basis_total = _simple_table(basis_ws, layouts["basis"], manifest, [(r["row_id"], r) for r in tables.basis])
    sec_ws = wb[spec["security"]["title"]]
    sec_total = _simple_table(sec_ws, layouts["security"], manifest, [(r["row_id"], r) for r in tables.security])
    ana_ws = wb[spec["analytics"]["title"]]
    ana_total = _simple_table(ana_ws, layouts["analytics"], manifest, [(r["row_id"], r) for r in tables.analytics])

    fs_ws = wb[spec["functional_scope"]["title"]]
    fs_total = _functional_scope(fs_ws, lob_sheets, sizing, (nc_ws.title, nc_total), layouts["catalogue"])

    def link(ws: Worksheet, col: int, row: int) -> str:
        return f"{quote_sheet(ws.title)}!{get_column_letter(col)}{row}"

    links = {"functional_scope": link(fs_ws, 4, fs_total),
             "data_migration": link(dm_ws, layouts["data_migration"].total_col, dm_total),
             "tech_dev": link(td_ws, layouts["tech_dev"].total_col, td_total),
             "security": link(sec_ws, layouts["security"].total_col, sec_total),
             "basis": link(basis_ws, layouts["basis"].total_col, basis_total),
             "analytics": link(ana_ws, layouts["analytics"].total_col, ana_total)}
    summary_ws = wb[spec["project_summary"]["title"]]
    total_row = _summary(summary_ws, links, sizing, manifest, policy)
    _project_timeline(wb[spec["project_timeline"]["title"]], sizing, manifest,
                      f"{quote_sheet(summary_ws.title)}!B{total_row}", policy)
    _bid_sheet(wb[spec["bid"]["title"]], manifest, ledger)

    # Tab order: Summary, Functional Scope, Timeline, LOB sheets, the scope sheets, _bid (hidden).
    head = [spec[k]["title"] for k in ("project_summary", "functional_scope", "project_timeline")]
    tail = [spec[k]["title"] for k in ("non_catalogue", "tech_dev", "data_migration", "basis", "security",
                                       "analytics", "bid")]
    order = head + [title for title, _ in lob_sheets.values()] + tail
    wb._sheets = [wb[name] for name in order] + [s for s in wb._sheets if s.title not in order]
    wb.active = 0
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    if manifest_dir is not None:
        save_manifest(manifest, manifest_dir)
    return path
