"""RFP ingestion: client files -> page-marked Markdown workspace (see workspace.py for the contract)."""

from .images import VISION_PROMPT, vision_prompt
from .models import IngestedFile, IngestResult
from .workspace import build_index, ingest, list_pages, read_section

__all__ = ["VISION_PROMPT", "IngestResult", "IngestedFile", "build_index", "ingest", "list_pages",
           "read_section", "vision_prompt"]
