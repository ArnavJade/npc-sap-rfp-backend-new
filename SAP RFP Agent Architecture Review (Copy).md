Design review · npc-sap-rfp-backend · 7 Oct 2026

# Moving the RFP agent's knowledge out of Python

The pipeline works, but it encodes every judgement as Python control flow wrapped around single LLM calls: what counts as Security scope, which section a client's ask belongs in, how two spellings of the same integration get merged. That is why each new requirement costs a module, a prompt edit and a deploy. This review traces the cause through the code and the git history, then proposes a design where SAP and proposal knowledge lives in versioned skill files, judgement runs in Claude subagents, and Python keeps only what must be exact.

## Summary

Problem

Every presales ask (a new scope area, a section rule, a dedup fix) turns into a Python change and an image build. The repo has 512 commits in ten weeks, and 65 of them touch the 4,154-line effort calculator.

Cause

The pipeline is the agent. Python fixes the order of work and decides what counts as what; Claude is called at the leaves to fill one field at a time. The knowledge behind those calls (2,700 lines of prompt text, hint chains, keyword lists, rate rules) is compiled into the service. Cutting each RFP into \~30K-character chunks then adds a merge and de-duplication layer, although the largest sample RFP is about 51K tokens and fits in one context window.

Recommendation

Keep the FastAPI service and the deterministic core. Run the **Claude Agent SDK** inside it on the current Bedrock setup. SAP and proposal knowledge moves into versioned `SKILL.md` files. Judgement runs in an orchestrator and parallel subagents. Layer 3–5 maths and rendering become tools. A validated JSON bid ledger replaces the Excel round trip as the state. An eval suite built from the real Sidel and DORABC responses gates every skill change.

What changes

A new scope area becomes a skill folder, a schema and a sheet entry. Tuning a prompt becomes a reviewed edit to a markdown file plus an eval run, with no deploy.

Decide

