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
| Workbook | **Full parity** with today's 11 sheets (Summary of Project Effort, Functional Scope Estimation, Project Timeline grids+reconciliation, one sheet per LOB, Non Catalogue SAP Tools, Tech Dev Scope, Data Migration per wave, Basis, Security, Analytics) + hidden `_bid`. Built from a static `template.xlsx` (styles/headers/static formulas/prototype rows) + a small openpyxl filler. No agent-driven file editing. |
| Word | **Full 42-section outline**, `docxtpl` template derived from `YASH_RFP_Template.docx`; narrative sections drafted in parallel by `section-writer` subagents as figure-free Markdown with `{{fig:..}}/{{table:..}}/{{diagram:..}}` placeholders resolved from the ledger. |
| Rate card | Sum all 5 phases (old behaviour); the SAP BP sheet's own Total formula omits UAT — deliberately ignored. |
| Platform | **Keep SharePoint (upload session > 4 MB) + Activity API.** Drop team model-config DB, KMS, S3 (local storage under `workspace/bids/<bid_id>/`). |
| Temperature | `null` = provider default (Gemini 3.x loops at low temperatures). |

## State (2026-10-08, branch `claude/keen-ride-iyeyve`)

Development of every component on the "what is left" list is done. Tests exist for each part but the
last round was written without being re-run (on request: finish development first, then test).
Data correctness has not been reviewed.

| Area | Where | State |
|---|---|---|
| Ingestion | `bidcore/ingest/{pdf,office,workspace}.py` | done: PDF/DOCX/PPTX/XLSX/CSV/TXT/MD -> `rfp/<slug>.md` with `<!-- page: N -->`, `index.md` (outline, tables, wave anchors, 3rd-party candidates) rebuilt from all files, `read_section`, `list_pages`, caption cache, `cache/prescan.json` |
| Sizing | `bidcore/sizing.py` | honours reviewer overrides: catalogue phase cells / factor / wave / deletions, Tech Dev edits / deletions / additions, Summary %/rates, hypercare setting, grid FTE cells |
| Workbook | `bidcore/render/workbook/` | layout registry (`layout.py`), template builder + `assets/templates/template.xlsx` (`scripts/build_templates.py`), filler with live formulas, hidden row-id columns, hidden `_bid`; manifest `ledger/manifest-<render_id>.json`; `read_edits` (by row id) + `apply_overrides` |
| Docx | `bidcore/render/docx/` | python-docx on `YASH_RFP_Template.docx` (cover tokens incl. text boxes/TOC, `updateFields`, heading-indent fix), Markdown -> Word, ledger tables, matplotlib diagrams (timeline, methodology, architecture), disclosure filtering, red marker for missing drafts. Uses python-docx, not docxtpl (closer to the old generator) |
| Outline | `bidcore/outline.py` | client-required placement rules from the proposal-outline skill (`<anchor>.<n>`, 4.3/6.1 fallbacks, `additional`) |
| API | `src/app/` | `main.py`, `jobs/{store,runner}.py`, `api/bids.py` (`/bids`, `/bids/{id}/proposal`, `/proposals`, `/jobs/{id}`, ledger/file downloads), `api/platform.py` (`/pipeline/match/effort`, `/pipeline/generate/from-excel`, SharePoint + Activity, old body with `?wait=true`), `services.py` |
| UI | `ui/streamlit_app.py` | call 1, call 2, bid list over the HTTP API (`API_URL`) |
| CLI | `scripts/run_local.py` | `effort` / `proposal` without the API, live progress |
| Container | `Dockerfile` | API image; UI runs from the same image |
| Skills | `skills/` | all referenced skills exist: rfp-reading, sap-scope-mapping (ported earlier); estimating, wave-planning, client-requirements, bid-review, proposal-writing references (new); six `scope-*` skills **0.1.0-draft, not ported** (see open items) |
| Tests | `tests/` | ingest, render (LibreOffice recalculation check), harness e2e for both calls with scripted models, API (both calls + platform routes), timeline, resourcing |

Decisions taken in this session
- YASH profile: the model may describe YASH qualitatively; specific claims (numbers, named
  clients, partner tiers, certifications, offices) are banned unless RFP/presales supply them.
- Disclosure defaults to withheld per category (old rule); `resource_location` drops only the
  Location column, not the role roster.
- RACI table ported from the old generator (5 roles, one A per row, no per-module rows).

## Open items
1. **Port from npc-dev** (old repo not yet accessible here; `ArnavJade/sap-backend` is an early
   2-Sep snapshot without the needed files): the six `scope-*` skills (sections A-G of
   `third_party_integration_extraction_layer.py:170-676`, plus `*_scope.py`), client-requirements
   (`client_requirements_layer5.py`), bid-review (generator verification prompts), and workbook
   layout parity (old writers in `effort_calculator_layer4.py`). Layout changes stay inside
   `render/workbook/layout.py` + `template_builder.py` + `filler.py`.
2. **Scope-sync inflation (data correctness, not fixed):** on the fixture bid, scope sync raises
   Security 35 -> 74 PD and Data Migration 52 -> 127 PD, because step 1 rounds every off-grain
   category cell UP to 0.5 FTE across all wave months and the tables are then moved up to the grid.
   Compare with the ARASCO reference workbook before deciding whether this is old behaviour.
3. Run the full test suite (`.venv/Scripts/python.exe -m pytest tests -q`); the last batch of edits
   (resourcing/timeline tests, run_local, Dockerfile) was not executed.
4. Live smoke run once `LLM_MODEL` is set (check Gemini tool-schema handling of nested/nullable fields).
5. Not built: evals (`evals/`), helm/CI, S3/KMS (dropped by decision).

## Gotchas
- `tests/platform` would shadow stdlib `platform` -> use `tests/platform_glue`.
- `deepagents` SubAgent `tools` must always be given (otherwise parent tools are inherited); `skills` sources are
  directories containing skill folders (hence per-agent bundles).
- Ledger write tools are per-section closures `ledger_write_<section>`; `delete_rows` restricted to own sections.
- Proposal `write_draft` is the only way to write `/drafts/` (filesystem permissions deny raw writes outside `/notes/`).
- The template's Heading 2 numbering carries a 10216-twip indent; the docx builder pins heading indents.
- A non-editable install needs `ASSETS_DIR`/`POLICY_DIR`/`SKILLS_DIR` (set in the Dockerfile).
