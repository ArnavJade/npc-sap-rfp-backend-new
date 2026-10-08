# Plan — Harness-based SAP RFP agent (new implementation in `npc-sap-rfp-backend-new`)

## Context

The current agent (`..\clone\npc-sap-rfp-backend`, branch `npc-dev` @ `0850ab3`, 521 commits) is a
fixed Python pipeline (Layer 0 → 1 → 2 → 3 → 4 → 5) with LLM calls at the leaves. Every judgement
(what counts as Security scope, which section a client ask belongs in, how duplicates merge) is
Python control flow plus a prompt string, so every presales request becomes a code change + image
build. The design review (`SAP RFP Agent Architecture Review (Copy).md`) proposes: keep FastAPI and
the deterministic core, run the **Claude Agent SDK** on Bedrock, move SAP/proposal knowledge into
versioned `SKILL.md` files, numbers/layouts into `policy/*.yaml`, make a validated **JSON bid ledger**
the state between the two calls, and gate every change with evals.

This plan builds that as a **completely new implementation** in this repo. It ports (not rewrites)
every item on the review's §4 keep-list from exact source locations below, and drops the rest:
chunking/stitching/salvage, Layers 1–2 LLM orchestration, the Others dedup/reclassify chain, the
section hint chain, the 835-line Excel reload, and the request-scoped contextvars.

**Outcome:** same two public calls (RFP → effort workbook; reviewed workbook → YASH `.docx`), same
workbook layout and docx template; one agent run per call; skill/policy edits ship without an image
build; every client-facing number comes from a tool; a scored eval suite gates changes.

## Facts that shape the design (verified in code + current SDK docs)

- RFPs fit in context (largest sample ≈51K tokens; Sonnet/Opus 1M) → no chunking, no merge layer.
- Old prod ran non-Claude at least once (`logs.txt`: `gemini/gemini-2.5-flash-lite`) → the SDK is
  Claude-only, so team config must be mapped to Claude/Bedrock and **fail fast** otherwise.
- Python `claude-agent-sdk` (pin ≥ 0.2.140) bundles the native CLI (no Node). Per-subagent `model`,
  `effort`, `tools`, `skills` (preload), `maxTurns`; caps via `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`,
  `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`, `max_budget_usd` (covers subagents). In-process tools via
  `@tool` + `create_sdk_mcp_server` (Python returns only `content` + `is_error`). Python hooks:
  `PreToolUse`, `PostToolUse(+Failure)`, `Stop`, `SubagentStart/Stop` (carry `agent_type`),
  `PreCompact`; Stop/SubagentStop block with `{"decision":"block","reason":…}`. `output_format`
  json_schema → `ResultMessage.structured_output`. Skills load from `<cwd>/.claude/skills` with
  `setting_sources=["project"]`.
- Bedrock: `CLAUDE_CODE_USE_BEDROCK=1`, default AWS chain (IRSA ok), **pin**
  `ANTHROPIC_DEFAULT_OPUS_MODEL` / `_SONNET_MODEL` (unpinned `sonnet` on Bedrock = Sonnet 4.5).
  WebSearch unavailable on Bedrock. IAM: `bedrock:InvokeModel*`, `ListInferenceProfiles`,
  `GetInferenceProfile`. Hosting ≈ 1 GiB RAM / 1 CPU / 5 GiB disk per running session; no session
  timeout (use `max_turns`); S3 `SessionStore` reference adapter available to copy.
- Latent bugs fixed during the port: SharePoint simple PUT caps at 4 MB (`sharepoint_client.py:526`;
  a Sidel docx was 6 MB) → use an upload session above 4 MB; `resource_scope_sync.py:344` uses an
  unseeded RNG → seed from `bid_id`; country availability reads a local file (`bp_mapper_layer3.py:269`)
  while the catalogue loads from S3 → one loader.

## Repository layout (files kept < 500 lines; src-layout per workspace rules)

