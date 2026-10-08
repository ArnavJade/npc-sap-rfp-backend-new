# SAP RFP Agent

Turns a client's SAP RFP into the two YASH bid deliverables:

1. **Call 1 – effort estimation workbook** (`Claude_BP_Effort_Output_<client>_<timestamp>_Summary.xlsx`):
   RFP files → agents read the RFP into a bid ledger → deterministic sizing → Excel workbook.
2. **Call 2 – YASH Word response** (`YASH_SAP_RFP_Response_<client>_<timestamp>.docx`):
   the workbook after presales has reviewed and edited it (plus, optionally, the RFP) → edits applied
   to the ledger → agents draft the sections → Word document.

Agents run on the Deep Agents harness (LangGraph), with models called through LiteLLM. Every number
in both files comes from deterministic code (the rate card, `policy/*.yaml`), never from a model.
More detail is in `docs/HANDOFF.md` and `docs/IMPLEMENTATION_PLAN.md`.

---

## 1. Prerequisites

- Python **3.12** (3.12 or 3.13 is supported).
- An LLM the agents can call: any LiteLLM model string with its key, for example
  `gemini/gemini-3.8-flash`, `bedrock/<model-id>` or `anthropic/<model-id>`.
- Optional: [uv](https://docs.astral.sh/uv/) for a faster install.
- Optional: LibreOffice (`soffice`), used only by one test that recalculates the workbook formulas.

## 2. Install

```bash
git clone https://github.com/ArnavJade/npc-sap-rfp-backend-new.git
cd npc-sap-rfp-backend-new

# with uv
uv venv .venv -p 3.12
uv pip install -p .venv -e ".[dev]"

# or with plain pip
python -m venv .venv
# Windows: .venv\Scripts\activate      Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"
```

On Windows, keep the project on a short path. Long paths hit the MAX_PATH limit and break some imports.

## 3. Configure

```bash
cp .env.example .env        # Windows: copy .env.example .env
```

Edit `.env`. The minimum is one model and its credentials:

```ini
LLM_MODEL=gemini/gemini-3.8-flash
GEMINI_API_KEY=...
```

Optional settings:

| Variable | Purpose |
|---|---|
| `LLM_MODEL_<ROLE>` | A different model per role. Roles: `ORCHESTRATOR`, `ANALYST`, `SPECIALIST`, `MAPPER`, `PLANNER`, `WRITER`, `REVIEWER`, `VISION` |
| `INGEST_VISION=on` | Transcribe images in the RFP (diagrams, scanned tables) with the `vision` role model |
| `INGEST_PDF_ENGINE=docling` | Use the Docling PDF engine instead of pymupdf4llm (`pip install -e ".[docling]"`) |
| `WORKSPACE_DIR` | Where bids are stored (default `./workspace`) |
| `MAX_CONCURRENT_JOBS` | Number of bids the API runs at the same time (default 2) |
| `AZ_*`, `SHAREPOINT_ROOT_FOLDER`, `ACTIVITY_API_BASE_URL` | Only for the platform routes (`/pipeline/*`), which use SharePoint and the Activity API |

If no model resolves, every entry point stops at once with a clear message (HTTP 422 from the API).

## 4. Generate the effort workbook and the Word response

There are three ways to run a bid. All of them use the same workspace, `workspace/bids/<bid_id>/`.

### Option A – command line (simplest)

**Step 1: RFP → effort estimation Excel**

```bash
python scripts/run_local.py effort \
    --rfp "path/to/ARASCO RFP.pdf" \
    --rfp "path/to/Annex - scope matrix.xlsx" \
    --client "ARASCO" \
    --sheet "SAP BP"            # rate card: "SAP BP" (default) or "YASH BP"
```

- Pass `--rfp` once per file. Supported inputs: PDF, DOCX, PPTX, XLSX, CSV, TXT, MD.
- Progress (stages, agent calls, tool calls) is printed as the run proceeds.
- At the end the script prints the bid id and the workbook path:
  `workspace/bids/<bid_id>/outputs/Claude_BP_Effort_Output_ARASCO_<timestamp>_Summary.xlsx`.

**Step 2: review the workbook in Excel.** You may:
- change effort cells, multiplication factors and the Wave column on the module (LOB) sheets;
- change Tech Dev efforts and object counts;
- change status and effort on the Data Migration, Basis, Security and Analytics sheets;
- change the %, risk factor, rates and Hypercare values on *Summary of Project Effort*;
- change FTE cells in the *Project Timeline* grids;
- delete rows, or add rows inside a table.

Do **not** delete or edit the hidden `_bid` sheet: it links the workbook to its bid. Do not overwrite
formula cells (Totals). An overwritten formula is reported as a conflict and is not applied.

**Step 3: reviewed Excel → YASH Word response**

```bash
python scripts/run_local.py proposal \
    --workbook "path/to/Claude_BP_Effort_Output_ARASCO_..._Summary.xlsx" \
    --instructions "Go deep on data migration; keep the YASH profile short." \
    --out "ARASCO_Response.docx"
```

- The bid is found from the workbook's `_bid` sheet. Run on the same machine and `WORKSPACE_DIR` as step 1.
- `--rfp file` is optional: pass it only if the RFP changed since step 1.
- `--instructions` is optional free text from presales. It becomes per-section guidance.
- The document is written to `workspace/bids/<bid_id>/outputs/YASH_SAP_RFP_Response_<client>_<timestamp>.docx`,
  and copied to `--out` when given.
- When you open the file, Word asks whether to update fields. Answer **Yes** so the table of contents
  is refreshed.
- A section the agents could not draft is marked in red ("Draft missing ..."). Complete those
  sections before you submit.

The reviewer edits that were applied are listed in `workspace/bids/<bid_id>/notes/reviewer-edits.md`.

### Option B – web UI (Streamlit)

Start the API, then the UI, in two terminals:

```bash
uvicorn app.main:app --app-dir src --port 8000
streamlit run ui/streamlit_app.py            # opens http://localhost:8501
```

- **Tab 1:** enter the client name, upload the RFP files, choose the rate card, then click *Build effort
  workbook*. Follow the progress and download the `.xlsx` when the run finishes.
- **Tab 2:** upload the reviewed workbook, plus RFP files only if they changed, add instructions, then
  click *Generate proposal* and download the `.docx`.
- **Tab 3:** lists every bid with its outputs and ledger.

If the API runs elsewhere, set `API_URL` (default `http://localhost:8000`).

### Option C – HTTP API

```bash
uvicorn app.main:app --app-dir src --port 8000      # API docs: http://localhost:8000/docs
```

```bash
# Call 1: RFP -> effort workbook (?wait=true blocks until done; without it you get 202 + a job id to poll)
curl -F "files=@ARASCO RFP.pdf" -F "client_name=ARASCO" -F "rate_card_sheet=SAP BP" \
     "http://localhost:8000/bids?wait=true"
#   -> {"bid_id": "...", "result": {"workbook": "Claude_BP_Effort_Output_....xlsx", ...}, ...}

curl -o effort.xlsx "http://localhost:8000/bids/<bid_id>/files/<workbook name>"

# Call 2: reviewed workbook -> Word (bid id is read from the workbook's _bid sheet)
curl -F "workbook=@effort_reviewed.xlsx" -F "instructions=Keep it concise" \
     "http://localhost:8000/proposals?wait=true"
curl -o response.docx "http://localhost:8000/bids/<bid_id>/files/<document name>"
```

Other routes:

| Route | Purpose |
|---|---|
| `GET /jobs/{job_id}` | Job status: stage and recent agent/tool events |
| `GET /bids`, `GET /bids/{id}` | List bids, or one bid's summary |
| `GET /bids/{id}/ledger` | The bid ledger (JSON) |
| `POST /bids/{id}/proposal` | Call 2 against an explicit bid id |
| `POST /pipeline/match/effort` | Platform call 1: `user_metadata` form field; input from SharePoint, output uploaded to SharePoint, Activity event sent |
| `POST /pipeline/generate/from-excel` | Platform call 2, same contract |
| `GET /health` | Policy version and the model resolved for each role |

## 5. Logging and diagnostics

Every run is recorded at three levels. All lines carry `[bid|stage|agent]`, so parallel bids and
subagents never mix.

**Files, per bid, in `workspace/bids/<bid_id>/trace/`:**

| File | Contents |
|---|---|
| `events.jsonl` | Every event, in order: run start/end, stage start/end with duration, agent start/end with its final output, each model call (model, latency, tokens, tool calls requested, output preview), each tool call (args, result), ledger writes and rejections |
| `errors.jsonl` | Only the failure points: model errors, tool errors, stage/run errors (with traceback), ledger rejections (with reasons) |
| `llm_calls.jsonl` | One record per model call: tools offered, last input message, full output |
| `run.log` | All log lines for this bid (DEBUG and up), human-readable |

Service-wide logs go to the console and to `workspace/logs/app.log`.

**Settings (`.env`):** `LOG_LEVEL` (INFO), `LOG_FORMAT` (`text` or `json`), `LOG_DIR`,
`TRACE_PREVIEW_CHARS` (1500), `TRACE_LLM_CONTENT` (`off` drops prompt/response text from
`llm_calls.jsonl`), `TRACE_LOG_CALLS` (`off` moves per-call lines to DEBUG to quiet the console).

**Watch or analyse a run:**

```bash
python scripts/trace_view.py <bid_id> --follow          # live tail while it runs
python scripts/trace_view.py <bid_id> --errors          # failure points with tracebacks (--full: untrimmed)
python scripts/trace_view.py <bid_id> --summary         # per-agent model calls, tokens, latency, tool/ledger errors, stage times
python scripts/trace_view.py <bid_id> --agent scope-security --kind model_call,tool
python scripts/trace_view.py <bid_id> --llm             # full model inputs/outputs
```

`run_local.py` prints the same summary when a run ends, success or failure.

**API:** `GET /bids/{id}/trace?kind=model_call,tool&agent=...&errors_only=true&tail=200`,
`GET /bids/{id}/trace/summary`, `GET /bids/{id}/logs?tail=500`. A failed job's record
(`GET /jobs/{job_id}`) includes `error_traceback`.

**UI:** each bid has a *Diagnostics* panel (totals, per-agent table, stage timings, errors), and a
failed job shows its traceback.

## 6. Docker

```bash
docker build -t sap-rfp-agent .
docker run -p 8000:8000 --env-file .env -v $(pwd)/data:/data sap-rfp-agent      # bids land in ./data/workspace
# UI from the same image:
docker run -p 8501:8501 -e API_URL=http://host.docker.internal:8000 sap-rfp-agent \
    streamlit run ui/streamlit_app.py --server.port 8501 --server.address 0.0.0.0
```

## 7. Tests

```bash
python -m pytest tests -q
```

The tests drive both calls end to end with scripted fake models, so they need no API key. One test
uses LibreOffice to recalculate the workbook formulas. It is skipped when `soffice` is not installed.

## 8. Where things live

```
src/bidcore/      deterministic core: ingestion, ledger + validators, effort/timeline/resourcing maths,
                  sizing, workbook and docx rendering (no LLM)
src/harness/      Deep Agents teams, tools, prompts, model access (LiteLLM)
src/workflows/    the two LangGraph state machines (effort.py = call 1, proposal.py = call 2)
src/app/          FastAPI service, job runner, SharePoint / Activity glue
skills/           agent knowledge (SKILL.md files) - presales / SAP practice edit these, no code change
policy/           numbers and layouts (rates, %, phase splits, sheet headers) as YAML
assets/           SAP Best Practice catalogue, rate card source, YASH Word template
workspace/bids/<bid_id>/
    uploads/ rfp/ ledger/ outputs/ notes/ drafts/ trace/ (events, errors, llm_calls, run.log)
```

To change a rate, a percentage or a sheet header, edit `policy/*.yaml`. To change how agents read the
RFP or write sections, edit `skills/**/SKILL.md`. Both take effect on the next run.

## 9. Troubleshooting

| Symptom | Fix |
|---|---|
| `No model configured for role ...` / HTTP 422 | Set `LLM_MODEL` (and the provider key) in `.env` |
| `this workbook has no '_bid' sheet` | Only workbooks produced by call 1 of this service can be used for call 2. Regenerate it |
| `render ... is unknown here (manifest missing)` | Call 2 must run against the same `WORKSPACE_DIR` as call 1 |
| Table of contents shows old entries | Open the file in Word and accept "update fields" (or right-click the TOC, then Update Field) |
| Sections marked "Draft missing" | The agents did not draft them in the retries allowed. Complete them by hand, or rerun call 2 |
| Need to see what the agents did | `python scripts/trace_view.py <bid_id> --summary` / `--errors` (see section 5) and `ledger/ledger.json` |
| Agent produced nothing / section missing | `trace_view.py <bid_id> --agent <name> --kind model_call,tool,ledger_rejected` shows each call and why writes were rejected |
