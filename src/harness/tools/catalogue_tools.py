"""Deterministic catalogue tools for the catalogue-mapper (and specialists that need a scope ID).

The 445 x 43 BP_ID_LIST matrix never enters a prompt: the agent asks for what it needs and gets
valid Scope IDs with their country flags, so a misread table column cannot invent a scope item.
"""

from __future__ import annotations

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field

from harness.context import RunContext


def _fmt_items(items: list[dict], limit: int = 40) -> str:
    lines = []
    for it in items[:limit]:
        avail = it.get("available_in")
        flags = f" | available in {','.join(avail) or 'NONE of the requested'}" if avail is not None else ""
        lines.append(f"{it['scope_item_id']} | {it['lob']} | {it['business_area']} | {it['description']}{flags}")
    more = f"\n... {len(items) - limit} more (narrow the query)" if len(items) > limit else ""
    return "\n".join(lines) + more if lines else "no matches"


class _Search(BaseModel):
    query: str = Field("", description="Words describing the capability, e.g. 'credit management'.")
    lob: str = Field("", description="Optional exact LOB filter.")
    business_area: str = Field("", description="Optional exact Business Area filter.")
    countries: list[str] = Field(default_factory=list, description="ISO codes to report availability for.")
    limit: int = Field(15, ge=1, le=60)


class _Lookup(BaseModel):
    module_name: str = Field(description="The client's module / capability name, e.g. 'FICO', 'SolMan'.")
    countries: list[str] = Field(default_factory=list)


class _Avail(BaseModel):
    scope_item_ids: list[str]
    countries: list[str]


class _Areas(BaseModel):
    lob: str = Field("", description="LOB to list business areas for; empty = all.")


def make_catalogue_tools(run: RunContext) -> list[BaseTool]:
    cat = run.catalogue

    def catalogue_search(query: str = "", lob: str = "", business_area: str = "", countries: list[str] | None = None,
                         limit: int = 15) -> str:
        hits = cat.search(query, lob or None, business_area or None, countries or [], limit)
        return "scope_item_id | LOB | Business Area | Description\n" + _fmt_items(hits)

    def cross_map_lookup(module_name: str, countries: list[str] | None = None) -> str:
        entry = cat.resolve_module(module_name)
        if entry is None:
            suggestions = cat.crossmap.suggest(module_name)
            if not suggestions:
                return (f"No cross-mapping row for '{module_name}'. Use catalogue_search with descriptive words, "
                        "or route it to non_catalogue if it is an SAP tool/system with no Best Practice items.")
            return (f"No exact cross-mapping row for '{module_name}'. Closest rows (judge, do not assume):\n"
                    + "\n".join(f"- {s.module_name} [{', '.join(s.aliases)}] -> {s.target_text()}" for s in suggestions))
        head = f"'{module_name}' -> cross-mapping row '{entry.module_name}': {entry.target_text()}"
        if entry.is_others:
            return head + "\nRoute: non_catalogue (no catalogue scope items exist for it)."
        blocks = [head]
        for f in entry.filters:
            items = cat.expand(f, countries or [])
            label = " | ".join(x for x in (f.lob or "(any LOB)", f.business_area, f.description_filter,
                                           f.component_filter) if x)
            blocks.append(f"\nFilter [{label}] -> {len(items)} scope item(s):\n" + _fmt_items(items, 60))
        blocks.append("\nKeep only the items the RFP actually asks for; do not take a whole filter blindly.")
        return "\n".join(blocks)

    def check_country_availability(scope_item_ids: list[str], countries: list[str]) -> str:
        table = cat.availability(scope_item_ids, countries)
        codes = [c.upper() for c in countries]
        lines = ["scope_item_id | " + " | ".join(codes)]
        known = cat.get(scope_item_ids)
        for sid in scope_item_ids:
            if sid not in known:
                lines.append(f"{sid} | NOT IN CATALOGUE")
                continue
            lines.append(f"{sid} | " + " | ".join("Yes" if table.get(sid, {}).get(c) else "No" for c in codes))
        return "\n".join(lines)

    def catalogue_business_areas(lob: str = "") -> str:
        rows = cat.business_areas(lob or None)
        return "\n".join(f"{r['lob']} | {r['business_area']} | {r['items']} items" for r in rows) or "unknown LOB"

    return [
        StructuredTool.from_function(func=cross_map_lookup, name="cross_map_lookup", args_schema=_Lookup,
                                     description="Resolve a client module name through the SAP cross-mapping rulebook "
                                                 "and list the catalogue scope items it points to."),
        StructuredTool.from_function(func=catalogue_search, name="catalogue_search", args_schema=_Search,
                                     description="Full-text search of the SAP Best Practice catalogue; returns valid "
                                                 "Scope IDs with country availability."),
        StructuredTool.from_function(func=check_country_availability, name="check_country_availability",
                                     args_schema=_Avail,
                                     description="Yes/No availability of scope items in the given countries."),
        StructuredTool.from_function(func=catalogue_business_areas, name="catalogue_business_areas",
                                     args_schema=_Areas, description="LOB -> Business Area map with item counts."),
    ]
