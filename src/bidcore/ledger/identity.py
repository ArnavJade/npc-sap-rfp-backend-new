"""Row identity per ledger section: when two rows are the same thing, and how a repeat merges.

Agents write incrementally and repeat themselves - a retried turn, a resent batch, a second source naming
the same system. The third live run appended every repeat (31 integration rows for 22 systems, Basis 18
for 12, Security 11 for 7). With an identity per section a write is an upsert: a row that matches one
already saved is merged into it (blank fields filled, lists joined, counts kept at the maximum) instead
of being added again, so writing the same thing twice is harmless.

Identities follow the old pipeline's merge keys (data_migration_scope.merge_data_migration,
basis_scope.merge_basis, security_scope.merge_security, analytics_scope.merge_analytics,
effort_calculator_layer4._normalize_system_name):
  capabilities    capability wording (+ scope type)
  scope_items     scope item id (+ status)
  non_catalogue   normalised tool name
  integrations    normalised system name ('ARASCO Sadad DB' = 'Arasco Sadad'), or one name containing the other
  data_migration  (area, object) - the same object under two RFP areas is two rows by design
  basis           activity wording
  security        activity wording, one containing the other, or the same SAP product
  analytics       (object, object type)
"""

from __future__ import annotations

import re
from typing import Any, Callable

from pydantic import BaseModel

from bidcore.ledger.overlap import cross_list_match, normalize_system_name

_WORDS = re.compile(r"[^a-z0-9]+")
MAX_FIELDS = ("interface_count", "no_of_objects")       # counts: keep the larger
SKIP_FIELDS = {"row_id", "written_by", "note"}


def norm(value: Any) -> str:
    return " ".join(_WORDS.split(str(value or "").lower())).strip()


def _contains(a: str, b: str) -> bool:
    """Token-boundary containment either way ('role design' in 'role design and build')."""
    return bool(a and b) and (f" {a} " in f" {b} " or f" {b} " in f" {a} ")


def _system(row: Any) -> str:
    return normalize_system_name(getattr(row, "system", "") or getattr(row, "name", ""))


_KEYS: dict[str, Callable[[Any], tuple]] = {
    "capabilities": lambda r: (norm(r.capability), r.scope_type),
    "scope_items": lambda r: (r.scope_item_id.strip().upper(), r.status),
    "non_catalogue": lambda r: (_system(r),),
    "integrations": lambda r: (_system(r),),
    "data_migration": lambda r: (norm(r.object), norm(r.module or r.sap_module)),
    "basis": lambda r: (norm(r.activity),),
    "security": lambda r: (norm(r.activity),),
    "analytics": lambda r: (norm(r.object), r.object_type),
}


def row_key(section: str, row: Any) -> tuple | None:
    """The section's identity of `row`, name first; None when the row has no name to compare."""
    fn = _KEYS.get(section)
    if fn is None:
        return None
    key = fn(row)
    return key if key[0] else None


def same_row(section: str, a: Any, b: Any) -> bool:
    """Do `a` and `b` describe the same item of `section`?"""
    ka, kb = row_key(section, a), row_key(section, b)
    if ka is None or kb is None:
        return False
    if ka == kb:
        return True
    if section == "integrations":
        return cross_list_match(ka[0], {kb[0]: kb[0]}) is not None
    if section == "security":
        pa, pb = norm(a.sap_product), norm(b.sap_product)
        return _contains(ka[0], kb[0]) or bool(pa and pa == pb)
    return False


def find_twin(section: str, rows: list[Any], row: Any, exclude: str = "") -> Any | None:
    """The saved row `row` duplicates (None when it is new)."""
    return next((r for r in rows if r.row_id != exclude and same_row(section, r, row)), None)


def _empty(value: Any, default: Any) -> bool:
    return value is None or value == default or value == "" or value == [] or value == {}


def merge_into(twin: BaseModel, row: BaseModel) -> list[str]:
    """Fold `row` into the saved `twin`: fields still at their default take the new value, lists are
    joined (evidence by quote), counts keep the maximum. Returns the names of the fields that changed."""
    changed: list[str] = []
    for name, info in type(twin).model_fields.items():
        if name in SKIP_FIELDS:
            continue
        old, new = getattr(twin, name), getattr(row, name, None)
        if _empty(new, info.get_default(call_default_factory=True)):
            continue
        if isinstance(old, list):
            seen = {_list_key(x) for x in old}
            extra = [x for x in new if _list_key(x) not in seen]
            if extra:
                setattr(twin, name, [*old, *extra])
                changed.append(name)
        elif name in MAX_FIELDS and isinstance(new, (int, float)) and new > (old or 0):
            setattr(twin, name, new)
            changed.append(name)
        elif _empty(old, info.get_default(call_default_factory=True)) and new != old:
            setattr(twin, name, new)
            changed.append(name)
    return changed


def _list_key(item: Any) -> Any:
    if isinstance(item, BaseModel):
        quote = getattr(item, "quote", None)
        return norm(quote) if quote is not None else item.model_dump_json()
    return norm(item) if isinstance(item, str) else item


def duplicates(section: str, rows: list[Any]) -> list[tuple[str, str]]:
    """(kept row_id, duplicate row_id) pairs among `rows` - for the ledger checks."""
    pairs, kept = [], []
    for r in rows:
        twin = next((k for k in kept if same_row(section, k, r)), None)
        if twin is None:
            kept.append(r)
        else:
            pairs.append((twin.row_id, r.row_id))
    return pairs
