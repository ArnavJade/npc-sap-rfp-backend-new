"""read_section: pull a page range or a heading's block out of the ingested RFP.

Complements the harness's own ls/read_file/glob/grep on /rfp/: grep finds where something is said,
read_section returns just those pages, so no agent ever loads a 150-page RFP into its context.
"""

from __future__ import annotations

from pathlib import PurePosixPath

from langchain_core.tools import BaseTool, StructuredTool, ToolException
from pydantic import BaseModel, Field

from harness.context import RunContext


class _ReadSection(BaseModel):
    file: str = Field(description="RFP workspace file, e.g. '/rfp/main-rfp.md' (see /rfp/index.md).")
    page_from: int | None = Field(None, description="First page/slide/block marker to read.")
    page_to: int | None = Field(None, description="Last page to read (inclusive); default = page_from.")
    heading: str = Field("", description="Alternatively: read the block under this heading text.")


def make_rfp_tools(run: RunContext) -> list[BaseTool]:
    def read_section(file: str, page_from: int | None = None, page_to: int | None = None, heading: str = "") -> str:
        from bidcore.ingest import read_section as _read   # ingestion layer owns the marker format

        name = PurePosixPath(file.replace("\\", "/")).name
        if not (run.ws.rfp / name).is_file() or name == "index.md":
            available = ", ".join(sorted(p.name for p in run.ws.rfp.glob("*.md") if p.name != "index.md"))
            raise ToolException(f"'{file}' is not an RFP file. Available: {available}")
        if page_from is None and not heading:
            raise ToolException("give page_from (and optionally page_to) or a heading")
        return _read(run.ws.rfp, name, page_from=page_from, page_to=page_to, heading=heading)

    return [StructuredTool.from_function(
        func=read_section, name="read_section", args_schema=_ReadSection, handle_tool_error=True,
        description="Read specific pages (or the block under a heading) of an RFP file. Use grep on /rfp/ first "
                    "to find where something is, then read just those pages.")]
