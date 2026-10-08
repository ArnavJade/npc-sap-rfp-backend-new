"""Provider-safe tool schemas.

The ledger models use "" as the "not set" value of several enum fields (e.g.
`Wave.kind: Literal["template_build", ..., ""]`), so pydantic emits `"enum": [..., ""]` in the
tool's JSON schema. OpenAI and Anthropic accept that; Gemini rejects it with
`...enum[3]: cannot be empty` (HTTP 400), which aborted every effort run on Gemini at the first
model call. The models keep "" (it is the field default, so the agent can simply omit the field);
only the schema sent to the provider is cleaned, at the one point every agent binds its tools.
"""

from __future__ import annotations

from typing import Any


def clean_schema(node: Any) -> Any:
    """Copy of a JSON schema without empty / null enum values; an enum left empty is dropped."""
    if isinstance(node, list):
        return [clean_schema(item) for item in node]
    if not isinstance(node, dict):
        return node
    out: dict[str, Any] = {}
    for key, value in node.items():
        if key == "enum" and isinstance(value, list):
            kept = [v for v in value if v not in ("", None)]
            if kept:
                out[key] = kept
            continue
        out[key] = clean_schema(value)
    return out


def safe_tools(tools: list[Any]) -> list[dict[str, Any]]:
    """Tools (BaseTool / pydantic / callables / dicts) as cleaned OpenAI-format tool dicts."""
    from langchain_core.utils.function_calling import convert_to_openai_tool

    return [clean_schema(convert_to_openai_tool(tool)) for tool in tools]