```
src/app/            FastAPI: main.py (lifespan, /health), api/bids.py (2 public routes + /jobs),
                    jobs/{runner,store}.py, platform/{request_context,headers,sharepoint,activity,
                    s3,llm_config,claude_runtime}.py, settings.py (infra/paths only)
src/harness/        runs.py (workspace + ClaudeAgentOptions + query), agents.py, hooks.py,
                    tools/{catalogue,ledger,effort,workbook,docx,drafts}.py, prompts/*.md,
                    session_store_s3.py (copied SDK reference adapter)
src/bidcore/        deterministic core, no LLM/SDK imports:
                    catalogue.py, evidence.py, policy.py, timeline.py, resourcing/, scope_sync.py,
                    effort/{rate_card,rollup,techdev,areas,summary}.py,
                    ledger/{models,store,validate,overlap,manifest,diff}.py,
                    render/{workbook/,docx/,diagrams.py,disclosure.py},
                    ingest/{extract.py,aperture/,vision.py}
skills/             knowledge (synced into each run's .claude/skills as a pinned bundle)
policy/             numbers + layouts (*.yaml), versioned with skills
assets/             catalogue xlsx + YASH template (dev fallback; prod = S3 reference-data/)
evals/              cases, gold readers, metrics, judge rubric, thresholds
tests/              ported unit tests, parity tests, new ledger/diff tests
Dockerfile, helm/, .github/workflows/, pyproject.toml
```

## Keep-list → port map (source = clone path:line)

| Review §4 item | New home | Port from | Change |
|---|---|---|---|
| Catalogue mapping + country availability | `bidcore/catalogue.py` | `module_matcher_layer1.py:102` (keep `index+3` = Excel row), `:123` cross-map loader, `:172` `parse_cross_mapping_entry`, `:297` country filter, `:368-443` alias index/exact match; `module_matcher_layer2.py:79,109,122,193` index selection, `:44/:551` Finance-core rule; `bp_mapper_layer3.py:136` `merge_others_modules`, `:187`, `:263`, `:310` (EXISTING_NO_CHANGE → excluded list); `classifier.py:371-403` keyword guardrails | LLM fuzzy match/classification removed (agent does it with skill + tools); guardrails become ledger validators |
| Effort & cost maths | `bidcore/effort/*`, `timeline.py`, `resourcing/`, `scope_sync.py` | `effort_calculator_layer4.py:113` EffortRow, `:251` EffortIndex (country→global→other fallback), `:387` per-country fan-out + zero rows, `:486`, `:541-710` wave shares/prepare_timeline, `:713-814` sub-module split, `:926` grid inputs, `:1048` recompute_totals, `:2970-3247` Tech Dev maths (split counts, h→d, Fiori 40-MD floor, 3P 60/10/15/15, interface subtraction), `:3253-3261` + `:3701` Summary ladder (8/5/8 %, ×1.1, flat hypercare cost); `resource_grid_layer4.py` all deterministic parts (`:89-152` roles/profiles, `:342` 0.5-FTE largest-remainder, `:409`, `:436`, `:460`, `:759`, `:809`, `:1097`, `:1418` PM cap kept as policy mode, `:1599-1958` four-pass rebalance, `:1716` category consultants, `:1961`, `:2012` pricing); `resource_scope_sync.py` whole; `project_timeline_extraction_layer.py:105-295, 333-460, 1137-1223` | LLM grid (`:945-1255`) and LLM wave sizing (`:1092-1322`) dropped (agent may set durations in ledger with evidence; else bands); constants → policy; area handling generalised (see Registry) |
| Rendering | `bidcore/render/workbook/`, `render/docx/`, `diagrams.py`, `disclosure.py` | `effort_calculator_layer4.py:2409-3954` (all sheets, live formulas, tab order) + writers in `data_migration_scope.py:289`, `basis_scope.py:151`, `security_scope.py:236`, `analytics_scope.py:218`; `document_generator_layer5.py:208-1702` (template, cover tokens, TOC field, `updateFields` order, theme, headings+bookmarks, md→docx incl. pipe tables, landscape, col widths, `_add_data_table`), `:1710-2430, 2951` table builders; `layer5_disclosure.py`; `layer5_diagrams.py` (verbatim) | Sheet titles/headers/widths/lists/formulas → `policy/workbook.yaml`; add hidden `_bid` sheet + `row_id` columns; render manifest for diffs |
| Evidence grounding | `bidcore/evidence.py` → used by `ledger.write` | `data_migration_scope.py:67-111` (`_clean_text`, `_norm_key`, `CorpusIndex`), `:228` MM-compulsory exemption | — |
| Platform glue | `app/platform/` | `models/request_context.py`, `models/headers.py` (verbatim), `utils/activity_client.py` (verbatim), `utils/sharepoint_client.py`, `utils/s3_client.py`, `utils/llm_config.py:119-441` (DB + KMS), `helm/`, `DockerfileGraviton`, `.github/workflows/` | + `claude_runtime.py`; SharePoint upload session > 4 MB |
| 2,700 lines of prompt text | `skills/` | see Skills table | Moved near-verbatim, split per workstream |
| Ingestion (implied by "embedded image/table blocks") | `bidcore/ingest/` | `routers/ingestion.py:94-217`, `src/aperture/*` (extractors, `image_filter`, `table_formatter`, `merge` block format, `orchestrator`, `prompts`, `third_party_table_scanner`) | Vision via Anthropic Bedrock client, cached by image sha1 in S3; per-file markdown with page markers |

