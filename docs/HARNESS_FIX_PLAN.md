# Agent harness: error analysis, fix plan and parity report (2026-10-08)

Inputs reviewed: the `app.log` of the ARASCO effort run (job 66f0d6fb016b4e27, bid 94b93d2bb68c, all roles on
`gemini/gemini-2.5-flash`), the generated workbook `Claude_BP_Effort_Output_arasco_20261008_154055_Summary.xlsx`,
the ground-truth workbook `Claude_BP_Effort_Output_Client_20261008_100321_Summary.xlsx` (old agent), and the old
codebase (`npc-sap-rfp-backend`, layered pipeline + Aperture ingestion).

## 1. The result was not fine

The first run's workbook prices about **30 %** of the reference. Most of the gap is ledger sections that were
never written, not wrong rates:

| Sheet / figure | Generated (arasco) | Reference (Client) | Cause |
|---|---|---|---|
| LOB sheets / scope items | 1 sheet (Finance), 19 items | 6 sheets, 195 items | mapper hand-picked items; old pipeline expanded whole Business Areas (§3.1) |
| Non-catalogue tools | 7 (incl. RISE licence, TM "extra stack", MDG licence lines) | 6 (Signavio, Enable Now, SuccessFactors, PS, Marel, CRM) | licence lines treated as tools; skill gap (§3.1) |
| Tech Dev rows | 5 (no third-party rows) | 29 (24 named integrations) | `scope-integrations` ended empty 9 times out of 9 (§2.1) |
| Data Migration | 0 objects, 1 wave | 68 objects x 3 waves | specialist ended empty 5 of 6 times; last run wrote "none" (§2.1, §2.3) |
| Security | 0 rows | 5 rows, 231 PD | specialist never wrote (54 model calls, grep over skill files) (§2.2) |
| Analytics | 0 rows | 2 rows | grep with `glob=<full path>` found nothing, so "no analytics" (§2.2) |
| Timeline / waves | 1 derived wave | 3 waves x 34.4 weeks | `rfp-analyst` never wrote `timeline` (empty replies) |
| Total project effort | 2,970 PD | 10,055 PD (recomputed) | all of the above |

Run cost: 17 min, 297 model calls, 3.41 M input tokens, 450 tool calls; the orchestrator re-spawned the same
specialists 3 times because sections stayed `pending`.

## 2. Errors in the log: root cause and fix

