"""The two agent teams, built on the Deep Agents harness. An API activates only its own team.

  effort   (call 1)  effort-orchestrator -> rfp-analyst, scope-* (auto-discovered), catalogue-mapper,
                     wave-planner                                   => bid ledger -> effort workbook
  proposal (call 2)  proposal-orchestrator -> requirements-analyst, section-writer, reviewer
                                                                    => drafts -> YASH .docx

The orchestrator spawns its specialists with the harness's `task` tool; each specialist runs in an
isolated context (its search traces never reach the orchestrator), sees only its own skill bundle and
holds write tools for only its own ledger sections.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from deepagents import FilesystemPermission, create_deep_agent
from deepagents.backends import CompositeBackend, FilesystemBackend, StateBackend
from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import InMemorySaver

from harness import skills as skill_registry
from harness.context import RunContext
from harness.llm import chat_model
from harness.middleware import LedgerGuardMiddleware, TraceMiddleware
from harness.tools.catalogue_tools import make_catalogue_tools
from harness.tools.ledger_tools import make_orchestrator_tools, make_read_tools, make_write_tools
from harness.tools.rfp_tools import make_rfp_tools

PROMPTS = Path(__file__).parent / "prompts"

DESCRIPTIONS = {
    "rfp-analyst": "Reads the RFP for the bid profile (engagement type, in-scope countries), the inventory of SAP "
                   "capabilities per country, and the programme timeline (waves, units, durations, hypercare, "
                   "sequencing). Writes rfp_profile, capabilities, timeline.",
    "catalogue-mapper": "Maps the analyst's capabilities to SAP Best Practice scope items with the catalogue tools "
                        "and the cross-mapping rulebook; routes SAP tools with no Best Practice content to "
                        "non_catalogue with an effort band. Writes scope_items, non_catalogue. Run after rfp-analyst.",
    "wave-planner": "Decides which wave delivers which scope: tags per-country scope lines, allocates each "
                    "workstream's effort across waves, sets each wave's SAP Activate phase split and the duration "
                    "of undated waves. Writes wave_plan. Run last.",
    "requirements-analyst": "Reads the RFP for what the client wants the response to contain: required sections, "
                            "per-section RFP excerpts, and which estimation detail may be disclosed. Writes "
                            "response_requirements. Run first.",
    "section-writer": "Drafts proposal sections (figure-free Markdown with table/diagram placeholders) for the "
                      "outline section ids you assign, grounded in bid facts and RFP excerpts.",
    "reviewer": "Reviews drafts against the client's requirements, the ledger facts and the disclosure profile "
                "and records findings for the writers. At most 2 rounds.",
}


def _backend(run: RunContext) -> CompositeBackend:
    ws = run.ws
    routes = {
        "/rfp/": FilesystemBackend(root_dir=ws.rfp, virtual_mode=True),
        "/skills/": FilesystemBackend(root_dir=ws.skills, virtual_mode=True),
        "/notes/": FilesystemBackend(root_dir=ws.notes, virtual_mode=True),
    }
    if run.team == "proposal":
        routes["/drafts/"] = FilesystemBackend(root_dir=ws.drafts, virtual_mode=True)
        routes["/review/"] = FilesystemBackend(root_dir=ws.review, virtual_mode=True)
    return CompositeBackend(default=StateBackend(), routes=routes)


# Agents write files only in their scratch space; drafts go through write_draft (checked), never raw.
PERMISSIONS = [
    FilesystemPermission(operations=["write"], paths=["/notes/**"], mode="allow"),
    FilesystemPermission(operations=["write"], paths=["/**"], mode="deny"),
]


def _skill_paths(source: str, names: list[str]) -> str:
    return ", ".join(f"{source}{n}/SKILL.md" for n in names)


def _subagent(run: RunContext, name: str, role: str, skill_names: list[str], writes: list[str],
              description: str, extra_tools: list[BaseTool]) -> dict[str, Any]:
    source = skill_registry.bundle(run.ws.skills, name, skill_names)
    write_tools = make_write_tools(run, name, [s for s in writes if s not in ("drafts", "review")])
    tools = [*make_read_tools(run), *make_rfp_tools(run), *write_tools, *extra_tools]
    prompt = (PROMPTS / "specialist.md").read_text(encoding="utf-8").format(
        name=name, description=description, skill_paths=_skill_paths(source, skill_names),
        sections=", ".join(writes) or "nothing", tools=", ".join(t.name for t in write_tools + extra_tools) or "-")
    return {
        "name": name,
        "description": description,
        "system_prompt": prompt,
        "model": chat_model(role, name, run.run_model),
        "tools": tools,
        "skills": [source],
        "permissions": PERMISSIONS,
        "middleware": [LedgerGuardMiddleware(name, writes), TraceMiddleware(name, run.trace)],
    }


def _extra_tools(run: RunContext, name: str) -> list[BaseTool]:
    if name == "catalogue-mapper":
        return make_catalogue_tools(run)
    if name.startswith("scope-"):
        return [t for t in make_catalogue_tools(run) if t.name == "catalogue_search"]
    if name == "wave-planner":
        from harness.tools.effort_tools import make_effort_tools
        return make_effort_tools(run)
    if run.team == "proposal":
        from harness.tools.proposal_tools import make_proposal_tools
        return make_proposal_tools(run, name)
    return []


def team_roster(run: RunContext) -> list[dict[str, Any]]:
    """Resolve the team's subagent entries (incl. auto-discovered scope-* skills) to concrete specs."""
    roster = []
    for entry in run.team_config["subagents"]:
        if "discover" in entry:
            for skill in skill_registry.discover(entry["discover"]):
                sections = skill.ledger_sections or [skill.name.removeprefix("scope-").replace("-", "_")]
                roster.append({"name": skill.name, "role": entry["role"], "skills": [skill.name],
                               "writes": sections, "description": skill.description})
        else:
            roster.append({"name": entry["name"], "role": entry["role"], "skills": list(entry.get("skills", [])),
                           "writes": list(entry.get("writes", [])),
                           "description": entry.get("description") or DESCRIPTIONS.get(entry["name"], "")})
    return roster


