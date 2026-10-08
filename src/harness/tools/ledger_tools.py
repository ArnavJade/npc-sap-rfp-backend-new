"""Ledger tools. The ONLY way an agent changes the bid ledger.

Every specialist gets one typed write tool per section it owns (`ledger_write_security`, ...), built as a
closure over (run, agent, section): a tool for another section simply does not exist in its toolbox, and
the LedgerGuardMiddleware double-checks every call. Writes are validated (schema, evidence, catalogue,
section rules); rejected rows come back with reasons the agent can act on, accepted rows are saved.
"""

from __future__ import annotations

import json
import re
from typing import Any, Literal

from langchain_core.tools import BaseTool, StructuredTool, ToolException
from pydantic import BaseModel, Field, create_model

from bidcore.ledger.base import RowSection, utcnow
from bidcore.ledger.identity import find_twin, merge_into
from bidcore.ledger.models import SECTIONS, Ledger
from bidcore.ledger.overlap import find_overlaps
from bidcore.ledger.validate import Verdict, validate
from harness.context import RunContext

MAX_READ_CHARS = 30_000


def _label(row: Any) -> str:
    for attr in ("scope_item_id", "system", "name", "activity", "object", "capability", "title"):
        value = getattr(row, attr, None)
        if value:
            return str(value)[:60]
    return ""


def _next_ids(section: RowSection, prefix: str, count: int) -> list[str]:
    nums = [int(m.group(1)) for r in section.rows if (m := re.fullmatch(rf"{prefix}-(\d+)", r.row_id or ""))]
    start = max(nums, default=0) + 1
    return [f"{prefix}-{n}" for n in range(start, start + count)]


def _report(section: str, saved: list[str], rejected: list[Verdict], notes: list[str]) -> str:
    parts = []
    if saved:
        parts.append(f"Saved {len(saved)} row(s) to {section}: {', '.join(saved[:40])}"
                     + (" ..." if len(saved) > 40 else "") + ".")
    if rejected:
        parts.append(f"REJECTED {len(rejected)} row(s) - fix and resend them (accepted rows are already saved):")
        parts += [f"  - row {v.index + 1} ({_label(v.row) or 'unnamed'}): {'; '.join(v.errors)}" for v in rejected]
    if notes:
        parts.append("Notes: " + " | ".join(notes[:20]))
    return "\n".join(parts) or "Nothing to write."