Whether this agent may be Claude-only, since the Agent SDK does not run non-Claude models and Neupac routes models per team. Also: who owns the skills, and moving the two endpoints to a job model. See [§10](#decisions).

1. [What I examined](#scope)
2. [How it works today](#today)
3. [Why every requirement becomes code](#diagnosis)
4. [What to keep](#keep)
5. [Target design](#design)
6. [How change requests land](#changes)
7. [Runtime options](#runtime)
8. [Risks and mitigations](#risks)
9. [Migration plan](#plan)
10. [Decisions needed](#decisions)
11. [Appendix: skill, sheet spec, wiring](#appendix)

## §1What I examined

- **Code.** All of `src/`, `utils/` and `config/`: about 22,000 lines of service code across 30 modules, plus the two public endpoints wired in `main.py` and `src/routers/pipeline.py`.
- **History.** 512 commits from 30 Jul to 5 Oct 2026 and more than 90 branches.
- **Data.** The 8 sample RFPs in `RFPs/`, the two human-written YASH responses (Sidel, DORABC), the agent's Excel outputs, and the catalogue workbooks in `static/`.
- **Platform.** `utils/llm_config.py` (per-team model chosen from the Neupac DB, called through LiteLLM), and current Anthropic documentation for the Agent SDK, Agent Skills, Managed Agents and feature availability on Bedrock.

## §2How it works today

Two endpoints are public. Call 1 turns RFP files into an effort workbook. A person reviews and edits the workbook. Call 2 takes the edited workbook and the RFP and writes the Word response. Figure 1 shows the path, and marks where SAP or proposal knowledge is written into Python.

**Figure 1. Today's two calls.** Simplified: the scope prompt's output skips Layers 1–2 and goes straight to the Excel writer, and doc-type and timeline results travel through request-scoped context variables. Six of eight call-1 stages and four of eight call-2 stages carry business knowledge as Python strings or branches.

## §3Why every requirement becomes code

The churn has a small number of structural causes. Each one below names the mechanism and points to where it shows up in the repository.

| Measure (30 Jul – 5 Oct 2026) | Value |
| --- | --- |
| Commits (non-merge) | 512 (362) |
| Non-merge commits that only bump the Helm image tag | 131 |
| Commits about prompt changes · reverts · duplicates | 29 · 9 · 14 |
| Python lines added / removed in the last 30 days | +17,052 / −3,569 |
| Commits touching `effort_calculator_layer4.py` (4,154 lines) | 65 |
| Feature flags (`*_ENABLED`) · env-driven settings in `settings.py` | 12 · 67 |

### 3.1 The pipeline is the agent; the model is a function

Every decision about the RFP is a Python branch with an LLM call at the leaf. The response outline is `STATIC_SECTIONS`, a 42-row list. Editorial guidance comes from an if-chain that returns a hint and a word target per section kind. Whether a section shows resource effort is decided by keyword matching. Because the judgement lives in code, a new ask from presales lands as code.

**document_generator_layer5.py:3697** STATIC_SECTIONS · **:2908** \_section_job_hint_and_target · **:3749** \_RESOURCE_EFFORT_CUES · **:2840–2929** Assumptions and Exclusions "were coming out too thin", fixed with two string constants and two special-case branches

### 3.2 One prompt carries seven extraction tasks

`SCOPE_EXTRACTION_PROMPT_BODY` is 617 lines (36K characters). It extracts integrations, RICEFW, Fiori, data migration, Basis, Security and Analytics in one call per chunk. Tightening one section shifts behaviour in the others, which shows up as fix and revert pairs.

**third_party_integration_extraction_layer.py:135** · **5d1ff5d** then **b4328c9** Revert, same day · **30d5ad2** "stopping overshoot" · **85ca27c**, **f67ba1f** Basis and Security constraints retuned

### 3.3 Each new scope area is shotgun surgery

Security, Basis, Data Migration and Analytics each added a 250–420-line module with the same shape: sanitise, merge, ground, total, write sheet. Each also needed edits in five other places: the mega-prompt, the merge loop that reads results by tuple position (`res[3]` … `res[6]`), the summary sheet, `resource_scope_sync.py`, the sheet-order list and the reload path. An eighth area today means repeating all of it.

**dd27ce0** Security + Analytics · **3381bdf** Basis · **8a1a74f** Data Migration · **third_party_integration_extraction_layer.py:1411–1451** positional merge

### 3.4 Chunking creates a reconciliation layer

RFPs are cut into \~30K-character chunks, each chunk is extracted separately, and the results are unioned. The team has already run into this: the chunk size was raised from 10 to 50 pages as an "EXPERIMENT (Sidel country-leak)" so related statements would "land in the SAME chunk … instead of being unioned in from isolated chunks". Downstream, the non-catalogue list goes through LLM effort estimation, LLM reclassification, LLM within-section dedup, cross-list dedup and scope-sheet dedup: about 1,200 lines. Figure 2 shows how small the inputs actually are.

**config/settings.py:155, :171** · **effort_calculator_layer4.py:1250–2440** · **291fdec** "two-word verification" · **762d09a**, **f341270** cross-list dedup

**Figure 2. Every sample RFP fits in one context window.** Text extracted from the sample files in `RFPs/` (paragraphs and tables, before OCR). The current Claude Sonnet and Opus models accept 1M tokens, about 20 times the largest RFP. Sidel also carries 76 embedded images; their OCR text adds to the total but does not change the conclusion.

### 3.5 State is smuggled instead of modelled

Route and helper signatures are treated as frozen, so new facts (document type, project timeline) travel through request-scoped context variables instead of parameters. Between call 1 and call 2 the only state is the workbook, so 835 lines read rounded display strings back into objects and then apply precedence rules (Excel over RFP over derived) to decide which value wins.

**pipeline.py:621** "its signature is frozen" · **rfp_type_classifier.py:116**, **project_timeline_extraction_layer.py:1328** ContextVar · **pipeline.py:1306–1358** reload and precedence

### 3.6 Nothing measures output quality

The 295 unit tests check code paths against mocked LLM output. None of them scores an end-to-end response against a human one, so regressions are found by accident. `pyproject.toml` pins litellm, openai and tiktoken because bumping them "changed LLM narrative sub-heading output (fewer sub-sections, \~20 fewer pages)". The repo already holds what a gold set needs: two real YASH responses and the reviewed agent workbooks.

### 3.7 Prompt edits are deployments

131 of 362 non-merge commits are Helm image-tag bumps. A prompt is a Python string inside the image, so a one-word wording change takes the same path as a code change.

|  | What the code does | Lines | In the new design |
| --- | --- | --- | --- |
|  | Prompt text: module-level prompt and hint strings | 2,731 | Moves into skills, largely verbatim |
|  | LLM plumbing: call, parse, salvage, sanitise, merge, dedup, ground, reclassify, verify, harmonize | 4,574 | Mostly removed; evidence grounding survives as a hook |
|  | Excel reload: rebuilding state from the reviewed workbook | 835 | Removed; edits come back as a ledger diff |
|  | Rendering: workbook writer, docx tables, diagrams, styling | 3,644 | Kept as tools; layouts move to YAML specs |
|  | Domain logic and glue: effort maths, resource grid, timeline, BP mapping, orchestration | 10,209 | Maths kept as tools; orchestration glue removed |

**Figure 3. Where the 22,000 lines go.** Heuristic split by function and constant name across `src/services`, `src/aperture` and `src/routers/pipeline.py`; treat each share as ±10 points. About a third of the code is prompt text or exists to call the model and repair its output.

## §4What to keep

This is not a rewrite of everything. These parts do work an LLM should not do, and they carry rules the team learned the hard way:

- **Catalogue mapping and country availability** (Layer 3) over `BP_ID_LIST` (447 rows), `BP_Efforts` (430 rows) and the cross-mapping sheet (61 rows).
- **Effort and cost maths**: rate-card lookups, complexity factors, the PM overhead cap (`515b23e`), hypercare rates, 0.5-FTE rounding (`0a50eda`), resource-grid reconciliation. The model must never type a client-facing number.
- **Rendering**: the workbook writer with live formulas, the YASH docx template, tables and diagrams.
- **Evidence grounding** (`CorpusIndex` in `data_migration_scope.py`), which becomes a check inside `ledger.write`.
- **Platform glue**: SharePoint, the Activity API, per-team model config, KMS, Helm.
- **The 2,700 lines of prompt text.** It is the best SAP presales knowledge the team has written down. It moves into skills almost as-is.

What changes is the packaging. The maths and rendering become tools with typed inputs, and their parameters (rates, caps, effort bands, sheet layouts) move from Python constants into YAML policy files.

## §5Target design

One rule decides where each piece goes: **Python does what must be exact, Claude does what needs judgement, and knowledge lives in files people can edit.**

**Figure 4. Components.** Knowledge lives in two folders outside the code: `skills/` for judgement and `policy/` for numbers and layouts. Claude agents read skills and call tools. Python stays deterministic. Agents also use the SDK's built-in Read and Grep on `rfp/`.

### Runtime

The **Claude Agent SDK** (Python) inside the existing FastAPI service. It provides the agent loop, skills loaded from `SKILL.md` files, subagents with their own model, tools, skills and effort, in-process tools via `@tool`, hooks, validated structured output, and spend caps (`max_budget_usd`, subagent depth and concurrency limits). It runs the Claude Code binary as a subprocess. It talks to Bedrock with `CLAUDE_CODE_USE_BEDROCK=1`, or through a gateway that exposes the Bedrock or Anthropic Messages format.

### Bid ledger

One JSON document per bid, with a schema per section: scope items, integrations, RICEFW, Fiori, data migration, Basis, Security, Analytics, timeline, and the client's response requirements. Every row carries an evidence quote and a page. Agents write only through `ledger.write`, which validates the schema, checks the quote exists in the RFP and flags overlaps with other sections. The Excel workbook and the Word response are both views of the ledger.

### Skills

Skills are folders of markdown that Claude loads when a task needs them. They are owned by the SAP practice and presales, reviewed like code, and versioned separately from the service.

| Skill | Contains | Replaces today |
| --- | --- | --- |
| `rfp-reading` | How to read an SAP RFP: scope matrices, in-scope, optional and out-of-scope language, embedded image and table blocks, hypercare idioms ("44 weeks including 12 weeks hypercare") | Prompts in Layer 0, the timeline layer and the doc-type classifier |
| `sap-scope-mapping` | Mapping a client capability to LOB, Business Area and scope items with the catalogue tool; cross-mapping and "SAP module without Best Practice" rules | Layers 1–2 prompts and batching, `classifier.py` |
| `scope-integrations`, `scope-ricefw-fiori`, `scope-data-migration`, `scope-basis`, `scope-security`, `scope-analytics` | One per workstream: what qualifies, what never does, the evidence rule, one row per capability, complexity and effort bands, which ledger section to write | Sections A–G of the 617-line scope prompt, and the per-area sanitise and merge modules |
| `estimating` | How to drive `effort.compute` and read its output; never state a number a tool did not return | Rules scattered across Layer 4 and 5 prompts |
| `proposal-outline` | The YASH response outline as an editable file (today's 42 sections), per-section guidance and word budgets, rules for adding client-required sections and where to anchor them | `STATIC_SECTIONS`, the hint chain, `_ASSUMPTIONS_HINT`, `client_requirements_layer5.py` |
| `proposal-writing` | YASH voice, reference files per section, boilerplate (profile, service catalogue), table and diagram placeholders | `SECTION_SYSTEM_PROMPT`, per-kind hints, the harmonization prompt |
| `bid-review` | Requirement-coverage audit, numbers against the ledger, unsupported claims | The requirement-verification prompt, `evaluator.py` |

### Agents

Model choices are a starting point to be settled by the evals in [§9](#plan), within whatever the team's model config allows.

| Agent | Reads | Writes | Starting model |
| --- | --- | --- | --- |
| Orchestrator | RFP index, ledger, skill list | Plan, delegations, run status | Opus 5.5, high effort |
| RFP analyst | Whole RFP | Countries, modules, timeline, client response requirements | Sonnet 5.5 |
| Scope extractor ×7 | Whole RFP, one `scope-*` skill each | Its own ledger section | Sonnet 5.5, medium effort |
| Catalogue mapper | Ledger modules, catalogue tool | Scope items with BP IDs | Sonnet 5.5 |
| Section writer ×N | One outline entry, ledger facts, RFP excerpts | `drafts/<section>.md` with table placeholders | Sonnet 5.5 |
| Reviewer | Drafts, ledger, client requirements | Findings; sends sections back, at most 2 rounds | Opus 5.5 |

### Tools

- `catalogue.search`, `catalogue.get`, `catalogue.cross_map` over the three static workbooks.
- `ledger.read`, `ledger.write` with schema, evidence and overlap checks. Rejections come back as tool errors, so the agent fixes the row itself.
- `effort.compute(group_by=…)` for module, wave, country or role views. Deterministic; reads `policy/*.yaml`.
- `workbook.render` from sheet specs, and `workbook.read_edits`, which returns the reviewer's changes as a ledger diff.
- `docx.render` on the YASH template; fills `{{table:…}}` and `{{diagram:…}}` placeholders from the ledger, so writers never type figures.

### Hooks and limits

- **Before a tool runs:** writes only inside the run's workspace; no network except the SharePoint tools.
- **On stop:** every number in `drafts/` must appear in the ledger or in `effort.compute` output, or the run continues with the list of mismatches. This replaces the number guard in harmonization.
- **Caps:** `max_budget_usd` per run, subagent depth 1, concurrency sized to the Bedrock quota.
- **Trace:** the SDK message stream is stored with the workspace. One transcript shows every delegation, tool call and ledger write, replacing the `[*-TRACE]` log tags.

### How a run works

**Figure 5. The same two calls, redesigned.** Laid out on the same grid as Figure 1. The chunker and the merge-and-dedup stage are gone because each extractor reads the whole RFP once. The Excel reload is gone because the ledger persists between calls. Every figure in the response comes from a tool.

Three things remove code instead of moving it:

- Each scope extractor reads the whole RFP once with its own skill, so there is nothing to merge across chunks. Overlap between workstreams (GRC under Security and under non-catalogue tools, for example) becomes one ledger check rather than five dedup passes.
- Call 2 applies the reviewer's edits as a diff to the same ledger, so nothing is rebuilt from display strings and there are no precedence rules to maintain.
- Section structure, guidance and client-required sections come from the outline skill, so the hint chain and its special cases go away.

## §6How change requests land

These are real requests from the git history, replayed against both designs.

| Request | Today | In the new design |
| --- | --- | --- |
| Add Security and Analytics detection dd27ce0 | Two new modules (251 and 298 lines), sections F and G in the mega-prompt, edits to the merge loop, summary sheet, resource sync, sheet order and reload path, image build | Two skill folders, two ledger schemas, two entries in `workbook.yaml`, eval cases. No image build. |
| Fix Basis scope detection 85ca27c | Edit a Python string, build and deploy the image | Edit `skills/scope-basis/SKILL.md`; CI runs the evals; the skill bundle syncs |
| Assumptions section too thin | Two string constants and two special-case branches in the hint chain | Edit `proposal-outline/sections/3.4-assumptions.md` |
| Client asks for a wave-wise effort table | A new requirement kind, a new generator (`generate_indicative_breakdown`) and anchoring rules | The writer calls `effort.compute(group_by="wave")` and inserts a table placeholder. No code if the tool already supports the dimension. |
| Duplicate tools across lists 762d09a, 291fdec, f341270 | Three more dedup passes and a two-word matching heuristic | Mostly does not arise; `ledger.write` flags cross-section overlaps for the orchestrator to resolve |
| Cap PM overhead at 15%/20% 515b23e | Code change in Layer 4 | Value change in `policy/commercials.yaml`; code only for a new kind of formula |

Code still changes for new deterministic calculations, new output formats (a PowerPoint summary, say), new systems to connect, and changes to a tool's interface. Those should be a small share of the requests.

## §7Runtime options

The deciding constraint is the platform. The service calls Claude through Bedrock, and on Bedrock the Messages-API Agent Skills, code execution, Managed Agents, Files API, Batches and MCP connector are not available. A design that needs skills today on Bedrock has to load them client-side, which is what the Agent SDK does.

|  | A. Agent SDK on Bedrock recommended | B. Own harness on LiteLLM or the Anthropic SDK tool runner | C. Claude Platform on AWS with Managed Agents |
| --- | --- | --- | --- |
| Skills as files | Built in; loaded on demand | You write the loader and a read-skill tool | Built in, uploaded through the Skills API |
| Subagents and parallelism | Built in, with per-agent model, tools, skills and effort, plus depth, concurrency and spend caps | You build and maintain it | Multiagent sessions |
| Runs on today's Bedrock setup | Yes | Yes | No; needs the Anthropic-operated Claude Platform on AWS |
| Non-Claude models from the Neupac DB | No; Anthropic does not support routing it to other models | Yes, through LiteLLM | No |
| Where it runs | Your container; runs the Claude Code binary as a subprocess; needs a writable workspace | Your container | Anthropic-hosted sandbox per session |
| Code you own | Tools, hooks, job runner | Tools, hooks, job runner, agent loop, skill loader, subagent orchestration, context management | Tools and the client |
| Fit | Best fit now | Fallback if the platform requires model-agnostic agents | Revisit later; most managed, largest governance change |

## §8Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Run-to-run variation | Every number comes from a tool, and the ledger schema constrains shape. Evals run each case three times and track variance, not only the mean. |
| Skill edits cause regressions | Skills are code by another name. Keep them in a repo with owners and pull-request review, gate merges on the eval suite, pin a skill bundle version per environment, and roll back by version. |
| Longer runs | A full run with fan-out can take tens of minutes. Both endpoints become jobs: submit, poll status, upload to SharePoint, emit the existing Activity API event on completion. |
| Cost | Rough estimate for the largest sample RFP: about 2–3M input and 200K output tokens across all agents, which is roughly $5–15 per run at list API prices. Bedrock pricing differs. Cap each run with `max_budget_usd`. |
| Platform model routing | Neupac selects models per team through LiteLLM; the Agent SDK is Claude-only. Agree with the platform team that this agent is Claude-only, map the team's config to SDK settings at run start, and fail fast with a clear message if it names a non-Claude model. If gateway logging is required, put LiteLLM in front in the Bedrock or Anthropic format and forward beta headers and body fields unchanged. |
| Container | The SDK ships a native binary. Confirm the ARM64 build works in the Graviton image and check image size during the first spike. |
| Debugging | Store the full transcript with each run's workspace; it shows every delegation, tool call and rejected ledger write in order. |

## §9Migration plan

Replace the pipeline in stages, with the old path running beside the new one until the evals say otherwise. Each phase ends on a check, not a date.

| Phase | Work | Done when |
| --- | --- | --- |
| 0 · Measure | Build the eval harness and gold set from the 8 sample RFPs, the Sidel and DORABC responses and the reviewed workbooks. Metrics: scope-item precision and recall against reviewed Excel; row recall per workstream; effort difference per workstream; client-requirement coverage (LLM judge with a rubric, seeded from `evaluator.py`); evidence-grounding rate; number consistency. Baseline today's pipeline. | One command scores any run, and the baseline is recorded. Worth doing whatever else is decided. |
| 1 · Extract the core | Put Layer 3–4 maths, the workbook writer, the docx renderer and catalogue access behind tool interfaces. Define the ledger schemas. Move rates, caps and sheet layouts to YAML. Lift the existing prompts into skills, splitting the 7-area prompt into 7 skills. | Tools have unit tests, and the current pipeline runs on them unchanged. |
| 2 · Call 1 on agents | Agent SDK runtime for RFP → ledger → Excel behind a flag, shadow-run on every RFP beside the current pipeline. | Evals at or above baseline on scope recall and effort difference; ARM64 container and Bedrock quotas confirmed. |
| 3 · Call 2 on agents | Outline skill, section writers, reviewer, numbers hook, docx render from ledger plus edit diff. | Coverage and consistency at or above baseline; presales signs off on three live bids. |
| 4 · Cut over and delete | Remove Layers 0–2, the non-catalogue dedup and reclassify chain, the hint chain, the Excel reload and the per-area modules. Skills ship from their own repo through the eval gate, without image builds. | A presales SME adds a new scope area with no Python change. |

## §10Decisions needed

01

**Claude-only for this agent?** The Agent SDK runs only Claude models. If Neupac must be able to swap this agent to another provider, choose option B and own the harness.

Platform team

02

**Bedrock now, Claude Platform on AWS later?** Staying on Bedrock keeps today's data path. Moving would unlock hosted skills, code execution and Managed Agents, at the cost of a data-governance review.

Infrastructure and security

03

**Who owns the skills?** Name an owner per skill in the SAP practice or presales, and decide who approves changes alongside the eval gate.

Presales lead, engineering lead

04

**Job-based endpoints.** Both calls become submit-then-poll jobs, with completion reported through the Activity API. The calling UI needs to handle that.

Platform UI team

05

**Feature freeze on the old path.** During phases 1–3, limit the current pipeline to bug fixes, or land new asks only as skills and policy entries.

Engineering lead

## AAppendix: skill, sheet spec, wiring

A worked example for the Security workstream, built from section F of today's prompt (`third_party_integration_extraction_layer.py:576–626`) and the layout in `security_scope.py`. These are sketches, not tested code.

### skills/scope-security/SKILL.md

```
---
name: scope-security
description: Extract the SAP Security workstream (roles and authorisations, SoD,
  GRC Access Control / Cloud IAG, SSO and identity, data-access restrictions) from
  an SAP RFP into the bid ledger. Use when building the effort estimate.
---

# SAP Security scope

## What counts
Role and authorisation design and build (S/4HANA, Fiori, SAP cloud apps), user
provisioning, Segregation of Duties, SAP GRC Access Control or SAP Cloud Identity
Access Governance, GRC Process Control / Risk Management, single sign-on and
identity (SAP Secure Login Service, SAP Cloud Identity Services), restricting data
access by entity or org unit, and security testing through hypercare.

## Never Security
Basis tasks (system setup, transports, certificates, backups), network or cyber
security, "the solution must be secure", functional approval workflows (Ariba,
SuccessFactors, purchasing), legal or financial compliance (audit, IFRS, tax).

## Rules
- Evidence: list an activity only when the RFP states it or puts its SAP product
  in scope. Quote the exact words and the page.
- One row per capability: a product in a licence list and its implementation
  described elsewhere are one row.
- A heading that groups activities is not an activity.
- Out of Scope when the RFP gives it to the client's IT team, another vendor or
  the hosting provider.

## Effort guide (man-days, whole numbers, illustrative)
| Activity                                   | Range |
|--------------------------------------------|-------|
| Single sign-on setup                       | 3-8   |
| Role design and build, multi-entity S/4    | 15-40 |
| GRC Access Control / Cloud IAG             | 20-40 |
| GRC Process Control                        | 30-60 |
| Table-level data restriction               | 10-25 |

## Output
Call ledger_write(section="security", rows=[...]) with
activity, sap_product, status, evidence, page, complexity, effort_days.
Fix any row the tool rejects. Never drop a rejected row silently.
```

### policy/workbook.yaml (one entry)

```
- sheet: Security Scope
  title: SAP Security Scope (Effort in Man Days)
  source: ledger.security
  columns:
    - {header: Activity, field: activity, width: 60}
    - {header: In Scope / Out of Scope, field: status, width: 20, list: [In Scope, Out of Scope]}
    - {header: Complexity, field: complexity, width: 14, list: [Low, Medium, High]}
    - {header: Effort (in Mandays), field: effort_days, width: 20}
    - {header: Total, formula: '=IF($B{r}="In Scope",N(D{r}),0)', width: 14}
  total_row: true
  summary_link: {label: Security, column: Total}
  resource_role: GRC Consultant
```

### Wiring: one extractor per scope skill folder

Adding a `scope-*` folder adds a workstream without touching this code.

```
from pathlib import Path
from claude_agent_sdk import AgentDefinition, ClaudeAgentOptions, create_sdk_mcp_server, query

from bid_tools import catalogue_search, ledger_write, effort_compute, workbook_render  # today's Layer 3-4 code behind @tool


def scope_agents(skills_dir: Path) -> dict[str, AgentDefinition]:
    agents = {}
    for skill_md in sorted(skills_dir.glob("scope-*/SKILL.md")):
        name = skill_md.parent.name
        agents[name] = AgentDefinition(
            description=f"Extracts the {name.removeprefix('scope-')} workstream from the RFP into the bid ledger.",
            prompt="Read the whole RFP in rfp/. Follow your skill. Write rows only with ledger_write.",
            skills=[name],
            tools=["Read", "Grep", "mcp__bid__ledger_write", "mcp__bid__catalogue_search"],
            model="sonnet",
            effort="medium",
        )
    return agents


options = ClaudeAgentOptions(
    cwd=run_dir,                       # the bid workspace; .claude/skills is synced into it
    setting_sources=["project"],
    skills="all",
    agents={**scope_agents(run_dir / ".claude" / "skills"), **core_agents},
    mcp_servers={"bid": create_sdk_mcp_server(
        name="bid", version="1.0.0",
        tools=[catalogue_search, ledger_write, effort_compute, workbook_render],
    )},
    allowed_tools=["Read", "Grep", "Glob", "Agent", "Skill", "mcp__bid__*"],
    hooks=guardrail_hooks,             # workspace-only writes; numbers must match ledger on Stop
    max_budget_usd=25.0,
    env={"CLAUDE_CODE_USE_BEDROCK": "1", "CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH": "1"},
)
```

**Sources.** Repository `npc-sap-rfp-backend` at `a425f70` (branch `feature/litellm-version`), its git history, and the files in `D:\SAP-T\RFPs`. Anthropic documentation: [Agent SDK overview](https://code.claude.com/docs/en/agent-sdk/overview), [skills](https://code.claude.com/docs/en/agent-sdk/skills), [subagents](https://code.claude.com/docs/en/agent-sdk/subagents), [custom tools](https://code.claude.com/docs/en/agent-sdk/custom-tools), [structured outputs](https://code.claude.com/docs/en/agent-sdk/structured-outputs), [gateway compatibility](https://code.claude.com/docs/en/llm-gateway-protocol), and the Claude API feature-availability table for Amazon Bedrock. Line counts and commit counts were measured on 7 Oct 2026; the code breakdown in Figure 3 is heuristic.