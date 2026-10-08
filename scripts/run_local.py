"""Run a bid locally without the API (needs LLM_MODEL or per-role models in .env).

    python scripts/run_local.py effort  --rfp path/to/rfp.pdf [--rfp annex.xlsx] --client "ARASCO" [--sheet "SAP BP"]
    python scripts/run_local.py proposal --workbook reviewed.xlsx [--rfp rfp.pdf] [--instructions "..."]

Call 1 prints the bid id and the workbook path. Call 2 takes any effort workbook in the template layout: it
reuses the call-1 bid when the workbook's hidden `_bid` sheet names one in this WORKSPACE_DIR, else it
builds a new bid from the workbook alone.
Progress (stages, agent starts/ends, tool calls) is printed as it happens; the full trace is in
workspace/bids/<bid_id>/trace/events.jsonl.
"""

from __future__ import annotations

import argparse
import asyncio
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from harness.observability import configure_logging  # noqa: E402

configure_logging()

from app import services  # noqa: E402
from harness import llm  # noqa: E402
from harness.workspace import BidWorkspace, new_bid_id  # noqa: E402


def printer(event: dict) -> None:
    """Live progress is printed by the 'trace' logger (harness.observability); nothing extra here."""


def report(ws: BidWorkspace) -> None:
    from harness.observability import load_events, summarize

    summary = summarize(load_events(ws.trace))
    print("\nRun summary:", summary["totals"])
    for name, stats in summary["agents"].items():
        print(f"  {name:<24} model calls {stats['model_calls']:>3}  tokens in/out {stats['input_tokens']}/"
              f"{stats['output_tokens']}  tool calls {stats['tool_calls']:>3}  tool errors {stats['tool_errors']}  "
              f"ledger rejections {stats['ledger_rejections']}")
    if summary["errors"]:
        print(f"  {len(summary['errors'])} failure point(s): python scripts/trace_view.py {ws.bid_id} --errors")
    print(f"  trace: {ws.trace}  (events.jsonl, errors.jsonl, llm_calls.jsonl, run.log)")


def _copy(ws: BidWorkspace, paths: list[str]) -> list[Path]:
    out = []
    for p in paths:
        src = Path(p)
        if not src.is_file():
            sys.exit(f"no such file: {p}")
        out.append(ws.save_upload(src.name, src.read_bytes()))
    return out


async def effort(args) -> None:
    services.ensure_models_configured("effort", args.model)
    sheet = services.check_rate_card_sheet(args.sheet)
    ws = BidWorkspace.open(new_bid_id())
    uploads = _copy(ws, args.rfp)
    services.prepare_effort(ws, args.client, sheet, llm.models_in_use(args.model))
    print(f"bid {ws.bid_id} -> {ws.root}")
    try:
        result = await services.run_effort(ws, args.client, uploads, args.model, printer)
    finally:
        report(ws)
    print(f"\nworkbook: {ws.outputs / result['workbook']}")
    if result.get("gaps"):
        print(f"sections not produced: {result['gaps']}")


async def proposal(args) -> None:
    services.ensure_models_configured("proposal", args.model)
    services.check_effort_workbook(Path(args.workbook))
    ws = services.proposal_workspace(Path(args.workbook))   # linked call-1 bid, else a new one from the workbook
    print(f"bid {ws.bid_id} -> {ws.root}")
    book = _copy(ws, [args.workbook])[0]
    rfp = _copy(ws, args.rfp or [])
    try:
        result = await services.run_proposal(ws, book, rfp, args.instructions or "", args.model, printer)
    finally:
        report(ws)
    target = ws.outputs / result["document"]
    print(f"\ndocument: {target}")
    if args.out:
        shutil.copy(target, args.out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="call", required=True)
    e = sub.add_parser("effort", help="call 1: RFP -> effort workbook")
    e.add_argument("--rfp", action="append", required=True)
    e.add_argument("--client", default="Client")
    e.add_argument("--sheet", default="")
    e.add_argument("--model", default=None)
    p = sub.add_parser("proposal", help="call 2: reviewed workbook -> YASH .docx")
    p.add_argument("--workbook", required=True)
    p.add_argument("--rfp", action="append")
    p.add_argument("--instructions", default="")
    p.add_argument("--model", default=None)
    p.add_argument("--out", default="")
    args = parser.parse_args()
    try:
        asyncio.run(effort(args) if args.call == "effort" else proposal(args))
    except services.ServiceError as exc:
        sys.exit(str(exc))


if __name__ == "__main__":
    main()