# ------------------------------------------------------------------------------ writes
def write_rows(run: RunContext, agent: str, section: str, rows: list[Any], mode: str = "append",
               none_reason: str = "") -> str:
    """Upsert `rows` into `section`. A row with the row_id of a saved row replaces that row (an explicit
    correction); any other row that matches a saved one by the section's identity (bidcore.ledger.identity)
    is merged into it instead of being added again, so resending a batch never duplicates. There is no
    'replace all': rows are removed only with delete_rows (the third live run wiped 34 of 36 capabilities
    by sending single-row corrections with mode='replace')."""
    spec = SECTIONS[section]
    stats = {"saved": 0, "merged": 0, "rejected": 0, "reasons": []}
    mode_note = ("mode='replace' is not supported: rows were matched to the saved ones (give row_id to "
                 "correct one; delete_rows removes rows)") if mode not in ("", "append") else ""

    def apply(ledger: Ledger) -> tuple[str, bool]:
        sec: RowSection = ledger.section(section)
        if not rows:
            if not none_reason.strip():
                return "Give none_reason when there is nothing to record (and cite the RFP if you can).", False
            if not sec.rows:
                sec.rows, sec.state, sec.none_reason = [], "empty", none_reason.strip()
                sec.written_by = sorted({*sec.written_by, agent})
                sec.updated_at = utcnow()
                return f"Recorded {section} as empty: {none_reason.strip()}", True
            # Not an error: the agent wanted "nothing more to add". Keep the rows.
            return (f"Nothing changed: {section} already has {len(sec.rows)} row(s), which are kept "
                    "(delete_rows removes rows you no longer want)."), True

        verdicts = validate(section, rows, run.validation(ledger))
        accepted = [v for v in verdicts if v.ok]
        rejected = [v for v in verdicts if not v.ok]
        notes = [f"row {v.index + 1}: {n}" for v in verdicts for n in v.notes]
        if mode_note:
            notes.insert(0, mode_note)
        existing = {r.row_id: i for i, r in enumerate(sec.rows)}
        new_ids = iter(_next_ids(sec, spec.row_prefix, len(accepted)))
        saved: list[str] = []
        for v in accepted:
            row = v.row
            row.written_by = agent
            if row.row_id and row.row_id in existing:          # explicit correction of a saved row
                sec.rows[existing[row.row_id]] = row
                saved.append(f"{row.row_id} (updated)")
                continue
            twin = find_twin(section, sec.rows, row)
            if twin is not None:                               # the same item again: merge, never duplicate
                changed = merge_into(twin, row)
                saved.append(f"{twin.row_id} (merged{': ' + ', '.join(changed) if changed else ', no change'})")
                stats["merged"] += 1
                continue
            row.row_id = next(new_ids)
            sec.rows.append(row)
            existing[row.row_id] = len(sec.rows) - 1
            saved.append(row.row_id)
        if sec.rows:
            sec.state, sec.none_reason = "written", ""
        sec.written_by = sorted({*sec.written_by, agent})
        sec.updated_at = utcnow()
        stats.update(saved=len(saved), rejected=len(rejected),
                     reasons=[f"row {v.index + 1} ({_label(v.row) or 'unnamed'}): {'; '.join(v.errors)}"[:400]
                              for v in rejected[:10]])
        return _report(section, saved, rejected, notes), bool(accepted)

    message, ok = run.ledger.update(apply, actor=agent, action=f"write {section}", section=section,
                                   detail=f"{len(rows)} row(s), mode={mode}")
    run.trace.emit("ledger_write", agent, section=section, rows=len(rows), mode=mode, ok=ok,
                   saved=stats["saved"], merged=stats["merged"], rejected=stats["rejected"], empty=not rows)
    if stats["rejected"] or not ok:
        run.trace.emit("ledger_rejected", agent, section=section, rejected=stats["rejected"] or len(rows),
                       reasons=stats["reasons"] or [message[:600]])
    if not ok:
        raise ToolException(message)
    return message


def write_object(run: RunContext, agent: str, section: str, data: Any, none_reason: str = "") -> str:
    def apply(ledger: Ledger) -> tuple[str, bool]:
        sec = ledger.section(section)
        if data is None:
            if not none_reason.strip():
                return "Provide `data`, or none_reason when the RFP has nothing for this section.", False
            sec.data, sec.state, sec.none_reason = None, "empty", none_reason.strip()
        else:
            [verdict] = validate(section, [data], run.validation(ledger))
            if not verdict.ok:
                return "REJECTED - fix and resend:\n  - " + "\n  - ".join(verdict.errors), False
            sec.data, sec.state, sec.none_reason = verdict.row, "written", ""
            if verdict.notes:
                sec.written_by = sorted({*sec.written_by, agent})
                sec.updated_at = utcnow()
                return f"Saved {section}. Notes: " + " | ".join(verdict.notes[:20]), True
        sec.written_by = sorted({*sec.written_by, agent})
        sec.updated_at = utcnow()
        return (f"Saved {section}." if data is not None else f"Recorded {section} as empty."), True

    message, ok = run.ledger.update(apply, actor=agent, action=f"write {section}", section=section)
    run.trace.emit("ledger_write", agent, section=section, ok=ok, empty=data is None, saved=int(ok), rejected=int(not ok))
    if not ok:
        run.trace.emit("ledger_rejected", agent, section=section, rejected=1, reasons=[message[:1200]])
    if not ok:
        raise ToolException(message)
    return message


