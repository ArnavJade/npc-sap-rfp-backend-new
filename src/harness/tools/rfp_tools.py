"""read_section / read_next_pages: pull pages of the ingested RFP, and record what each agent read.

Complements the harness's own ls/read_file/glob/grep on /rfp/: grep finds where something is said,
read_section returns just those pages, so no agent ever loads a 150-page RFP into one tool result.
read_next_pages walks the RFP in order from the first page this agent has not read yet - the old
pipeline's chunk scan as a tool. Every page an agent reads is recorded (RunContext.pages_read): an
agent may only record a section as empty, or finish, once it has read the RFP (see ledger_tools and
harness.recovery.SectionCompletionMiddleware).
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from langchain_core.tools import BaseTool, StructuredTool, ToolException
from pydantic import BaseModel, Field

from harness.context import RunContext, page_ranges

_MARKER_RE = re.compile(r"^<!-- page: (\d+) -->$", re.MULTILINE)
NEXT_PAGES_MAX_CHARS = 18_000


class _ReadSection(BaseModel):
    file: str = Field(description="RFP workspace file, e.g. '/rfp/main-rfp.md' (see /rfp/index.md).")
    page_from: int | None = Field(None, description="First page/slide/block marker to read.")
    page_to: int | None = Field(None, description="Last page to read (inclusive); default = page_from.")
    heading: str = Field("", description="Alternatively: read the block under this heading text.")


class _NextPages(BaseModel):
    max_pages: int = Field(8, description="At most this many pages (capped at 18,000 characters).")


def pages_in(text: str) -> list[int]:
    return [int(m.group(1)) for m in _MARKER_RE.finditer(text or "")]


def make_rfp_tools(run: RunContext, agent: str = "") -> list[BaseTool]:
    def read_section(file: str, page_from: int | None = None, page_to: int | None = None, heading: str = "") -> str:
        from bidcore.ingest import read_section as _read   # ingestion layer owns the marker format

        name = PurePosixPath(file.replace("\\", "/")).name
        if not (run.ws.rfp / name).is_file() or name == "index.md":
            available = ", ".join(sorted(p.name for p in run.ws.rfp.glob("*.md") if p.name != "index.md"))
            raise ToolException(f"'{file}' is not an RFP file. Available: {available}")
        if page_from is None and not heading:
            raise ToolException("give page_from (and optionally page_to) or a heading")
        text = _read(run.ws.rfp, name, page_from=page_from, page_to=page_to, heading=heading)
        if agent:
            run.mark_read(agent, name, pages_in(text))
        return text

    def read_next_pages(max_pages: int = 8) -> str:
        from bidcore.ingest import read_section as _read

        unread = run.unread_pages(agent)
        if not unread:
            return "You have read every page of the RFP. Write your sections now."
        max_pages = max(1, min(int(max_pages or 8), 20))
        file = unread[0][0]
        chosen = [p for f, p in unread if f == file][:max_pages]
        sizes = {p: c for f, p, c in run.rfp_pages() if f == file}
        picked, total = [], 0
        for page in chosen:          # consecutive unread pages of one file, within the character cap
            if picked and (page != picked[-1] + 1 or total + sizes.get(page, 0) > NEXT_PAGES_MAX_CHARS):
                break
            picked.append(page)
            total += sizes.get(page, 0)
        text = _read(run.ws.rfp, file, page_from=picked[0], page_to=picked[-1], max_chars=NEXT_PAGES_MAX_CHARS)
        got = pages_in(text) or picked[:1]
        run.mark_read(agent, file, got)
        left = run.unread_pages(agent)
        tail = (f"\n\n[read_next_pages: /rfp/{file} p.{got[0]}-{got[-1]}; {len(left)} page(s) still unread"
                + (f" ({page_ranges(left)[:300]}) - call read_next_pages again]" if left else " - you have read the whole RFP]"))
        return text + tail

    tools = [StructuredTool.from_function(
        func=read_section, name="read_section", args_schema=_ReadSection, handle_tool_error=True,
        description="Read specific pages (or the block under a heading) of an RFP file. Use grep on /rfp/ first "
                    "to find where something is, then read just those pages.")]
    if agent:
        tools.append(StructuredTool.from_function(
            func=read_next_pages, name="read_next_pages", args_schema=_NextPages, handle_tool_error=True,
            description="Read the next pages of the RFP you have not read yet, in order (about 8 pages per call). "
                        "Call it repeatedly to read the whole RFP; the reply says what is still unread."))
    return tools
