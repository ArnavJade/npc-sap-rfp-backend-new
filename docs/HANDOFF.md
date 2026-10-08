# Handoff — SAP RFP Agent PoC on Deep Agents (as of 2026-10-08)

Read with `docs/IMPLEMENTATION_PLAN.md` (original plan, Claude-Agent-SDK based). This file records how the
PoC **deviates** from that plan, what exists, and what is left. Nothing is committed to git yet.

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

## What exists

**Data/knowledge assets (done, verified)**
- `scripts/build_assets.py`: `assets/source/*.xlsx` → `assets/catalogue/{scope_items,availability,cross_mapping}.parquet`
  (445 items, 13 LOBs, 46 BAs, 43 countries, 60 cross-map rows) and `policy/rate_cards/bp_efforts.parquet`
  (429 rows/sheet; all country key US); generates `skills/sap-scope-mapping/reference/{cross-mapping-aliases,catalogue-structure}.md`.
- `policy/*.yaml` (commercials, effort, resourcing, timeline, catalogue [country codes quoted — YAML `NO`=false], workstreams,
  workbook, runtime) + `src/bidcore/policy.py` typed loader with version hash. Porting agents added extra keys.

**bidcore (deterministic, no LLM)**
- `catalogue/` crossmap parser + in-memory SQLite FTS5 store (`catalogue_search`, availability, cross-map resolve/expand) — verified.
- `ledger/` models (`base.py`, `sections_effort.py`, `sections_proposal.py`, `models.py` SECTIONS registry), `store.py`
  (locked, atomic, audited, checkpoints), `validate.py` (evidence via `evidence.CorpusIndex`, countries, catalogue
  existence/availability, covered codes, DM snapping/MM exemption, Basis 1–5, Security 1–120, analytics, timeline, wave plan),
  `overlap.py` — 8 tests passing (`tests/ledger`).
- Contracts: `effort/models.py`, `resourcing/models.py` (+ `WaveSpec`, `PassWeights`), `timeline/model.py`.
- Ported by background agents (UNREVIEWED — check their tests, signatures vs. contracts):
  `effort/{rate_card,catalogue_effort,techdev,workstreams,summary,waves}.py`, `timeline/resolve.py`,
  `resourcing/{rounding,roles,grid,plan,rebalance,pricing,scope_sync}.py`, `ingest/{models,anchors,images,tables}.py`
  (ingest is **incomplete**: `pdf.py`, `office.py`, `workspace.py` with `ingest()`/`read_section()` and its tests missing),
  `app/platform/*` + `tests/platform_glue/*` (**DONE: 51 tests pass**; SharePoint upload session > 4,000,000 bytes,
  5 MiB chunks; `SharePointError` → map to 502 and missing attachment ids → 422 in routes; module does not load `.env`,
  so app start-up must call `load_dotenv()`). tests/effort, tests/timeline, tests/resourcing may be missing/incomplete.