def _schema_error(exc: Exception) -> str:
    """A malformed tool call comes back as a message the agent can fix, not a crash."""
    lines = str(exc).splitlines()
    return "REJECTED (schema) - fix these fields and resend:\n" + "\n".join(lines[:30])


def _write_tool(run: RunContext, agent: str, section: str) -> BaseTool:
    spec = SECTIONS[section]
    if spec.kind == "rows":
        args = create_model(
            f"Write_{section}", rows=(list[spec.model], Field(default_factory=list, description="Rows to save.")),
            mode=(str, Field("append", description="Always 'append'. A row matching a saved one is merged into "
                                                   "it; give row_id to correct a saved row.")),
            none_reason=(str, Field("", description="Only with rows=[]: why the RFP has nothing here.")))

        def run_rows(rows: list | None = None, mode: str = "append", none_reason: str = "") -> str:
            return write_rows(run, agent, section, list(rows or []), mode, none_reason)
        func, desc = run_rows, (f"Save rows to the ledger section '{section}' (validated: rejected rows come "
                                "back with reasons). A row that matches one already saved is merged into it, "
                                "never duplicated; give row_id to correct a saved row; delete_rows removes "
                                "rows. Use rows=[] + none_reason when nothing applies.")
    else:
        args = create_model(
            f"Write_{section}", data=(spec.model | None, Field(None, description=f"The complete {section} object.")),
            none_reason=(str, Field("", description="Only with data omitted: why the RFP has nothing here.")))

        def run_object(data: Any = None, none_reason: str = "") -> str:
            return write_object(run, agent, section, data, none_reason)
        func, desc = run_object, (f"Save the ledger section '{section}' (replaces it; validated). Omit data and "
                                  "give none_reason when the RFP has nothing for it.")
    return StructuredTool.from_function(func=func, name=f"ledger_write_{section}", description=desc,
                                        args_schema=args, handle_tool_error=True,
                                        handle_validation_error=_schema_error)


def _delete_tool(run: RunContext, agent: str, sections: list[str]) -> BaseTool:
    row_sections = [s for s in sections if SECTIONS[s].kind == "rows"]
    args = create_model("DeleteRows", section=(Literal[tuple(row_sections)], ...),
                        row_ids=(list[str], ...), reason=(str, ...))

    def delete_rows(section: str, row_ids: list[str], reason: str) -> str:
        def apply(ledger: Ledger) -> str:
            sec = ledger.section(section)
            before = len(sec.rows)
            sec.rows = [r for r in sec.rows if r.row_id not in set(row_ids)]
            if not sec.rows and sec.state == "written":
                sec.state = "pending"
            return f"Deleted {before - len(sec.rows)} row(s) from {section}."
        return run.ledger.update(apply, actor=agent, action=f"delete {section}", section=section,
                                 detail=f"{row_ids}: {reason}")
    return StructuredTool.from_function(func=delete_rows, name="delete_rows", args_schema=args,
                                        description="Delete your own rows (give the reason).")


def make_write_tools(run: RunContext, agent: str, sections: list[str]) -> list[BaseTool]:
    tools = [_write_tool(run, agent, s) for s in sections]
    if any(SECTIONS[s].kind == "rows" for s in sections):
        tools.append(_delete_tool(run, agent, sections))
    return tools


# ------------------------------------------------------------------------------ reads / checks
class _ReadArgs(BaseModel):
    section: str = Field(description="Ledger section name, e.g. 'capabilities', 'timeline', 'scope_items'.")
    offset: int = Field(0, description="First row to return (row sections).")
    limit: int = Field(200, description="Max rows to return.")