def build_team(run: RunContext, client: str, instructions: str = "") -> Any:
    """The orchestrator Deep Agent for `run.team`, with its subagents registered for the task tool."""
    cfg = run.team_config
    orch = cfg["orchestrator"]
    roster = team_roster(run)
    subagents = [_subagent(run, r["name"], r["role"], r["skills"], r["writes"], r["description"],
                           _extra_tools(run, r["name"])) for r in roster]
    source = skill_registry.bundle(run.ws.skills, orch["name"], list(orch.get("skills", [])))
    tools: list[BaseTool] = [*make_read_tools(run), *make_orchestrator_tools(run)]
    if run.team == "effort":
        from harness.tools.effort_tools import make_effort_tools
        tools += make_effort_tools(run)
    else:
        from harness.tools.proposal_tools import make_proposal_tools
        tools += make_proposal_tools(run, orch["name"])
    prompt = (PROMPTS / orch["prompt"]).read_text(encoding="utf-8").format(
        client=client, skill_paths=_skill_paths(source, list(orch.get("skills", []))),
        roster="\n".join(f"- `{r['name']}`: {r['description']}" for r in roster),
        instructions=instructions.strip() or "(none)")
    run.trace.emit("team_built", orch["name"], subagents=[r["name"] for r in roster])
    return create_deep_agent(
        model=chat_model(orch["role"], orch["name"], run.run_model),
        tools=tools,
        system_prompt=prompt,
        subagents=subagents,
        skills=[source],
        backend=_backend(run),
        permissions=PERMISSIONS,
        middleware=[TraceMiddleware(orch["name"], run.trace)],
        checkpointer=InMemorySaver(),      # a coverage retry continues the same orchestrator conversation
        name=orch["name"],
    )