Survives only in `evals/` (as gold reader): reload path `effort_calculator_layer4.py:3957-4805`.
Deleted outright: chunk/stitch/salvage (`country_module_extraction_layer.py:809-1525`,
`third_party_integration_extraction_layer.py:755-1495`), Layer 1/2 LLM calls, Others LLM
estimate/dedup/reclassify/PM-classifier (`effort_calculator_layer4.py:1328-2406` — deterministic
overlap helpers `:1816-2036` and `:1283-1325` are kept as ledger checks), Layer 5 hint chain /
steering / harmonization / verification LLM plumbing, `routers/pipeline.py` orchestration,
contextvars (`rfp_type_classifier`, timeline, disclosure, llm params).

## Bid ledger (`bidcore/ledger/`)

- One JSON document per bid; agents write **only** through `ledger_write`. Stored in the run
  workspace and versioned to S3 `sap-rfp-agent/bids/<bid_id>/ledger/v<N>.json`; `bid_id` +
  manifest version travel in the workbook's hidden `_bid` sheet.
- Sections (JSON Schema per section; every row has `row_id`, `evidence{quote,file,page}`, `written_by`):
  `rfp_profile` (engagement type + reason, countries/scope_type, unsupported countries) ·
  `capabilities` (country → SAP capability, confidence, implementation_status) · `scope_items`
  (LOB/BA/scope_item_id, countries, submodule, mapping basis, status incl. `excluded_existing`) ·
  `non_catalogue` (sap_tool | third_party, is_project_management, effort_days + rationale) ·
  `integrations` (today's labelled facts A + Tech Dev columns) · `ricefw` · `fiori` ·
  `data_migration` · `basis` · `security` · `analytics` (fields = today's prompt sections B–G) ·
  `timeline` (waves, hypercare, sequencing, axis, duration_source) · `response_requirements`
  (requirements narrative|indicative_breakdown|phase_plan, maps_to/placement, section_excerpts,
  disclosure 5 flags + evidence) · `overrides` (reviewer edits: rate-card cells, %/rates, grid
  cells) · `audit` (append-only).
- `ledger_write` rejects with a per-row error list (agent fixes and retries): schema/enums;
  quote ∈ RFP via `CorpusIndex`; ported section rules — DM effort ∈ {0.5,1,2,3,4} + MM-compulsory
  four, Basis 1–5 (null when Out of Scope), Security 1–120 whole days, Analytics 1–500 + exclusion
  needs verbatim evidence, timeline hypercare ≤ total ≤ 260 wk and ≤ 12 waves + wave-anchor ordinal
  checklist (`find_wave_anchors`), 43 allowed country codes, scope item exists and is available in the
  country, Finance core BAs, GRC/ERC, Cash→Treasury, receivables→AFO, sensitive-LOB qualification
  evidence, catalogue-covered codes barred from `non_catalogue`. Cross-section overlaps
  (`_normalize_system_name`, `_is_cross_list_duplicate`, security/analytics product match, catalogue
  GRC vs Security GRC) return as warnings the orchestrator resolves via `ledger_resolve_overlap`.
- **Scope-area registry** (meets the review's "new area = skill + schema + sheet entry"): each area
  declares schema (`skills/scope-<area>/ledger.schema.json`, with `x-effort` fields, status field,
  optional rate table), sheet spec + `summary_link` + `resource_role` in `policy/workbook.yaml`.
  Generic validators, effort roll-up, Summary-of-Project-Effort row, category-consultant grid row
  and scope-sync pairing are driven from the registry. Existing DM/Basis/Security/Analytics become
  registry entries; their extra rules stay as named Python validators.

## Policy (`policy/*.yaml`, loaded + validated by `bidcore/policy.py`, version hash stamped in outputs)

`commercials` (320 USD/day, hypercare 160/40 split and flat 360, 21 days/month, 8/5/8 %, ×1.1,
programme-overhead mode `rebalance` 8 % with legacy cap 0.07/0.10 available) · `effort` (rate-card
sheet SAP BP|YASH BP, factor 1.0, Tech Dev defaults, 3P split, 8 h/day, Fiori floor, RICEFW types) ·
`resourcing` (phase weights .08/.18/.50/.14, programme roles + windows, lead profiles 0.5–2.0, grains
0.5/0.25 < 200 MD, PGLS retention .35/.25, PM-system keyword floor) · `timeline` (duration bands,
3-month hypercare default, 12/156 wk bounds, 21.4 wk min build, 4.345 wk/month) · `catalogue` (LOBs,
countries, Finance core, sensitive LOBs, guardrail keywords, covered codes) · `scope_sync` (+30 PD
band, 1 PD step, seeded) · `workbook` (sheet specs, tab order) · `disclosure` (header cues, rule
text) · `runtime` (per-agent model/effort/max_turns, budget, concurrency, Bedrock model pins).

## Skills (knowledge moved near-verbatim; SKILL.md < 500 lines, detail in `reference/*.md`)

| Skill | Sourced from |
|---|---|
| `rfp-reading` | `country_module_extraction_layer.py:66-807` (countries, matrices, templates, workstreams, scope types, implementation status, embedded blocks, evidence); `project_timeline_extraction_layer.py:467-655` (waves, 44-incl-12 idiom, hypercare, sequencing, anchor checklist); `rfp_type_classifier.py:31-58`; `client_requirements_layer5.py:116-196, 478-598, 714-727` (response requirements, excerpts, disclosure); `third_party…:444-466` → `reference/reading-tables.md` |
| `sap-scope-mapping` | `country_module…:417-656`; `module_matcher_layer1.py:502-636, 845-967`; `module_matcher_layer2.py:334-413`; `classifier.py:86-324` → `reference/finance-business-areas.md`; `config/lob_categories*.py` + `utils/lob_semantic_corpora.py` → `reference/lobs/*.md`; SAP-branded vs third-party (`effort_calculator_layer4.py:2206-2250`); PM-system definition (`:821-860`) |
| `scope-integrations` | `third_party…:170-238` (A) + `:1116-1153` columns; `aperture/prompts.py:46-61` edge convention; effort guidance `effort_calculator_layer4.py:1361-1384` |
| `scope-ricefw-fiori` | `third_party…:240-357` (B, C) |
| `scope-data-migration` | `third_party…:358-520` (D) |
| `scope-basis` / `scope-security` / `scope-analytics` | `:521-574` (E) / `:575-627` (F; review appendix sketch) / `:628-676` (G) |
| `estimating` | how to drive `effort_compute`, policy vs bid override, never state a number a tool did not return; non-catalogue effort bands |
| `proposal-outline` | `outline.yaml` from `STATIC_SECTIONS` (`document_generator_layer5.py:3872-3920`) + per-section ledger views (`layer5_excel_context.py:71-109`) + kind guidance/word budgets (`:3083-3175`); `sections/3.4-assumptions.md`, `3.5-scope-exclusions.md` (`:3015-3080`); client-required placement (`:4022-4041`), detail bonus (`:3199`), combine rule (`:3924`), steering (`:3177`, `client_requirements_layer5.py:754-834`) |
| `proposal-writing` | `SECTION_SYSTEM_PROMPT` `:275-335`, visual guidance `:577-627`, indicative breakdown `:2489-2520`, phase plan `:2629-2707`, integrations `:2854-2873`, harmonization rules `:3317-3367` (editorial checklist), disclosure rule text, RACI convention `:2376-2398`; **new** `reference/yash-profile.md`, `service-catalog.md` (content from presales — today LLM-invented) |
| `bid-review` | verification `:3513-3543` + cost-gap rule `:3568-3592`; `routers/evaluator.py:134-196` rubric; numbers-vs-ledger; unsupported claims |

Frontmatter carries `metadata: {owner, version}`; each `scope-*` skill ends with an Output section
naming its ledger section and fields.

## Agents, tools, hooks (`src/harness/`)

| Agent | Model (policy) | Tools | Skills | Writes |
|---|---|---|---|---|
| `orchestrator-call1` (main thread) | Opus 5.5, high | Read, Grep, Glob, Agent, Skill, `ledger_read/check/resolve_overlap`, `effort_compute`, `workbook_render` | estimating | delegations, overlap fixes |
| `rfp-analyst` (call 1) | Sonnet 5.5 | Read, Grep, Glob, Skill, `ledger_read/write` | rfp-reading | rfp_profile, capabilities, timeline |
| `requirements-analyst` (call 2) | Sonnet 5.5 | Read, Grep, Glob, Skill, `ledger_read/write` | rfp-reading (response-requirements + disclosure references) | response_requirements |
| `scope-<area>` ×6 (auto-discovered from `skills/scope-*`) | Sonnet 5.5, medium | Read, Grep, Glob, Skill, `ledger_read/write`, `catalogue_search` | own | own section |
| `catalogue-mapper` | Sonnet 5.5 | `ledger_read/write`, `catalogue_search/get/cross_map` | sap-scope-mapping | scope_items, non_catalogue |
| `orchestrator-call2` (main thread) | Opus 5.5, high | Read, Grep, Glob, Agent, Skill, `ledger_read/write`, `workbook_read_edits`, `ledger_apply_diff`, `effort_compute`, `draft_check`, `docx_render` | proposal-outline, estimating | applied diff, section briefs |
| `section-writer` ×N | Sonnet 5.5 | Read, Grep, Glob, Write/Edit (drafts/ only), Skill, `ledger_read(view)`, `draft_check` | proposal-writing | `drafts/<id>.md` |
| `reviewer` | Opus 5.5 | Read, Grep, Glob, Skill, `ledger_read`, `draft_check` | bid-review | `review/findings.json`; ≤ 2 rounds |

- **Tools** (one in-process MCP server `bid`, built per run with closures over run context; CPU work
  in `asyncio.to_thread`; read-only tools annotated `readOnlyHint`): `catalogue_search/get/cross_map`,
  `ledger_read/write/check/resolve_overlap/apply_diff`, `effort_compute(group_by=module|wave|country|
  role|workstream, overrides=…)` → stable figure keys + views, `workbook_render` (+ manifest),
  `workbook_read_edits` (manifest diff), `draft_check`, `docx_render`.
- **Drafts never contain figures**: `{{fig:total_project_effort}}`, `{{table:resource_plan}}`,
  `{{diagram:timeline}}` resolved by `docx_render` with disclosure filtering. Bare numbers allowed only
  for dates, ledger counts/durations, or quotes verified in the RFP.
- **Hooks**: PreToolUse Write|Edit → only `drafts/`, `notes/`; PreToolUse `ledger_write` → section
  ownership by `agent_type`; no Bash/WebFetch/WebSearch anywhere (`disallowed_tools`); SubagentStop →
  section rules + recall checks (integrations vs `third_party_table_scanner` candidates; timeline vs
  wave anchors), block once; Stop call 1 → `ledger_check` clean + workbook rendered; Stop call 2 →
  `draft_check` clean + docx rendered; max 2 blocks then fail job with the list; PostToolUse →
  audit + `trace/tool_calls.jsonl`.
- **Limits/isolation**: `max_budget_usd` (start 25), per-agent `maxTurns`, depth 1, concurrency
  from policy (sized to Bedrock quota), `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`, per-run
  `CLAUDE_CONFIG_DIR`, `setting_sources=["project"]` on the run workspace, system prompt = `claude_code`
  preset + appended playbook (explicit delegation instruction), S3 SessionStore for transcripts.

## Run flow

**Call 1 — `POST /pipeline/match/effort`** → job: parse `RequestContext` (ported) → resolve Claude
runtime from team config → download SharePoint attachments → ingest to `rfp/` (per-file markdown,
page markers, table/image blocks, `index.md` with headings, tables, wave anchors, 3rd-party table
candidates; file hashes recorded) → create ledger, sync pinned skills bundle, write workspace
`CLAUDE.md` → `query(orchestrator-call1)`: analyst ∥ 6 extractors → mapper → `ledger_check` →
`effort_compute` → `workbook_render` (+ manifest, `_bid` sheet) → SharePoint upload (upload
session above 4 MB) → persist workspace/ledger/manifest/transcript to S3 → Activity
`effort_excel_generated`.

**Call 2 — `POST /pipeline/generate/from-excel`** → job. Inputs (unchanged): the workbook call 1
saved to SharePoint, after users edited it there, plus the RFP. Steps: download attachments → the
`.xlsx/.xlsm` is the reviewed workbook, everything else is RFP → read `_bid` → load ledger + manifest
from S3 → `workbook_read_edits` (input-cell diff against the manifest: line items, added/deleted
rows, statuses, efforts, %/rates, waves, grid FTE cells; formula cells overwritten with constants
reported as conflicts) → orchestrator applies the diff → `requirements-analyst` extracts client
requirements, section excerpts and the disclosure profile **from the attached RFP** (reuses call 1's
`rfp/` markdown when the file hash matches, so no second vision pass; ingests otherwise; falls back
to the stored RFP text if none is attached; disclosure falls back to high-level if extraction
fails, as today) → free-text `instructions` become section briefs → `effort_compute` → outline →
writers in parallel → reviewer → `draft_check` → `docx_render` → upload → Activity
`proposal_generated`. The reviewed ledger timeline is authoritative (no timeline re-extraction).

**Workbook compatibility**: only workbooks produced by this service are accepted (hidden `_bid` →
ledger). A workbook without `_bid` gets a 422 asking to regenerate with call 1; bids already in flight
on the old service finish there during cutover. No importer for the old format.

**API (jobs + sync shim)**: keep both paths and the `user_metadata` Form contract. Default returns
`202 {job_id, status_url}`; `?wait=true` blocks until the job ends and returns today's
`{"status":"success","sharepoint":…}` body so the UI can migrate later. `GET /jobs/{job_id}` for
polling; Activity API events unchanged. Job records in S3 with a heartbeat lease (stale → failed);
per-pod concurrency semaphore (429 when full).

**Runtime mapping** (`claude_runtime.py`): keep `ModelConfig` DB lookup + KMS decrypt; provider
bedrock → `CLAUDE_CODE_USE_BEDROCK=1`, `AWS_REGION`, creds (or IRSA), model pins; anthropic →
`ANTHROPIC_API_KEY`; anything else → HTTP 422 naming the configured model. Same creds feed the
ingestion vision client.

## Evals (`evals/`)

- Data (not committed; not found on this machine — review cites `D:\SAP-T\RFPs`): 8 sample RFPs,
  Sidel + DORABC human responses, reviewed workbooks → `evals/data/` (git-ignored) or `EVALS_DATA_URI`.
- `gold_reader.py` reuses the old reload loaders to normalise reviewed old-format workbooks.
- Metrics: scope-item precision/recall (LOB, BA, ID, country); row recall per workstream; effort
  difference per workstream and total; evidence-grounding rate; number consistency (docx ⊆
  figures/ledger); requirement coverage via Claude judge (rubric from `evaluator.py` + verification
  prompt). Each case ×3, report mean and stdev. Baseline = old pipeline outputs on the same RFPs.
- `python -m evals run --cases all --repeats 3 --bundle <version|path>` → `report.md`,
  `scores.json`; thresholds in `evals/thresholds.yaml`.

## Build sequence (each phase ends on a check)

| Phase | Work | Done when |
|---|---|---|
| 0 · Scaffold + measure | Repo layout, `pyproject.toml`, CI skeleton; gold readers, metrics, judge; `scripts/capture_parity_fixtures.py` run in the clone venv (LLM paths off, RNG seeded) to snapshot old intermediate objects + workbook cells; baseline scores | `python -m evals score` works on the baseline |
| 1 · Deterministic core | Port `bidcore` (catalogue, evidence, timeline, resourcing, scope_sync, effort, render, disclosure, diagrams, ingest) with ported tests (`unit/test_resource_grid_and_totals.py` — its workbook round-trip cases move to the eval gold-reader tests — `test_disclosure.py`, `test_aperture/*`, deterministic parts of `test_layer1_cross_mapping_batching.py`, `test_phantom_lob_qualification.py`); ledger models/validators/manifest/diff; policy YAML from today's constants | `pytest` green; parity: same inputs → identical totals and workbook input/formula cells (only intended fixes differ) |
| 2 · Call 1 on agents | Author skills from prompts; agents/tools/hooks; ingestion + vision cache; job API + platform glue; ARM64 image spike (CLI launches, memory/run, Bedrock quota and region/inference-profile prefix, model pins) | Evals ≥ baseline on scope recall and effort difference, 8 RFPs ×3; cost per run logged under budget |
| 3 · Call 2 on agents | Diff/apply, outline, writers, reviewer, numbers hook, docx render | Coverage + consistency ≥ baseline; presales sign-off on three live bids |
| 4 · Cutover | Platform routes both endpoints here; `publish-bundle.yaml` (tar skills+policy → S3, env pins version) behind `evals.yaml` gate; old repo frozen, then retired | A presales SME adds a scope area with no Python change |

## Verification

- `pytest tests/` (unit + `tests/parity`); `ruff`/type check in CI.
- Local bid: `python scripts/run_local.py --rfp <dir> --call 1|2` with Bedrock creds → xlsx opens in
  Excel, sheet totals equal `effort_compute` figures, `_bid` round-trips; docx opens, TOC updates,
  no bare figures (`draft_check` clean), disclosure honoured.
- API: `uvicorn src.app.main:app` → POST with `user_metadata` (SharePoint test folder) → poll job →
  SharePoint item + Activity event (mock receiver in dev); >4 MB upload path exercised.
- Container: `docker buildx build --platform linux/arm64`, smoke bid in dev cluster.
- Evals: `python -m evals run --cases all --repeats 3` vs `thresholds.yaml`; per-run
  `total_cost_usd` / `model_usage` recorded.

## Decisions

Confirmed with you:
- API: jobs + sync shim (`202` + `GET /jobs/{id}` by default, `?wait=true` returns today's body).
- Claude access: per-team Neupac DB config (DB + KMS) mapped into the SDK env; non-Claude team
  config fails fast with a 422.
- Call 2: workbook is the call-1 output edited in SharePoint (new-service workbooks only); client
  requirements come from the RFP attached to call 2.

Assumed (review defaults):
- Claude-only for this agent (review decision 01), Bedrock now (decision 02).
- Skills/policy live in this repo for now, shipped as an eval-gated S3 bundle; split repo later.
- Python SDK (TypeScript-only features such as the `Workflow` tool are not needed).
- Workbook layout, file names (`Claude_BP_Effort_Output_*`, `YASH_SAP_RFP_Response_*`) and the
  `{"status","sharepoint"}` response body are preserved.

Prerequisite outside the code: the eval gold set (8 RFPs, Sidel/DORABC responses, reviewed
workbooks) must be supplied — it is not on this machine.