- Written by me, **untested**: `sizing.py` (full pipeline; imports agents' function names — reconcile signatures),
  `figures.py` (placeholder keys), `outline.py`, `drafts.py` (draft_check).

**harness (Deep Agents)** — written, untested: `llm.py` (verified manually), `workspace.py`, `skills.py` (per-run skill
bundles `/skills/<agent>/`, auto-discovery `skills/scope-*`, frontmatter `metadata.ledger_sections`), `context.py`
(RunContext, Trace → `trace/events.jsonl` + progress sink), `middleware.py` (LedgerGuard, Trace), `teams.py`
(build_team), `tools/{ledger,catalogue,rfp,effort,proposal}_tools.py`, `prompts/*.md`.

**workflows** — written, untested: `common.py`, `effort.py` (ingest→agents→verify↺→size→render),
`proposal.py` (apply_edits→rfp→size→agents→verify↺→render).

**skills** — partial (agents were mid-way): `rfp-reading`, `sap-scope-mapping` (SKILL.md + finance ref; lobs/guardrails refs
may be missing), `proposal-outline` (SKILL.md, outline.yaml, sections/). Missing: `wave-planning`, `estimating`,
`scope-integrations`, `scope-ricefw-fiori`, `scope-data-migration`, `scope-basis`, `scope-security`, `scope-analytics`,
`proposal-writing` (+ yash-profile, service-catalog, placeholders refs), `client-requirements`, `bid-review`.
Skill frontmatter `metadata` values must be strings. Source line ranges: plan's Skills table.

## Background agents — all stopped (state at stop)
- effort-port: all 7 modules written; smoke run + test suite NOT done (tests/effort, tests/timeline empty).
- resourcing-port: modules written; was moving test helpers out of conftest; tests incomplete.
- skills-effort: rfp-reading done; was writing sap-scope-mapping (lobs/guardrails/non-catalogue refs); remaining skills not started.
- skills-proposal: proposal-outline done; proposal-writing, client-requirements, bid-review not written.
- ingest-build: models/anchors/images/tables done; was starting office.py; pdf.py/workspace.py/tests missing.
- platform-port: finished (51 tests pass).

## What is left (in order)

1. Check whatever the background agents finished (if not, redo from the briefs: effort/timeline port, resourcing port,
   effort skills, proposal skills, ingestion, platform). Run `pytest tests -q`; fix contract mismatches with `sizing.py`.
2. Finish ingestion: `bidcore/ingest/{pdf,office,workspace}.py` exporting `ingest(files, rfp_dir, *, pdf_engine, caption,
   cache_dir) -> IngestResult`, `read_section(rfp_dir, file, page_from, page_to, heading, max_chars)`, `list_pages`,
   `VISION_PROMPT`; markers exactly `<!-- page: N -->`; compact `index.md` (outline, tables, wave anchors, 3rd-party candidates).
3. Rendering:
   - `bidcore/render/workbook/template_builder.py` + `scripts/build_templates.py` → `assets/templates/template.xlsx`
     (prototype rows per sheet; layout notes: styles.py has colours copied from old writers; old writers are in
     `effort_calculator_layer4.py` `write_effort_workbook`, `_write_resource_plan_block`, `_write_resource_reconciliation_block`,
     `_write_project_effort_summary_sheet`, and `*_scope.py` writers).
   - `render_workbook(ledger, sizing, path, policy) -> Path` (filler; live formulas as old; hidden `row_id` column per table).
   - `render/workbook/manifest.py`: `_bid` sheet (bid_id, render_id, ledger/policy version) + server-side
     `ledger/manifest-<render_id>.json` of every input cell; `read_edits(workbook, ledger_dir)` and
     `apply_overrides(ledger, edits)` (module effort/factor/wave/deleted/added rows → `ledger.overrides`; scope-sheet rows →
     direct ledger edits; Summary %/hypercare → settings; grid cells → overrides; formula cells overwritten → conflicts).
     NOTE `workflows/proposal.py` currently calls `read_edits(workbook, ledger/manifest.json)` — change to the ledger dir.
   - `sizing.compute_effort`/`size_bid` must honour phase-field, deleted-row, tech-dev, hypercare-setting and grid overrides.
   - `bidcore/render/docx`: template builder from `YASH_RFP_Template.docx` (has `{{CLIENT_NAME}}`, `{{DATE}}`, `{{YEAR}}`, TOC
     field; set `updateFields`), one `{{p S_x_y }}` subdoc per outline section, markdown→subdoc (headings, lists, bold,
     pipe tables), placeholder resolution, client-required sections appended after their anchor, disclosure filtering,
     `render_proposal(ledger, sizing, drafts_dir, out, policy)`; diagrams (timeline Gantt via matplotlib, methodology, architecture).
4. API (`src/app`): FastAPI `main.py`; jobs runner/store (asyncio tasks, semaphore, JSON records, progress from Trace sink);
   routes `POST /bids` (multipart RFP files, client_name, rate_card_sheet, model) → job; `GET /jobs/{id}`;
   `GET /bids/{id}`, `/bids/{id}/ledger`, `/bids/{id}/files/{name}`; `POST /bids/{id}/proposal` (reviewed xlsx [+RFP],
   instructions) or bid_id read from `_bid`; platform routes `POST /pipeline/match/effort` and
   `/pipeline/generate/from-excel` (user_metadata + SharePoint download/upload + Activity; 202 + `?wait=true`);
   422 for workbooks without `_bid`; fail fast if no model configured.
5. Streamlit UI (`ui/streamlit_app.py`): call-1 upload + progress + ledger summary + xlsx download; call-2 upload reviewed
   xlsx + instructions + docx download; bid list. Reference: DeepAgent `app_streamlit.py` (zip in repo root, extracted copy
   was in the session scratchpad).
6. Tests: harness wiring with scripted fake models per agent (`harness.llm.set_model_factory`; pattern from DeepAgent
   `tests/test_agent_e2e.py`), workflow e2e on a fixture ledger → real xlsx/docx, diff round-trip.
7. Live smoke run once the user configures `LLM_MODEL` (check Gemini tool-schema handling of nested/nullable fields).

## Gotchas
- `tests/platform` would shadow stdlib `platform` → use `tests/platform_glue`.
- `deepagents` SubAgent `tools` must always be given (otherwise parent tools are inherited); `skills` sources are
  directories containing skill folders (hence per-agent bundles).
- Ledger write tools are per-section closures `ledger_write_<section>`; `delete_rows` restricted to own sections.
- Proposal `write_draft` is the only way to write `/drafts/` (filesystem permissions deny raw writes outside `/notes/`).
