"""Deterministic catalogue tools for the catalogue-mapper (and specialists that need a scope ID).

The 445 x 43 BP_ID_LIST matrix never enters a prompt: the agent asks for what it needs and gets
valid Scope IDs with their country flags, so a misread table column cannot invent a scope item.
"""

from __future__ import annotations

from langchain_core.tools import BaseTool, StructuredTool, ToolException
from pydantic import BaseModel, Field

from bidcore.countries import check_countries
from harness.context import RunContext

MAX_SEARCH_LIMIT = 100   # the largest Business Area (Sales | Order and Contract Management) has 53 items


def bid_countries(run: RunContext) -> list[str]:
    profile = run.ledger.load().rfp_profile.data
    return [c.code for c in profile.countries] if profile else []


def resolve_countries(run: RunContext, countries: list[str] | None) -> tuple[list[str], str]:
    """ISO-2 catalogue codes for the countries an agent passed ('KSA' -> 'SA'), defaulting to the bid's
    in-scope countries, plus a note for the agent. Unknown values raise: an availability answer for a
    code the catalogue does not have would read "available in NONE" and silently empty the mapping."""
    check = check_countries(countries, run.policy.catalogue.allowed_countries)
    if check.unknown:
        raise ToolException(f"{check.unknown} are not recognised countries. Use ISO-2 codes; this bid's countries "
                            f"are {bid_countries(run) or 'not recorded yet (rfp_profile)'}.")
    codes = check.codes
    note = check.note()
    if not codes:
        codes = bid_countries(run)
        if countries and check.unsupported:
            note += f"; using the bid's catalogue countries {codes} instead"
    return codes, (f"[{note}]\n" if note else "")


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
    countries: list[str] = Field(default_factory=list, description="ISO-2 codes to report availability for; "
                                                                   "empty = the bid's countries.")
    limit: int = Field(15, description="Max rows to return (1-100; larger values are capped).")


class _Lookup(BaseModel):
    module_name: str = Field(description="The client's module / capability name, e.g. 'FICO', 'SolMan'.")
    countries: list[str] = Field(default_factory=list, description="ISO-2 codes; empty = the bid's countries.")


class _Avail(BaseModel):
    scope_item_ids: list[str]
    countries: list[str] = Field(default_factory=list, description="ISO-2 codes; empty = the bid's countries.")


class _Areas(BaseModel):
    lob: str = Field("", description="LOB to list business areas for; empty = all.")


def make_catalogue_tools(run: RunContext) -> list[BaseTool]:
    cat = run.catalogue

    def catalogue_search(query: str = "", lob: str = "", business_area: str = "", countries: list[str] | None = None,
                         limit: int = 15) -> str:
        limit = max(1, min(int(limit or 15), MAX_SEARCH_LIMIT))   # cap, never reject (Gemini asked for 100)
        codes, note = resolve_countries(run, countries)
        hits = cat.search(query, lob or None, business_area or None, codes, limit)
        return note + "scope_item_id | LOB | Business Area | Description\n" + _fmt_items(hits, limit)

    def cross_map_lookup(module_name: str, countries: list[str] | None = None) -> str:
        codes, note = resolve_countries(run, countries)
        return note + _cross_map_lookup(module_name, codes)

    def _cross_map_lookup(module_name: str, countries: list[str]) -> str:
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
        blocks.append(f"\nTo map it, call map_scope_area(module_name='{entry.module_name}', capability_refs=[...], "
                      "countries=[...]): it writes every item above that is available (Business-Area granularity; "
                      "the reviewer prunes lines in the workbook).")
        return "\n".join(blocks)

    def check_country_availability(scope_item_ids: list[str], countries: list[str] | None = None) -> str:
        codes, note = resolve_countries(run, countries)
        table = cat.availability(scope_item_ids, codes)
        lines = [note + "scope_item_id | " + " | ".join(codes)]
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
        StructuredTool.from_function(func=cross_map_lookup, name="cross_map_lookup", args_schema=_Lookup, handle_tool_error=True,
                                     description="Resolve a client module name through the SAP cross-mapping rulebook "
                                                 "and list the catalogue scope items it points to."),
        StructuredTool.from_function(func=catalogue_search, name="catalogue_search", args_schema=_Search, handle_tool_error=True,
                                     description="Full-text search of the SAP Best Practice catalogue; returns valid "
                                                 "Scope IDs with country availability."),
        StructuredTool.from_function(func=check_country_availability, name="check_country_availability",
                                     args_schema=_Avail, handle_tool_error=True,
                                     description="Yes/No availability of scope items in the given countries."),
        StructuredTool.from_function(func=catalogue_business_areas, name="catalogue_business_areas",
                                     args_schema=_Areas, description="LOB -> Business Area map with item counts."),
    ]


