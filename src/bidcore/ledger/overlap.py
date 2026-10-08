"""Cross-section overlap checks: the same system or product priced in two places.

Ported from effort_calculator_layer4.py (`_normalize_system_name`, `_is_cross_list_duplicate`,
`dedupe_others_against_third_party`, `dedupe_others_against_scope_sheets`,
`warn_catalogue_grc_overlap`). The old pipeline silently dropped the losing row; here the
checks only REPORT, with the suggested winner, and the effort orchestrator resolves each one
through `ledger_resolve_overlap` so the decision is visible in the audit trail.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from bidcore.ledger.models import Ledger

_NOISE_SUFFIXES = frozenset({
    "system", "systems", "platform", "software", "solution", "solutions", "tool", "tools", "db",
    "database", "app", "application", "module", "service", "services", "server", "suite",
})
_SPLIT = re.compile(r"[^a-z0-9]+")


def normalize_system_name(name: str) -> str:
    """'Marel system' -> 'marel'; '' for empty input."""
    if not name or not isinstance(name, str):
        return ""
    tokens = [t for t in _SPLIT.split(name.lower()) if t]
    while tokens and tokens[-1] in _NOISE_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def _token_norm(value: str) -> str:
    return _SPLIT.sub(" ", (value or "").lower()).strip()


def cross_list_match(name_norm: str, others: dict[str, str]) -> str | None:
    """Matching display name when `name_norm` duplicates an entry of `others` (exact, same
    letters without spaces, or token-boundary containment either way)."""
    if not name_norm:
        return None
    if name_norm in others:
        return others[name_norm]
    compact = name_norm.replace(" ", "")
    for norm, display in others.items():
        if norm.replace(" ", "") == compact:
            return display
    padded = f" {name_norm} "
    for norm, display in others.items():
        if f" {norm} " in padded or padded in f" {norm} ":
            return display
    return None


@dataclass
class Overlap:
    kind: str
    keep_section: str
    keep_row_id: str
    drop_section: str
    drop_row_id: str
    detail: str

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def find_overlaps(ledger: Ledger) -> list[Overlap]:
    out: list[Overlap] = []
    nc_rows = ledger.non_catalogue.rows

    # Integrations win over a non-catalogue duplicate: they carry the interface columns.
    integ = {normalize_system_name(r.system): r for r in ledger.integrations.rows if r.system}
    integ_names = {k: v.system for k, v in integ.items() if k}
    for nc in nc_rows:
        match = cross_list_match(normalize_system_name(nc.name), integ_names)
        if match:
            keep = next(r for k, r in integ.items() if r.system == match)
            out.append(Overlap("integration_vs_non_catalogue", "integrations", keep.row_id,
                               "non_catalogue", nc.row_id,
                               f"'{nc.name}' is also integration '{match}' - price it once, as the integration."))

    # Security / Analytics sheets win over non-catalogue SAP security/analytics products.
    sheet_rows: list[tuple[str, str, str]] = []   # (section, row_id, name)
    for r in ledger.security.rows:
        for name in (r.sap_product, r.activity):
            if name:
                sheet_rows.append(("security", r.row_id, name))
    for r in ledger.analytics.rows:
        if r.object:
            sheet_rows.append(("analytics", r.row_id, r.object))
    products = {normalize_system_name(n): (s, rid, n) for s, rid, n in sheet_rows if normalize_system_name(n)}
    for nc in nc_rows:
        norm = normalize_system_name(nc.name)
        hit = cross_list_match(norm, {k: k for k in products})
        if hit is None and norm and norm != "sap":
            hit = next((k for k in products if f" {norm} " in f" {_token_norm(products[k][2])} "), None)
        if hit:
            section, rid, name = products[hit]
            out.append(Overlap(f"{section}_vs_non_catalogue", section, rid, "non_catalogue", nc.row_id,
                               f"'{nc.name}' is already on the {section} sheet as '{name}'."))

    # Catalogue GRC scope items vs a GRC product on the Security sheet: flag only.
    grc_security = [r for r in ledger.security.rows if " grc " in f" {_token_norm(r.sap_product or r.activity)} "]
    grc_catalogue = [s for s in ledger.scope_items.rows
                     if "risk and compliance" in _token_norm(s.business_area) or " grc " in f" {_token_norm(s.description)} "]
    if grc_security and grc_catalogue:
        out.append(Overlap("catalogue_grc_vs_security", "security", grc_security[0].row_id, "scope_items",
                           grc_catalogue[0].row_id,
                           "GRC appears both as catalogue scope and on the Security sheet - the same effort may "
                           "be counted twice. Keep one unless the RFP clearly asks for both."))
    return out
