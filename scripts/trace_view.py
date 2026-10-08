"""Inspect a bid's run trace while it runs or afterwards.

    python scripts/trace_view.py <bid_id>                 # all events, one line each
    python scripts/trace_view.py <bid_id> --follow        # live tail (Ctrl+C to stop)
    python scripts/trace_view.py <bid_id> --errors        # failure points with tracebacks
    python scripts/trace_view.py <bid_id> --summary       # per-agent calls, tokens, latency, errors; stage timings
    python scripts/trace_view.py <bid_id> --agent scope-security --kind model_call,tool
    python scripts/trace_view.py <bid_id> --llm --agent rfp-analyst   # full model-call records

<bid_id> may also be a path to a bid folder or its trace/ folder.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from harness.observability import format_event, is_error, load_events, summarize  # noqa: E402


def trace_dir(arg: str) -> Path:
    path = Path(arg)
    if path.is_dir():
        return path if path.name == "trace" else path / "trace"
    from bidcore.paths import workspace_dir

    found = workspace_dir() / "bids" / arg / "trace"
    if not found.is_dir():
        sys.exit(f"no trace for bid '{arg}' under {found.parent.parent}")
    return found


def show(events: list[dict], errors: bool, full: bool = False) -> None:
    for e in events:
        print(time.strftime("%H:%M:%S", time.localtime(e.get("ts", 0))), format_event(e))
        if errors and e.get("traceback"):
            lines = e["traceback"].rstrip().splitlines()
            if not full and len(lines) > 25:          # the root cause is at the end; middleware frames come first
                lines = ["... (--full for the whole traceback)"] + lines[-25:]
            print("    " + "\n    ".join(lines))
        if errors and e.get("reasons"):
            for reason in e["reasons"]:
                print(f"    - {reason}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("bid")
    parser.add_argument("--follow", action="store_true")
    parser.add_argument("--errors", action="store_true", help="failure points only, with tracebacks")
    parser.add_argument("--full", action="store_true", help="whole tracebacks with --errors")
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--agent", default="")
    parser.add_argument("--kind", default="", help="comma list, e.g. model_call,tool,ledger_rejected")
    parser.add_argument("--llm", action="store_true", help="print llm_calls.jsonl records")
    args = parser.parse_args()
    directory = trace_dir(args.bid)
    kinds = {k.strip() for k in args.kind.split(",") if k.strip()} or None

    if args.llm:
        path = directory / "llm_calls.jsonl"
        for line in path.read_text(encoding="utf-8").splitlines() if path.is_file() else []:
            record = json.loads(line)
            if not args.agent or record.get("agent") == args.agent:
                print(json.dumps(record, indent=1, ensure_ascii=False))
        return
    if args.summary:
        print(json.dumps(summarize(load_events(directory)), indent=1, ensure_ascii=False, default=str))
        return
    events = load_events(directory, kinds=kinds, agent=args.agent or None, errors_only=args.errors)
    show(events, args.errors, args.full)
    if not args.follow:
        return
    last = events[-1]["ts"] if events else 0.0
    try:
        while True:
            time.sleep(1.0)
            fresh = load_events(directory, kinds=kinds, agent=args.agent or None, errors_only=args.errors, since=last)
            show(fresh, args.errors, args.full)
            if fresh:
                last = fresh[-1]["ts"]
                if any(e.get("kind") in ("run_end", "run_error") for e in fresh):
                    print("-- run finished --")
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
