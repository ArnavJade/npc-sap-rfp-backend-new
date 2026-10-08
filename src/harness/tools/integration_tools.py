"""Recall aids for the integrations specialist: every place a third-party system can hide, gathered
deterministically so a weak model cannot skip it.

The second live ARASCO run found 6 of the 24 integrations in the reference workbook: the agent read
the integration diagram page only, while most systems were listed in the annexure of legacy
applications ("13.1 Legacy Applications details & Integrations required") and in diagram text.
`integration_candidates` returns, with page numbers:
  1. the table-scan candidates the ingestion layer found (named-system table columns);
  2. every diagram text block (pymupdf "picture text", vision transcriptions of images);
  3. the list / table lines of every page that talks about integrations, interfaces, legacy or
     third-party applications.
`uncovered_candidates` is used by the integrations write tool to say which table-scan candidates no
row covers yet.
"""

from __future__ import annotations

import json
import re

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel

from bidcore.evidence import norm_key
from bidcore.ingest.workspace import split_pages
from harness.context import RunContext

_TOPIC_RE = re.compile(r"integrat|interface|legacy|third[- ]party|3rd[- ]party|non[- ]sap|external system|"
                       r"landscape|applications? (?:in|currently)|in operational use", re.IGNORECASE)
_LIST_LINE_RE = re.compile(r"^\s*(?:[-*•▪◦]|\d+[.)]|\|)")
_PICTURE_RE = re.compile(r"<!-- Start of picture text -->(.*?)<!-- End of picture text -->", re.DOTALL)
_IMAGE_RE = re.compile(r"\[EMBEDDED IMAGE[^\]]*\](.*?)\[END EMBEDDED IMAGE\]", re.DOTALL)
MAX_CHARS = 24_000


def table_scan_candidates(run: RunContext) -> list[dict]:
    path = run.ws.cache / "prescan.json"
    try:
        items = json.loads(path.read_text(encoding="utf-8")).get("third_party_candidates", [])
    except (OSError, ValueError):
        return []
    seen, out = set(), []
    for item in items:
        key = norm_key(item.get("name"))
        if key and key not in seen:
            seen.add(key)
            out.append(item)
    return out


def uncovered_candidates(run: RunContext, systems: list[str]) -> list[str]:
    """Table-scan candidate names that no integration row (by name containment) covers."""
    covered = [norm_key(s) for s in systems if norm_key(s)]
    out = []
    for item in table_scan_candidates(run):
        key = norm_key(item.get("name"))
        if key and not any(key in c or c in key for c in covered):
            out.append(f"{item['name']} (p.{item.get('page', '?')})")
    return out


def _gather(run: RunContext) -> str:
    parts: list[str] = []
    scan = table_scan_candidates(run)
    parts.append("## 1. Table-scan candidates (named-system table columns)")
    parts += [f"- {c['name']} ({c.get('file', '')} p.{c.get('page', '?')})" for c in scan] or ["- none"]
    diagrams, passages = [], []
    for path in sorted(run.ws.rfp.glob("*.md")):
        if path.name == "index.md":
            continue
        for page, body in split_pages(path.read_text(encoding="utf-8", errors="replace")):
            for block in [*_PICTURE_RE.findall(body), *_IMAGE_RE.findall(body)]:
                text = " ".join(block.split())
                if text:
                    diagrams.append(f"- /rfp/{path.name} p.{page}: {text[:1500]}")
            if _TOPIC_RE.search(body):
                lines = [" ".join(line.split()) for line in body.splitlines()
                         if _LIST_LINE_RE.match(line) or _TOPIC_RE.search(line)]
                lines = [line[:300] for line in lines if len(line) > 2][:60]
                if lines:
                    passages.append(f"### /rfp/{path.name} p.{page}\n" + "\n".join(lines))
    parts.append("\n## 2. Diagram text (box labels of diagrams / image transcriptions, often in jumbled order)")
    parts += diagrams or ["- none"]
    parts.append("\n## 3. Lists and tables on pages about integrations, interfaces, legacy or third-party applications")
    parts += passages or ["- none"]
    text = "\n".join(parts)
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + "\n[... cut - read the remaining pages with read_section]"
    return text + ("\n\nEvery non-SAP system named above that must connect to the new SAP landscape is a row in "
                   "integrations (legacy applications being REPLACED by SAP are not). Check each one.")


class _NoArgs(BaseModel):
    pass


def make_integration_tools(run: RunContext) -> list[BaseTool]:
    return [StructuredTool.from_function(
        func=lambda: _gather(run), name="integration_candidates", args_schema=_NoArgs,
        description="Every candidate third-party system in the RFP, with pages: table-scan hits, diagram text and "
                    "the list / table lines of pages about integrations, interfaces and legacy applications. "
                    "Call it first, then confirm each candidate in the RFP text.")]
