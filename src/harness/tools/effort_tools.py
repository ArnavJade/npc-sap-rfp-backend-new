"""effort_preview: the deterministic person-day totals the wave-planner allocates.

Shown so the planner can weigh its decisions; it never types these numbers into the ledger - it
records shares and tags, and the sizing pipeline turns them into person-days.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Literal

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field

from harness.context import RunContext


class _Preview(BaseModel):
    group_by: Literal["workstream", "lob", "lob_country"] = Field(
        "workstream", description="workstream = the allocation keys the wave plan uses; lob_country = per-country "
                                  "lines (with scope_items row ids) for item tags.")


def make_effort_tools(run: RunContext) -> list[BaseTool]:
    def effort_preview(group_by: str = "workstream") -> str:
        from bidcore.effort.workstreams import workstream_totals
        from bidcore.sizing import compute_effort

        ledger = run.ledger.load()
        timeline = ledger.timeline.data
        waves = len(timeline.waves) if timeline and timeline.waves else 1
        effort = compute_effort(ledger, waves, run.policy)
        if group_by == "lob_country":
            lines = ["scope_items row_id | LOB | country | scope item | person-days"]
            for lob, module in sorted(effort.modules.items()):
                for row in module.rows:
                    lines.append(f"{row.item_row_id} | {lob} | {row.country or 'ALL'} | {row.scope_id} | {row.total:g}")
            return "\n".join(lines[:400]) + ("\n... (truncated)" if len(lines) > 400 else "")
        if group_by == "lob":
            per = defaultdict(float)
            for lob, module in effort.modules.items():
                per[lob] += module.total_effort
            return "\n".join(f"lob:{lob} | {days:g} PD" for lob, days in sorted(per.items())) or "no scope items yet"
        totals = workstream_totals(effort.workstreams, run.policy)
        third_party = effort.third_party_effort
        rows = [(f"lob:{lob}", m.total_effort) for lob, m in sorted(effort.modules.items())]
        rows += [("integrations", third_party), ("non_catalogue", effort.non_catalogue_effort),
                 ("tech_dev", round(effort.tech_dev_effort - third_party, 2))]
        rows += [(k, totals[k]) for k in ("data_migration", "basis", "security", "analytics")]
        note = (f"(data_migration is per-wave tables x {waves} wave(s))" if waves > 1 else "")
        return "workstream | person-days " + note + "\n" + "\n".join(f"{k} | {v:g}" for k, v in rows if v)

    return [StructuredTool.from_function(
        func=effort_preview, name="effort_preview", args_schema=_Preview,
        description="Deterministic person-day totals from the current ledger (rate card, Tech Dev, workstreams), "
                    "grouped for wave planning. Read-only.")]
