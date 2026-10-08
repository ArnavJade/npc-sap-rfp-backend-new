"""Presales UI for the SAP RFP agent (talks to the FastAPI service over HTTP).

    uvicorn app.main:app --port 8000          # the service (src on the path / pip install -e .)
    streamlit run ui/streamlit_app.py         # this UI; API_URL defaults to http://localhost:8000

Tabs: 1) new bid: upload the RFP, follow the agents, download the effort workbook;
2) proposal: upload the reviewed workbook (+ RFP) and instructions, download the YASH .docx;
3) bids: every bid on the server with its outputs and ledger.
"""

from __future__ import annotations

import os
import time

import httpx
import streamlit as st

API = os.getenv("API_URL", "http://localhost:8000").rstrip("/")
POLL_SECONDS = 2.0

st.set_page_config(page_title="SAP RFP Agent", layout="wide")


def api(method: str, path: str, **kwargs) -> httpx.Response:
    with httpx.Client(base_url=API, timeout=120) as client:
        return client.request(method, path, **kwargs)


def show_error(resp: httpx.Response) -> None:
    try:
        detail = resp.json().get("detail") or resp.json().get("error") or resp.text
    except ValueError:
        detail = resp.text
    st.error(f"{resp.status_code}: {detail}")


def follow_job(job_id: str) -> dict | None:
    """Poll a job until it ends, showing its stage and the latest agent/tool events."""
    status_box, events_box = st.empty(), st.empty()
    while True:
        resp = api("GET", f"/jobs/{job_id}")
        if resp.status_code != 200:
            show_error(resp)
            return None
        job = resp.json()
        status_box.info(f"Job {job_id}: **{job['status']}** - stage: {job.get('stage') or 'queued'}")
        lines = []
        for event in job.get("events", [])[-20:]:
            kind, agent = event.get("kind"), event.get("agent") or ""
            bad = kind in ("model_error", "tool_error", "stage_error", "run_error", "ledger_rejected") \
                or event.get("ok") is False
            mark = "**ERROR** " if bad else ""
            if kind == "tool":
                lines.append(f"- {mark}`{agent}` -> `{event.get('tool')}` ({event.get('ms', 0)} ms)")
            elif kind == "model_call":
                calls = ", ".join(c.get("name", "") for c in event.get("tool_calls", []))
                lines.append(f"- `{agent}` model {event.get('ms', 0)} ms, tokens {event.get('input_tokens')}/"
                             f"{event.get('output_tokens')}" + (f" -> {calls}" if calls else ""))
            elif bad:
                lines.append(f"- {mark}{kind} `{agent}` {event.get('error_type', '')} "
                             f"{(event.get('error') or event.get('reasons') or '')}"[:400])
            elif kind in ("agent_start", "agent_end", "stage", "stage_end", "coverage", "output", "run_end"):
                lines.append(f"- {kind} `{agent}` {event.get('stage') or event.get('file') or event.get('gaps') or ''}")
        events_box.markdown("\n".join(lines) or "_waiting for the first agent step..._")
        if job["status"] in ("succeeded", "failed"):
            if job["status"] == "failed":
                st.error(job.get("error") or "job failed")
                if job.get("error_traceback"):
                    with st.expander("Traceback"):
                        st.code(job["error_traceback"])
                diagnostics(job["bid_id"])
                return None
            status_box.success(f"Job {job_id} finished.")
            diagnostics(job["bid_id"])
            return job
        time.sleep(POLL_SECONDS)


def diagnostics(bid_id: str) -> None:
    """Per-agent calls / tokens / errors and every failure point of the bid's runs."""
    resp = api("GET", f"/bids/{bid_id}/trace/summary")
    if resp.status_code != 200:
        return
    summary = resp.json()
    with st.expander(f"Diagnostics - {len(summary.get('errors', []))} failure point(s)"):
        st.write(summary.get("totals", {}))
        st.dataframe([{"agent": name, **{k: v for k, v in stats.items() if k != "tools"}}
                      for name, stats in summary.get("agents", {}).items()], use_container_width=True)
        if summary.get("stages"):
            st.dataframe(summary["stages"], use_container_width=True)
        for error in summary.get("errors", []):
            st.error(f"{error.get('kind')} {error.get('agent', '')} {error.get('tool', '')}: "
                     f"{error.get('error_type', '')} {error.get('error') or error.get('result') or ''}"[:800])