| # | Symptom in app.log | Count | Root cause | Fix (this branch) |
|---|---|---|---|---|
| 2.1 | `!! model_empty ... model returned neither text nor tool calls`, then `agent_end ... "output": ""` | 40 | Gemini Flash answers some turns with nothing (out=0), typically after a long tool result or when it abandons a large function call. Deep Agents treats a reply without tool calls as "done", so the specialist exits with no output and its sections stay `pending`. | `harness/recovery.py::ModelRecoveryMiddleware`: an empty reply is retried with a nudge (continue; write at most 10 rows per call), `limits.empty_reply_retries` (default 2); a final empty reply becomes a visible text. `model_empty` now records `finish_reason`. Specialist prompt: batches of <= 10 rows. |
| 2.2 | 151 `grep` calls: 60 "No matches found" (e.g. `RISE`, `BI`, `analytics` in a RISE RFP), 83 results listing `/skills/...` files | 151 | Harness `grep` is literal and case-sensitive; `glob` is a file-name filter, so `glob="/rfp/x.md"` matches nothing; models invented `file`, `file_path`, `page_from` (ignored), so the search ran over every mount incl. all agents' skill bundles. | `RfpGrepMiddleware`: RFP searches answered by our own search - case-insensitive, `a|b` alternation, page numbers in every hit, `page_from/page_to` honoured, only `/rfp/` unless another mount is asked for; other paths are passed on with sane `path`/`glob`. Prompt documents the call shape. |
| 2.3 | `ledger_rejected ... evidence quote not found in the RFP: 'File & Output'`, `'Bank Communication management module ...'` | 8 rows | The ingested tables keep `<br>`, `**`, `&amp;` and hyphen breaks (`Man-<br>agement`); the matcher's alphanumeric key turned `<br>` into the letters "br", so verbatim table quotes could never match. Agents then gave up ("intractable validation issue"). | `bidcore/evidence.py`: tags/entities stripped, `&` = "and", hyphen breaks rejoined on both sides; long quotes (8+ words) pass at >= 85 % in-order word match. Invented text is still rejected (tests). |
| 2.4 | `catalogue_search ... limit: Input should be less than or equal to 60` | 4 | The skill told the mapper to use `limit=100`; the tool rejected > 60. | Limit capped (max 100, largest Business Area has 53 items), never rejected. |
| 2.5 | `LedgerWriteScopeItemsRows is not a valid tool` | 4 | Model invented a tool name from the schema and sent one row as the arguments. | `ModelRecoveryMiddleware` maps an unknown name to the offered tool it contains (never to another agent's section) and wraps a single row into `rows=[...]`. |
| 2.6 | `effort_band must be one of [...]` (sent `"M"`) | 7 rows | Field was a free string whose allowed keys the model never saw. | Field description lists the keys; an invalid band is derived from kind + effort (note, not rejection); missing effort -> band minimum. |
| 2.7 | `basis already has 9 row(s); use mode='replace'` raised as a tool error | 2 | `rows=[] + none_reason` on a written section was treated as a failure. | Now a successful no-op ("Nothing changed ..."). |
| 2.8 | `scope sync: Basis: every cell is at its 5 PD cap ... cap lifted` | 2 | Deterministic warning, not an agent error: the Basis consultants' grid FTE exceeds what 1-5 PD per activity can absorb. | Not changed. Plan item 5.4. |

## 3. Skills vs the old agent

The old agent has no SKILL.md files: its knowledge lives in prompts inside `src/services/*.py`. The new skills
are faithful **text** ports of those prompts (sections A-G of the combined scope prompt, the timeline prompt,
the Layer 1/2 mapping prompts, the Layer 5 prompts). What did not match is the **procedure** around them.

### 3.1 Mismatches found and fixed

| Area | Old agent | New harness (before) | Fix |
|---|---|---|---|
| Catalogue granularity | Layer 2 picks LOB + Business Area per module; Layer 3 keeps 100 % of that area's items, then filters by country (deterministic, no LLM per item) | Skill said "Business-Area granularity", but `cross_map_lookup` told the model "keep only the items the RFP asks for; do not take a whole filter", and the model had to type every scope id | New tool `map_scope_area(capability_refs, module_name | lob+business_area, countries)` writes every item the selection holds (availability-filtered, merged). Tool text and skill now agree. |
| Finance core | `FINANCE_CORE_ALWAYS = [Financial Operations, Advanced Financial Operations]`, forced in code | policy listed AFC, AFO, CMPA (no Financial Operations) and relied on the model | Policy now AFC, FO, AFO, CMPA; `ensure_finance_core` runs deterministically before sizing. |
| Reading coverage | the combined scope prompt ran over **every chunk** of the RFP (map-reduce, union + grounding) | specialists told "never page through a whole document" and to grep | Specialist prompt + `rfp-reading`: read the whole RFP in ~10-page ranges when it is under ~200 k characters (ARASCO: 80 k), grep-first only for larger ones. |
| Image / diagram text | Aperture always sent images to a vision model; prompts look for `[EMBEDDED IMAGE]` | vision off by default; the integration diagram arrived as pymupdf4llm "picture text", which no skill mentioned | Vision captioning on by default (`INGEST_VISION=off` to skip); skills name the "Start of picture text" blocks and how to read them. |
| Licence lines | non-catalogue routing excluded licences implicitly | RISE subscription, TM "extra stack", MDG licence lines became 20-PD tools | `sap-scope-mapping` lists licence / subscription / extra-stack lines as never non-catalogue. |
| Search limit | n/a | skill told `limit=100`, tool max 60 | Tool max 100. |

### 3.2 Still different by design (keep an eye on these)

- Wave effort split: old `wave_attribution_layer4` heuristics vs new `wave-planner` agent + deterministic code.
- Old Layer 0 country x module extraction ran as one prompt per chunk; the new `rfp-analyst` writes
  `capabilities` itself. Coverage now depends on the full-read rule above.
- `estimating` and `wave-planning` skills have no old equivalent.

## 4. How images and tables are handled

**Tables.** PDF: `pymupdf4llm` renders each page to Markdown with pipe tables (`INGEST_PDF_ENGINE=docling` is
the optional alternative); every table is wrapped in `[EXTRACTED TABLE -- p.N] ... [END EXTRACTED TABLE]`
(`bidcore/ingest/tables.py`). DOCX / PPTX / XLSX / CSV tables are written cell-exact in the same format (cell
line breaks become `<br>`, `|` is escaped). `index.md` lists every table with its page, and a deterministic
scanner (ported from `aperture/third_party_table_scanner.py`) lists third-party system candidates found in
table columns. Agents read tables with `read_section`; there is no LLM table clean-up pass (the old Aperture
`table_llm` had one for pdfplumber tables, but it was off by default: `APERTURE_TABLE_CLEANUP=False`). Known weaknesses: cells keep `<br>`, `**`
and hyphen breaks (now neutralised for evidence matching, §2.3); merged / borderless PDF tables can lose
column alignment.

**Images.** Old Aperture: on by default (`APERTURE_ENABLED=True`), raster images via pypdf, one vision call
per kept image. New: raster images are extracted per page (PDF via PyMuPDF, DOCX inline and anchored pictures, PPTX
picture shapes), filtered (size / aspect / bytes, sha1 de-duplication, an image on 3+ pages is treated as
a logo), capped at `INGEST_MAX_IMAGES_PER_FILE` (30), and sent to the `vision` role model with the ported
Aperture prompt (transcribe verbatim, rebuild matrices as tables, list every integration edge). The reply is
inserted where the image was as `[EMBEDDED IMAGE -- p.N]` and cached by sha1 (`cache/captions.json`).
In the ARASCO run captioning was **off** ("9 embedded image(s) not captioned: no captioner configured"); it is
now on by default. **Vector** diagrams are not rasterised: only their text layer survives, as pymupdf4llm
"picture text" in jumbled order (the ARASCO integration landscape on page 16). Plan item 5.2.

**Word output.** Tables in the .docx are built from the ledger / sizing (`render/docx/tables.py`), never from
model text; diagrams (timeline, landscape) are matplotlib PNGs (`render/docx/diagrams.py`); writers place
them with `{{table:..}}` / `{{diagram:..}}` placeholders.

## 5. Word generation without `_bid` (done)

Call 2 no longer needs the hidden `_bid` sheet or the call-1 workspace:

- `bidcore/render/workbook/reader.py` reads any workbook in the template layout by its header rows (Summary
  parameters + Hypercare, Functional Scope sub-modules, Project Timeline grids, LOB sheets, Non Catalogue,
  Tech Dev, Data Migration per wave, Basis, Security, Analytics). It recomputes formulas the way the sheet
  does, so files saved by openpyxl (no cached values) and by Excel read the same.
- `snapshot.ledger(bid_id)` gives the writers their facts; `snapshot.sizing()` gives every figure, table and
  diagram in the document - the numbers are the workbook's.
- `services.proposal_workspace`: if `_bid` names a bid on this server (ledger + render manifest present) that
  bid is reused, as before; otherwise a new bid is built from the workbook. API (`/proposals`,
  `/bids/{id}/proposal`, `/pipeline/generate/from-excel`), CLI and UI follow; a non-template file is a 422
  ("does not look like an effort workbook").
- Without an RFP, `requirements-analyst` is skipped and the disclosure profile falls back to "withheld" (old
  rule for an unclassified RFP), so cost figures read "available on request" unless an RFP is supplied.

Verified on both uploaded workbooks: the reference file reads as 195 lines / 6 LOBs, 29 Tech Dev rows,
3 x 68 DM rows, 3 grids; the generated one as 19 lines, 5 Tech Dev rows, 9 Basis rows.

## 6. Second live run (arasco_2, gemini-2.5-flash) and the fixes it led to

| Sheet | Run 1 | Run 2 | Reference |
|---|---|---|---|
| LOB sheets / scope items | 1 / 19 | 6 / 195 | 6 / 195 |
| Integrations (named) | 0 | 6 (effort 0 -> rejected, resent) | 24 |
| Data Migration objects | 0 | 0 ("RFP only broadly mentions 'Masters'") | 68 x 3 waves |
| Basis | 9 | 0 (never written) | 6 |
| Security | 0 | 2 | 5 |
| Analytics | 0 | 0 | 2 |

Root causes in `cfa695ac-app.log`: 84 warnings, 42 of them empty replies. Every empty reply came after
the agent read the integration-diagram pages (16-17), and the nudge alone never recovered it: the
same request got the same empty answer three times (`scope-basis` 6 runs, `scope-integrations` 6 runs).
The data-migration and analytics agents recorded their sections empty after reading 1 and 13 pages.
The integrations agent read pages 16-17 only; most systems sit in the annexure of legacy applications.

| Fix | Where |
|---|---|
| Empty reply ladder: nudge -> thinking off (`reasoning_effort: disable`, Gemini) -> `tool_choice="any"` (a tool call is forced) -> fallback model (`LLM_MODEL_FALLBACK` / `models.fallback_model`) | `harness/recovery.py::ModelRecoveryMiddleware` |
| Completion guard: a specialist that stops with a section still `pending`, or (RFP <= 200k chars) before reading 90 % of the pages, is sent back to its model with what is missing (3 times) | `SectionCompletionMiddleware` |
| Reading coverage per agent; `read_next_pages` walks the RFP in order; `rows=[]` / no data is refused until the agent has read the RFP | `harness/context.py`, `tools/rfp_tools.py`, `tools/ledger_tools.py::empty_gate` |
| `integration_candidates()`: table-scan hits, every diagram text block, list lines of integration / legacy pages; the write tool lists table-scan candidates no row covers; missing effort -> Low 10 / Medium 20 / High 40 PD per interface | `tools/integration_tools.py`, `validate.py` |
| Skills for basis, security, analytics, data migration, integrations: mandatory detection procedure, signal words, typical counts, none_reason must name what was searched | `skills/scope-*/SKILL.md` |
| Updated cross-mapping workbook (74 rows, 15 new modules, richer aliases); parquet + alias guide rebuilt | `assets/source`, `assets/catalogue/cross_mapping.parquet`, `skills/sap-scope-mapping/reference/cross-mapping-aliases.md` |
| Rate-card "no row for X in SA" warning logged once per process (was 1,118 lines) | `effort/rate_card.py` |

### Data Migration per wave
Before: wave tables were copies of one table, then nudged at random cells by scope sync to match
the grid. Now the ledger rows are the BASE (first-wave) table; the wave-planner writes
`wave_plan.data_migration_waves` = `{wave, scale, key_scale?, objects?, rationale}` and
`effort/workstreams.py::scale_dm_table` builds each wave's table: only that wave's objects, every
cell x its factor, snapped to 0.5/1/2/3/4 (capped cells are noted). No entry -> scaled by the wave's
`data_migration` allocation share relative to wave 1; neither -> copy (noted). The Data Migration
person-days are split across waves exactly as the tables split them (`effort/waves.py`). A reviewer
edit in wave N>1's table changes that wave only (`data_migration_wave` override); wave 1 edits change
the base. Caveat: scope sync still rounds the grid row up to 0.5 FTE per month and moves table cells
to match, which inflates very small tables.

## 7. Remaining plan (not in this branch), in priority order

1. **Re-run ARASCO and diff against the reference** with `scripts/trace_view.py`: expect `model_empty`
   followed by `model_retry` instead of `agent_end ""`, no grep over `/skills/`, 0 limit / invalid-tool errors.
   Acceptance: every required section written on the first orchestrator pass; 5-6 LOB sheets; integrations
   >= 15 rows; DM objects > 40; Security and Analytics non-empty.
2. **Rasterise vector diagrams**: when a page has "picture text" or many drawings and no raster image, render
   that region with PyMuPDF (`page.get_pixmap(clip=...)`) and send it to the captioner.
3. **Model choice**: Gemini 2.5 Flash produced 40 empty turns in one run. Try `gemini-2.5-pro` (or Claude) for
   `analyst` and `specialist` roles via `LLM_MODEL_ANALYST` / `LLM_MODEL_SPECIALIST`; keep Flash for the
   orchestrator. Measure empty-turn rate per model from `trace/llm_calls.jsonl` (`finish_reason`).
4. **Basis grid cap** (§2.8): decide whether Basis activity effort should scale with the grid (old behaviour
   lifted the cap) or the grid should be capped by the activities.
5. **Old Layer 0 parity check**: add an eval that runs the reference RFP and compares scope ids, integration
   names and DM objects with the reference workbook (precision / recall per sheet).
6. **Table clean-up pass** for PDF tables with misaligned columns (old Aperture `table_llm`, off by default
   there too), behind a flag - only if a re-run shows misread tables.
7. **Disclosure without an RFP**: let presales instructions set the disclosure profile in workbook-only runs.
