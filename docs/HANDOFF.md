# Handoff — SAP RFP Agent PoC on Deep Agents (as of 2026-10-08)

Read with `docs/IMPLEMENTATION_PLAN.md` (original plan, Claude-Agent-SDK based). This file records how the
PoC **deviates** from that plan, what exists, and what is left.

- New repo (this one): `C:\Users\arnav.jade\Desktop\NPC SAP Agent\npc-sap-rfp-backend-new`
- Old agent (read-only source to port from): `..\clone\npc-sap-rfp-backend` (branch `npc-dev` @ `67b88e6`).
  The plan was written at `0850ab3`; since then `wave_attribution_layer4.py` (820 lines) was added and
  `project_timeline_extraction_layer.py` / `resource_grid_layer4.py` changed — plan line numbers for those are stale.
- Env: `.venv` (Python 3.12, created with uv, all deps from `pyproject.toml` installed, editable install).
  Run tests: `.venv/Scripts/python.exe -m pytest tests -q`. Keep venvs on short paths (Windows MAX_PATH broke
  langsmith imports from a long temp path).
- Sample inputs for testing: `C:\Users\arnav.jade\Downloads\ARASCO SAP S4HANA RISE AMENDED  RFP V_4.5.pdf`,
  `ABC_SystemImplementation_RFP_2022 2.docx`; current-layout reference output
  `Claude_BP_Effort_Output_ARASCO_20261006_071733_Summary.xlsx` (same folder).

## Decisions agreed with the user (override the plan)

| Topic | Decision |
|---|---|
| Harness | **Deep Agents** (LangGraph), not Claude Agent SDK. Models via **LiteLLM** (`langchain-litellm` `ChatLiteLLM`). No model fixed yet — user will set `LLM_MODEL` later (Gemini 3.8 Flash / Claude Sonnet 5 on Bedrock). Tests use scripted fake models. |
| Orchestration | Raw LangGraph outer state machine (deterministic order); Deep Agents only in the `agents` node. |
| Spawning | Each API has its own **orchestrator Deep Agent** which spawns specialists with the harness **`task` tool** (isolated contexts). Code checks coverage afterwards and sends the orchestrator back for missing sections (max `coverage_retries`). Built-in general-purpose subagent disabled. |
| Team separation | Call 1 activates only the **effort team**; call 2 only the **proposal team** (`policy/runtime.yaml teams`). |
| RFP context | Shared workspace read on demand: `/rfp/index.md` + page-marked `/rfp/<file>.md`; agents use grep/read_file/`read_section`. No whole-document prompts, no chunking. |
| Calls | Two calls + human review: (1) RFP → ledger → effort workbook; (2) reviewed workbook (+RFP) → diff via hidden `_bid` sheet → ledger → YASH .docx. |
| Wave effort | **Agent allocates, tools compute**: `wave-planner` writes `ledger.wave_plan` (item tags, per-workstream wave shares, per-wave phase split starting from SAP Activate .08/.18/.50/.14 relative, durations for undated waves); deterministic code turns it into person-days/FTE (largest remainder, exact sums). Replaces old heuristic `wave_attribution_layer4`. |
| PDF parsing | `pymupdf4llm` default, pluggable (`INGEST_PDF_ENGINE=docling` optional extra). **AGPL licence — review before production.** |
| Workbook | **Full parity** with today's sheets (Summary of Project Effort, Functional Scope Estimation, Project Timeline grids+reconciliation, one sheet per LOB, Non Catalogue SAP Tools, Tech Dev Scope, Data Migration per wave, Basis, Security, Analytics) + hidden `_bid`. Written directly by an openpyxl filler ported from the old writers (the prototype-row template idea was dropped: the old sheets are too heterogeneous). No agent-driven file editing. |
| Word | **Full 42-section outline**, `docxtpl` template derived from `YASH_RFP_Template.docx`; narrative sections drafted in parallel by `section-writer` subagents as figure-free Markdown with `{{fig:..}}/{{table:..}}/{{diagram:..}}` placeholders resolved from the ledger. |
| Rate card | Sum all 5 phases (old behaviour); the SAP BP sheet's own Total formula omits UAT — deliberately ignored. |
| Platform | **Keep SharePoint (upload session > 4 MB) + Activity API.** Drop team model-config DB, KMS, S3 (local storage under `workspace/bids/<bid_id>/`). |
| Temperature | `null` = provider default (Gemini 3.x loops at low temperatures). |

## State (2026-10-08, branch `claude/keen-ride-iyeyve`)

All development items are done and the old agent (npc-dev @ 67b88e6, provided as a zip) has been
ported where the plan said "port". Full suite: 157 tests pass (incl. LibreOffice recalculation of the
workbook formulas). Data correctness has not been reviewed (see open items).

