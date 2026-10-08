"""Result models and the on-disk format of the ingested RFP workspace.

WHY this module exists: the workspace format - one `rfp/<slug>.md` per client file, pages
introduced by a line that is exactly `<!-- page: N -->`, tables wrapped in
`[EXTRACTED TABLE -- p.N]` blocks and image transcriptions in `[EMBEDDED IMAGE -- p.N]` blocks
(the block format of the old aperture/merge.py) - is a contract between this package, the
evidence grounding in `bidcore.evidence` (which strips the markers before matching quotes) and
the skills that teach agents to grep/read `rfp/*.md`.  Defining the markers here, next to the
result models, keeps that contract in one place.

Public results are pydantic because they leave the package (job records, ledger hooks).  The
in-flight shapes (`Page`, `ImageRef`, `Extracted`) are plain dataclasses: they carry raw image
bytes and never cross a process boundary.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from functools import cached_property
from typing import Any

from pydantic import BaseModel, Field

PAGE_MARKER_RE = re.compile(r"^<!-- page: (\d+) -->$", re.MULTILINE)
TABLE_BLOCK_RE = re.compile(
    r"^\[EXTRACTED TABLE -- (?P<where>[^\]\n]*)\]\n(?P<body>.*?)\n\[END EXTRACTED TABLE\]$",
    re.MULTILINE | re.DOTALL,
)
IMAGE_BLOCK_RE = re.compile(
    r"^\[EMBEDDED IMAGE -- [^\]\n]*\]\n.*?\n\[END EMBEDDED IMAGE\]$", re.MULTILINE | re.DOTALL
)

# Size of a synthetic page (DOCX/TXT/MD/CSV/XLSX blocks): the old ingestion router's pseudo-page.
BLOCK_CHARS = 3000


def page_marker(number: int) -> str:
    return f"<!-- page: {number} -->"


def table_block(page: int, table_md: str, *, continued: bool = False) -> str:
    where = f"p.{page} (continued)" if continued else f"p.{page}"
    return f"[EXTRACTED TABLE -- {where}]\n{table_md.strip()}\n[END EXTRACTED TABLE]"


def image_block(page: int, content: str) -> str:
    return f"[EMBEDDED IMAGE -- p.{page}]\n{content.strip()}\n[END EMBEDDED IMAGE]"


class IngestedFile(BaseModel):
    """One client file as written to the workspace."""

    name: str  # original filename
    slug: str  # unique per run; the Markdown lives at rfp/<slug>.md
    md_path: str  # workspace-relative, e.g. 'rfp/<slug>.md'
    kind: str  # pdf | docx | pptx | xlsx | csv | txt | md | unsupported
    pages: int = 0  # number of page markers (physical pages only for pdf/pptx)
    sha256: str = ""
    chars: int = 0
    tables: int = 0
    images_captioned: int = 0
    warnings: list[str] = Field(default_factory=list)


class IngestResult(BaseModel):
    """Everything `ingest()` produced; the deterministic pre-scans feed hooks and the index."""

    files: list[IngestedFile] = Field(default_factory=list)
    index_path: str = ""
    wave_anchors: list[dict[str, Any]] = Field(default_factory=list)  # {file, page, text}
    declared_waves: list[dict[str, Any]] = Field(default_factory=list)
    sequencing_hint: str = ""  # sequential | parallel | staggered | ''
    third_party_candidates: list[dict[str, Any]] = Field(default_factory=list)  # {name, file, page, evidence}
    total_chars: int = 0


@dataclass(eq=False)
class ImageRef:
    """An embedded image at its position in a page; `caption` is filled by images.process_images."""

    data: bytes
    mime: str
    width: int | None = None
    height: int | None = None
    context: str = ""  # nearby text, passed to the captioner for orientation
    caption: str = ""
    duplicate_of: int | None = None  # page of the first occurrence of the same bytes

    @cached_property
    def sha1(self) -> str:
        return hashlib.sha1(self.data).hexdigest()


@dataclass
class Page:
    """One marker-delimited page: rendered Markdown strings and image placeholders, in order."""

    number: int
    parts: list[str | ImageRef] = field(default_factory=list)


@dataclass
class Extracted:
    """A converter's output for one file."""

    pages: list[Page]
    warnings: list[str] = field(default_factory=list)
    unit_note: str = ""  # what a page marker means for this format, shown in the file header
