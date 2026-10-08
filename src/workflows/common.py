"""Pieces shared by the two outer state machines (call 1 and call 2)."""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path
from typing import Any, Awaitable, Callable

from langchain_core.messages import BaseMessage

from bidcore.ledger.models import Ledger, SourceFile
from harness.context import RunContext
from harness.observability import bind, error_info


def staged(run: RunContext, name: str, fn: Callable[[Any], Awaitable[dict]]) -> Callable[[Any], Awaitable[dict]]:
    """A workflow node with observability: stage start / end with duration, the stage bound into
    every log record and trace event inside it, and any failure recorded with its traceback
    (stage_error) before it propagates."""
    async def node(state: Any) -> dict:
        started = time.time()
        with bind(stage=name):
            run.trace.emit("stage", "", stage=name)
            try:
                result = await fn(state)
            except Exception as exc:
                run.trace.emit("stage_error", "", stage=name, ms=int((time.time() - started) * 1000), **error_info(exc))
                raise
            run.trace.emit("stage_end", "", stage=name, ms=int((time.time() - started) * 1000),
                           updates=sorted((result or {}).keys()))
            return result
    node.__name__ = name
    return node


def message_text(message: BaseMessage | Any) -> str:
    content = getattr(message, "content", message)
    if isinstance(content, list):
        return "".join(b if isinstance(b, str) else b.get("text", "") for b in content
                       if isinstance(b, str) or (isinstance(b, dict) and b.get("type") == "text"))
    return str(content or "")


def last_ai_text(result: dict) -> str:
    for message in reversed(result.get("messages", [])):
        if getattr(message, "type", "") == "ai":
            text = message_text(message).strip()
            if text:
                return text
    return ""


def make_captioner(run: RunContext):
    """Embedded-image captioning with the 'vision' role model (INGEST_VISION=on), else None."""
    if os.getenv("INGEST_VISION", "off").strip().lower() not in ("on", "1", "true", "yes"):
        return None
    from harness.llm import resolve_model_name

    model = resolve_model_name("vision", run.run_model)
    if not model:
        return None

    def caption(image_bytes: bytes, mime: str, context: str) -> str:
        import base64

        import litellm
        from bidcore.ingest import vision_prompt

        data = base64.b64encode(image_bytes).decode()
        response = litellm.completion(model=model, messages=[{"role": "user", "content": [
            {"type": "text", "text": vision_prompt(context[:1500])},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}},
        ]}], max_tokens=2000)
        return response.choices[0].message.content or ""
    return caption


def ingest_uploads(run: RunContext, uploads: list[Path]) -> list[SourceFile]:
    """Uploaded RFP files -> page-marked Markdown workspace (/rfp/) + source-file records."""
    from bidcore.ingest import ingest

    files = [(p.name, p.read_bytes()) for p in uploads]
    result = ingest(files, run.ws.rfp, caption=make_captioner(run), cache_dir=run.ws.cache)
    run.reset_corpus()
    sources = []
    for f in result.files:
        sources.append(SourceFile(name=f.name, sha256=f.sha256, workspace_md=f.md_path, pages=f.pages))
    run.trace.emit("ingested", "", files=[s.name for s in sources], chars=result.total_chars,
                   anchors=len(result.wave_anchors))
    return sources


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def record_sources(ledger: Ledger, sources: list[SourceFile]) -> None:
    known = {s.sha256 for s in ledger.meta.files}
    ledger.meta.files.extend(s for s in sources if s.sha256 not in known)
