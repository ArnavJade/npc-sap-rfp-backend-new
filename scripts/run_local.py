"""Run a bid locally without the API (needs LLM_MODEL or per-role models in .env).

    python scripts/run_local.py effort  --rfp path/to/rfp.pdf [--rfp annex.xlsx] --client "ARASCO" [--sheet "SAP BP"]
    python scripts/run_local.py proposal --workbook reviewed.xlsx [--rfp rfp.pdf] [--instructions "..."]

Call 1 prints the bid id and the workbook path; call 2 finds the bid from the workbook's `_bid` sheet.
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

from app import services  # noqa: E402
from harness import llm  # noqa: E402
from harness.workspace import BidWorkspace, new_bid_id  # noqa: E402


def printer(event: dict) -> None:
    kind = event.get("kind")
    if kind == "stage":
        print(f"\n== {event.get('stage')}")
    elif kind in ("agent_start", "agent_end"):
        print(f"  [{event.get('agent')}] {kind.split('_')[1]} {event.get('summary', '')[:120]}")
    elif kind == "tool":
        mark = "" if event.get("ok", True) else "  !! " + str(event.get("result", ""))[:160]
        print(f"    {event.get('agent')} -> {event.get('tool')} {event.get('args') or ''}{mark}")
    elif kind in ("coverage", "output", "ingested", "edits"):
        print(f"  {kind}: { {k: v for k, v in event.items() if k not in ('ts', 'kind', 'agent')} }")


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
    result = await services.run_effort(ws, args.client, uploads, args.model, printer)
    print(f"\nworkbook: {ws.outputs / result['workbook']}")
    if result.get("gaps"):
        print(f"sections not produced: {result['gaps']}")


async def proposal(args) -> None:
    services.ensure_models_configured("proposal", args.model)
    bid_id = services.bid_of_workbook(Path(args.workbook))
    ws = BidWorkspace.open(bid_id, create=False)
    book = _copy(ws, [args.workbook])[0]
    rfp = _copy(ws, args.rfp or [])
    result = await services.run_proposal(ws, book, rfp, args.instructions or "", args.model, printer)
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