| Area | Where | State |
|---|---|---|
| Ingestion | `bidcore/ingest/{pdf,office,workspace}.py` | PDF/DOCX/PPTX/XLSX/CSV/TXT/MD -> `rfp/<slug>.md` with `<!-- page: N -->`, `index.md` (outline, tables, wave anchors, 3rd-party candidates) rebuilt from all files, `read_section`, `list_pages`, caption cache, `cache/prescan.json` |
| Sizing | `bidcore/sizing.py` | honours reviewer overrides: catalogue phase cells / factor / wave / deletions, Tech Dev edits / deletions / additions, Summary %/rates, hypercare, grid FTE cells |
| Workbook | `bidcore/render/workbook/{layout,filler,manifest}.py` | old layout cell for cell (`write_effort_workbook`, `*_scope.py` writers, Resources sheet + reconciliation); additions: hidden row-id columns, hidden `_bid`, rates + Total Project Cost row on the Summary; manifest `ledger/manifest-<render_id>.json`; `read_edits` (by row id, skips band/subtotal rows) + `apply_overrides` |
| Docx | `bidcore/render/docx/` | YASH template (cover tokens, TOC refresh, heading-indent fix); old table builders (per-LOB functional scope, module-wise effort, delivery waves + landscape month grids / phase-skill fallback, combined staffing, role roster, cost, RACI); column-level disclosure + old header-cue filter for writer tables (`bidcore/disclosure.py`); matplotlib diagrams (not the old SVG renderer) |
| Outline | `bidcore/outline.py` | client-required placement rules, `additional` section, resource/effort combine flip |
| API / UI / CLI | `src/app/`, `ui/streamlit_app.py`, `scripts/run_local.py`, `Dockerfile` | jobs, bid routes, platform routes (SharePoint + Activity), UI over HTTP, local runner |
| Observability | `src/harness/observability.py`, `harness/context.py` (Trace), `harness/middleware.py` (TraceMiddleware), `workflows/common.py` (`staged`), `scripts/trace_view.py` | context-stamped logging (bid/stage/agent), per-bid `trace/` (events, errors, llm_calls, run.log), summaries; API `/bids/{id}/trace`, `/trace/summary`, `/logs`; README section 5 |
| Skills | `skills/` | ported from the old prompts: six `scope-*` (sections A-G + per-area rules), client-requirements (requirements/excerpts, disclosure, steering), bid-review (verification gate, cost-gap, harmonisation, evaluator), proposal-writing references (indicative breakdown, phase plan, integrations); rfp-reading / sap-scope-mapping / proposal-outline ported earlier; estimating / wave-planning are new (no old equivalent) |
| Ledger | `bidcore/ledger/sections_effort.py` | DM rows carry the RFP area (`module`), analytics rows `sap_product`; DM sheet label = old `module - domain - object` |

Decisions taken in this session
- YASH profile: the model may describe YASH qualitatively; specific claims (numbers, named
  clients, partner tiers, certifications, offices) are banned unless RFP/presales supply them.
- Disclosure defaults to withheld per category (old rule).
- The old hidden 'Pipeline Data' sheet and the LLM-deduced BP ids for non-catalogue items are not
  ported (call 2 reads the ledger; the non-catalogue BP-ID column shows "-").

## Open items
1. **Data correctness (not reviewed, by request).** Observed on the fixture bid:
   - scope sync more than doubles small workstreams (Security 35 -> 74 PD, Data Migration 52 -> 127
     PD) because off-grain category cells are rounded UP to 0.5 FTE in every month - the old
     `resource_scope_sync` does the same (`math.ceil`), so this is faithful old behaviour;
   - programme roles (Program / Project Manager, Solution Architect ...) end up with FTE only in the
     hypercare months on a small bid: the 8 % management envelope spread over many roles and months
     rounds to 0 at the 0.5 grain.
   Compare against the ARASCO reference workbook before trusting totals.
2. Live smoke run once `LLM_MODEL` is set (check Gemini tool-schema handling of nested/nullable fields).
3. Not built: evals (`evals/`), helm/CI; diagrams are matplotlib, not a port of `layer5_diagrams.py`.

## Gotchas
- `tests/platform` would shadow stdlib `platform` -> use `tests/platform_glue`.
- `deepagents` SubAgent `tools` must always be given (otherwise parent tools are inherited); `skills` sources are
  directories containing skill folders (hence per-agent bundles).
- Ledger write tools are per-section closures `ledger_write_<section>`; `delete_rows` restricted to own sections.
- Proposal `write_draft` is the only way to write `/drafts/` (filesystem permissions deny raw writes outside `/notes/`).
- The template's Heading 2 numbering carries a 10216-twip indent; the docx builder pins heading indents.
- A non-editable install needs `ASSETS_DIR`/`POLICY_DIR`/`SKILLS_DIR` (set in the Dockerfile).