def download(bid_id: str, name: str, label: str) -> None:
    resp = api("GET", f"/bids/{bid_id}/files/{name}")
    if resp.status_code == 200:
        st.download_button(label, resp.content, file_name=name, key=f"dl-{bid_id}-{name}")
    else:
        show_error(resp)


def ledger_summary(bid_id: str) -> None:
    resp = api("GET", f"/bids/{bid_id}")
    if resp.status_code != 200:
        show_error(resp)
        return
    bid = resp.json()
    cols = st.columns(3)
    cols[0].metric("Client", bid.get("client_name", "-"))
    summary = bid.get("summary") or {}
    if summary:
        cols[1].metric("Total project effort (PD)", f"{summary.get('total_project_effort', 0):,.2f}")
        cols[2].metric("Total project cost (USD)", f"{summary.get('total_project_cost_usd', 0):,.0f}")
    st.dataframe([{"section": k, **v} for k, v in (bid.get("sections") or {}).items()], use_container_width=True)


st.title("SAP RFP Agent")
st.caption(f"API: {API}")
try:
    health = api("GET", "/health").json()
    missing = [r for r, m in health.get("models", {}).items() if m == "(not configured)"]
    if missing:
        st.warning(f"No model configured for roles {missing}: set LLM_MODEL on the server or enter one below.")
except httpx.HTTPError as exc:
    st.error(f"API not reachable at {API}: {exc}")
    st.stop()

tab1, tab2, tab3 = st.tabs(["1. New bid -> effort workbook", "2. Reviewed workbook -> proposal", "Bids"])

with tab1:
    with st.form("effort"):
        client_name = st.text_input("Client name", "Client")
        files = st.file_uploader("RFP files", accept_multiple_files=True,
                                 type=["pdf", "docx", "pptx", "xlsx", "csv", "txt", "md"])
        sheet = st.selectbox("Rate card", ["SAP BP", "YASH BP"])
        model = st.text_input("Model for this run (optional, LiteLLM string)", "")
        submitted = st.form_submit_button("Build effort workbook")
    if submitted:
        if not files:
            st.warning("Upload at least one RFP file.")
        else:
            resp = api("POST", "/bids", data={"client_name": client_name, "rate_card_sheet": sheet, "model": model},
                       files=[("files", (f.name, f.getvalue())) for f in files])
            if resp.status_code != 202:
                show_error(resp)
            else:
                st.session_state["bid_id"] = resp.json()["bid_id"]
                job = follow_job(resp.json()["job_id"])
                if job:
                    result = job["result"]
                    if result.get("gaps"):
                        st.warning(f"Sections the agents did not produce: {result['gaps']}")
                    ledger_summary(result["bid_id"])
                    download(result["bid_id"], result["workbook"], "Download effort workbook")
                    st.info("Review and edit the workbook, then use tab 2 (any workbook in this template layout works there).")

with tab2:
    with st.form("proposal"):
        workbook = st.file_uploader("Reviewed effort workbook", type=["xlsx", "xlsm"])
        rfp = st.file_uploader("RFP files (optional - only if not the same as call 1)", accept_multiple_files=True)
        instructions = st.text_area("Presales instructions (optional)", "")
        model2 = st.text_input("Model for this run (optional)", "", key="model2")
        go = st.form_submit_button("Generate proposal")
    if go:
        if workbook is None:
            st.warning("Upload the reviewed workbook.")
        else:
            files = [("workbook", (workbook.name, workbook.getvalue()))]
            files += [("rfp_files", (f.name, f.getvalue())) for f in (rfp or [])]
            resp = api("POST", "/proposals", data={"instructions": instructions, "model": model2}, files=files)
            if resp.status_code != 202:
                show_error(resp)
            else:
                job = follow_job(resp.json()["job_id"])
                if job:
                    result = job["result"]
                    if result.get("missing_drafts"):
                        st.warning(f"Sections without a draft (marked in the document): {result['missing_drafts']}")
                    download(result["bid_id"], result["document"], "Download YASH response (.docx)")

with tab3:
    resp = api("GET", "/bids")
    bids = resp.json() if resp.status_code == 200 else []
    if not bids:
        st.write("No bids yet.")
    for bid in bids:
        with st.expander(f"{bid.get('client_name', '-')} - {bid['bid_id']} ({bid.get('status', '')})"):
            ledger_summary(bid["bid_id"])
            for name in bid.get("outputs", []):
                download(bid["bid_id"], name, f"Download {name}")
            if st.button("Show ledger JSON", key=f"ledger-{bid['bid_id']}"):
                st.json(api("GET", f"/bids/{bid['bid_id']}/ledger").json())