def make_read_tools(run: RunContext) -> list[BaseTool]:
    def ledger_read(section: str, offset: int = 0, limit: int = 200) -> str:
        if section not in SECTIONS:
            raise ToolException(f"unknown section '{section}'; sections: {sorted(SECTIONS)}")
        sec = run.ledger.load().section(section)
        payload: dict[str, Any] = {"section": section, "state": sec.state, "none_reason": sec.none_reason}
        if isinstance(sec, RowSection):
            rows = sec.rows[offset:offset + limit]
            payload.update(total_rows=len(sec.rows), offset=offset,
                           rows=[r.model_dump(exclude={"written_by"}, exclude_defaults=True) for r in rows])
        else:
            payload["data"] = sec.data.model_dump(exclude_defaults=True) if sec.data else None
        text = json.dumps(payload, ensure_ascii=False, default=str)
        if len(text) > MAX_READ_CHARS:
            text = text[:MAX_READ_CHARS] + f'... [truncated: read again with offset/limit]"'
        return text

    def ledger_status() -> str:
        led = run.ledger.load()
        lines = ["section | state | rows | written_by | note"]
        for name, spec in SECTIONS.items():
            if spec.team != run.team:
                continue
            sec = led.section(name)
            count = len(sec.rows) if isinstance(sec, RowSection) else (1 if sec.data else 0)
            lines.append(f"{name} | {sec.state} | {count} | {','.join(sec.written_by) or '-'} | {sec.none_reason[:80]}")
        return "\n".join(lines)

    return [
        StructuredTool.from_function(func=ledger_read, name="ledger_read", args_schema=_ReadArgs,
                                     description="Read one ledger section as JSON (row sections are paged).",
                                     handle_tool_error=True),
        StructuredTool.from_function(func=ledger_status, name="ledger_status",
                                     description="State of every ledger section of this call: written / empty / pending."),
    ]


def coverage_gaps(run: RunContext, ledger: Ledger | None = None) -> list[str]:
    ledger = ledger or run.ledger.load()
    required = run.team_config.get("required_sections", [])
    return [s for s in required if s in SECTIONS and ledger.section(s).state == "pending"]


def make_orchestrator_tools(run: RunContext) -> list[BaseTool]:
    def ledger_check() -> str:
        led = run.ledger.load()
        gaps = coverage_gaps(run, led)
        overlaps = [o.as_dict() for o in find_overlaps(led)] if run.team == "effort" else []
        return json.dumps({"missing_sections": gaps, "overlaps": overlaps,
                           "ok": not gaps and not overlaps}, ensure_ascii=False)

    class _Resolve(BaseModel):
        keep_section: str
        keep_row_id: str
        drop_section: str
        drop_row_id: str
        reason: str

    def ledger_resolve_overlap(keep_section: str, keep_row_id: str, drop_section: str, drop_row_id: str,
                               reason: str) -> str:
        def apply(ledger: Ledger) -> str:
            pairs = {(o.keep_section, o.keep_row_id, o.drop_section, o.drop_row_id) for o in find_overlaps(ledger)}
            flipped = (drop_section, drop_row_id, keep_section, keep_row_id)
            if (keep_section, keep_row_id, drop_section, drop_row_id) not in pairs and flipped not in pairs:
                raise ToolException("That pair is not a reported overlap; call ledger_check for the current list.")
            sec = ledger.section(drop_section)
            sec.rows = [r for r in sec.rows if r.row_id != drop_row_id]
            return f"Dropped {drop_section}/{drop_row_id}; kept {keep_section}/{keep_row_id}."
        return run.ledger.update(apply, actor=f"{run.team}-orchestrator", action="resolve overlap",
                                 section=drop_section, detail=reason)

    return [
        StructuredTool.from_function(func=ledger_check, name="ledger_check",
                                     description="Missing sections and cross-section overlaps still to resolve."),
        StructuredTool.from_function(func=ledger_resolve_overlap, name="ledger_resolve_overlap", args_schema=_Resolve,
                                     description="Resolve one reported overlap: keep one row, drop the other.",
                                     handle_tool_error=True),
    ]