# ------------------------------------------------------------------------------ deterministic mapping
def _known_refs(run: RunContext, refs: list[str]) -> tuple[list[str], str]:
    """Keep the capability refs that exist (once the analyst has written capabilities); report the rest.
    The third live run's mapper linked items to invented ids ('cap-co-1')."""
    caps = run.ledger.load().capabilities.rows
    if not caps:
        return refs, ""
    ids = {c.row_id for c in caps}
    known = [r for r in refs if r in ids]
    unknown = [r for r in refs if r not in ids]
    note = (f"[capability_refs {unknown} do not exist and were left out; ids run {caps[0].row_id}.."
            f"{caps[-1].row_id} - see ledger_read('capabilities')]
") if unknown else ""
    return known, note


class _MapArea(BaseModel):
    capability_refs: list[str] = Field(default_factory=list, description="row_ids of the capabilities this mapping "
                                                                  "serves, e.g. ['cap-3'] (ledger_read('capabilities')).")
    module_name: str = Field("", description="A cross-mapping rulebook module name (e.g. 'Sales & Distribution (SD)', "
                                             "'Controlling (CO)'): every item its filters select is mapped.")
    lob: str = Field("", description="Instead of module_name: the catalogue LOB ...")
    business_area: str = Field("", description="... and Business Area (empty = the whole LOB).")
    description_contains: str = Field("", description="Optional: only items whose description contains this text.")
    countries: list[str] = Field(default_factory=list, description="ISO-2 codes; empty = every in-scope country.")
    status: str = Field("in_scope", description="in_scope | optional | excluded_existing")
    mapping_basis: str = Field("", description="cross_map | catalogue_search | finance_core (default from the call).")


def make_mapping_tools(run: RunContext, agent: str) -> list[BaseTool]:
    """`map_scope_area`: the old Layer 2/3 behaviour as one deterministic call. The mapper decides the
    module / Business Area (judgement); the tool writes EVERY catalogue item it selects that is
    available in the countries (no LLM transcription of 40 scope ids, no item dropped by guesswork),
    merging with rows already written. Ported from module_matcher_layer2 index selection +
    bp_mapper_layer3 (retain 100% of the baseline items, then the country-availability filter)."""
    from bidcore.catalogue.crossmap import LobBaFilter
    from bidcore.ledger.base import utcnow
    from bidcore.ledger.sections_effort import ScopeItem

    cat = run.catalogue
    sensitive = set(run.policy.catalogue.sensitive_lobs)

    def map_scope_area(capability_refs: list[str] | None = None, module_name: str = "", lob: str = "", business_area: str = "",
                       description_contains: str = "", countries: list[str] | None = None, status: str = "in_scope",
                       mapping_basis: str = "") -> str:
        status = status if status in ("in_scope", "optional", "excluded_existing") else "in_scope"
        submodule, basis = "", mapping_basis
        if module_name.strip():
            entry = cat.resolve_module(module_name)
            if entry is None:
                hints = ", ".join(s.module_name for s in cat.crossmap.suggest(module_name)) or "none"
                return f"No rulebook row named '{module_name}'. Closest: {hints}. Or give lob + business_area."
            if entry.is_others:
                return (f"'{entry.module_name}' is an 'Others' row ({entry.others_label}): it has no catalogue items - "
                        "write it with ledger_write_non_catalogue.")
            filters, submodule, basis = list(entry.filters), entry.module_name, basis or "cross_map"
        elif lob.strip():
            filters, basis = [LobBaFilter(lob.strip(), business_area.strip(), description_contains.strip())], \
                basis or "catalogue_search"
        else:
            return "Give module_name, or lob (+ business_area)."
        if description_contains.strip() and module_name.strip():
            filters = [LobBaFilter(f.lob, f.business_area, description_contains.strip(), f.component_filter)
                       for f in filters]
        basis = basis if basis in ("cross_map", "catalogue_search", "finance_core", "reviewer") else "catalogue_search"
        stats = {"added": [], "merged": [], "unavailable": [], "sensitive": []}
        codes, note = resolve_countries(run, countries)
        capability_refs, ref_note = _known_refs(run, capability_refs or [])
        note += ref_note

        def apply(ledger):
            sec = ledger.scope_items
            nums = [int(r.row_id.split("-")[-1]) for r in sec.rows if r.row_id.startswith("si-")
                    and r.row_id.split("-")[-1].isdigit()]
            next_id = max(nums, default=0) + 1
            seen: set[str] = set()
            for f in filters:
                for item in cat.expand(f, codes):
                    sid = item["scope_item_id"]
                    if sid in seen:
                        continue
                    seen.add(sid)
                    if item["lob"] in sensitive and not capability_refs:
                        stats["sensitive"].append(sid)
                        continue
                    avail = item.get("available_in", codes) if codes else []
                    if codes and not avail:
                        stats["unavailable"].append(sid)
                        continue
                    twin = next((r for r in sec.rows if r.scope_item_id == sid and r.status == status), None)
                    if twin is not None:
                        twin.countries = sorted({*twin.countries, *avail})
                        twin.capability_refs = sorted({*twin.capability_refs, *capability_refs})
                        stats["merged"].append(sid)
                        continue
                    sec.rows.append(ScopeItem(
                        row_id=f"si-{next_id}", scope_item_id=sid, lob=item["lob"], business_area=item["business_area"],
                        description=item["description"], countries=list(avail), submodule=submodule,
                        capability_refs=sorted(set(capability_refs)), mapping_basis=basis, status=status,
                        written_by=agent))
                    next_id += 1
                    stats["added"].append(sid)
            if sec.rows:
                sec.state, sec.none_reason = "written", ""
            sec.written_by = sorted({*sec.written_by, agent})
            sec.updated_at = utcnow()

        run.ledger.update(apply, actor=agent, action="map scope area", section="scope_items",
                          detail=f"{module_name or lob + ' | ' + business_area} -> {capability_refs}")
        ok = bool(stats["added"] or stats["merged"])
        run.trace.emit("ledger_write", agent, section="scope_items", rows=len(stats["added"]), mode="map_area",
                       ok=ok, saved=len(stats["added"]) + len(stats["merged"]), rejected=0, empty=False)
        target = submodule or f"{lob}{' | ' + business_area if business_area else ''}"
        if not ok:   # a mapping that writes nothing is a failure the agent must see, never "ok, added 0"
            if stats["unavailable"]:
                why = (f"none of its {len(stats['unavailable'])} catalogue item(s) is available in {codes} "
                       f"(e.g. {', '.join(stats['unavailable'][:8])}). The bid's countries are "
                       f"{bid_countries(run)}; if those are right, this area has no Best Practice content there - "
                       "map the capability to another Business Area or route it to non_catalogue.")
            elif stats["sensitive"]:
                why = "its items are in a sensitive LOB: give the capability_refs that ask for it."
            else:
                why = "the selection holds no catalogue items - check lob / business_area / description_contains."
            raise ToolException(f"{note}NOTHING MAPPED for {target}: {why}")
        parts = [f"{target}: added {len(stats['added'])} scope item(s)"
                 + (f" ({', '.join(stats['added'][:60])})" if stats["added"] else "")
                 + f", merged {len(stats['merged'])} already listed"]
        if stats["unavailable"]:
            parts.append(f"skipped {len(stats['unavailable'])} not available in {codes}: {', '.join(stats['unavailable'][:30])}")
        if stats["sensitive"]:
            parts.append(f"skipped {len(stats['sensitive'])} sensitive-LOB item(s): give capability_refs")
        return note + "; ".join(parts) + "."

    return [StructuredTool.from_function(
        func=map_scope_area, name="map_scope_area", args_schema=_MapArea, handle_tool_error=True,
        description="Map a capability to the catalogue at Business-Area / rulebook-filter granularity: writes EVERY "
                    "scope item the rulebook module (or LOB + Business Area) selects that is available in the "
                    "countries, merged with rows already written. Prefer this over typing scope ids one by one.")]


def ensure_finance_core(run: RunContext) -> list[str]:
    """Deterministic Finance-core guarantee (old module_matcher_layer2._ensure_finance_core_areas):
    whenever a Finance scope item is in scope for a country, every policy finance-core Business Area
    item available there is listed too. Runs after the agents, so a mapper that forgot it cannot
    leave the core out. Returns the scope ids it added."""
    from bidcore.catalogue.crossmap import LobBaFilter
    from bidcore.ledger.sections_effort import ScopeItem

    areas = list(run.policy.catalogue.finance_core_business_areas)
    added: list[str] = []

    def apply(ledger) -> None:
        sec = ledger.scope_items
        finance = [r for r in sec.rows if r.lob == "Finance" and r.status == "in_scope"]
        if not finance or not areas:
            return
        profile = ledger.rfp_profile.data
        bid_countries = [c.code for c in profile.countries] if profile else []
        countries = sorted({c for r in finance for c in (r.countries or bid_countries)})
        refs = sorted({ref for r in finance for ref in r.capability_refs})
        listed = {r.scope_item_id for r in sec.rows}
        nums = [int(r.row_id.split("-")[-1]) for r in sec.rows if r.row_id.split("-")[-1].isdigit()]
        next_id = max(nums, default=0) + 1
        for area in areas:
            for item in run.catalogue.expand(LobBaFilter("Finance", area), countries):
                avail = item.get("available_in", countries) if countries else []
                if item["scope_item_id"] in listed or (countries and not avail):
                    continue
                sec.rows.append(ScopeItem(row_id=f"si-{next_id}", scope_item_id=item["scope_item_id"], lob="Finance",
                                          business_area=item["business_area"], description=item["description"],
                                          countries=list(avail), capability_refs=refs, mapping_basis="finance_core",
                                          written_by="workflow", note="Finance core business area (policy)"))
                listed.add(item["scope_item_id"])
                added.append(item["scope_item_id"])
                next_id += 1

    run.ledger.update(apply, actor="workflow", action="finance core", section="scope_items")
    if added:
        run.trace.emit("finance_core", "", added=added)
    return added
