"""Convert the three reference workbooks into the PoC's data and knowledge assets.

    python scripts/build_assets.py            # reads assets/source/*.xlsx

Outputs (all regenerated, all committed):
  assets/catalogue/scope_items.parquet          BP_ID_LIST 'Scope' sheet, one row per scope item
  assets/catalogue/availability.parquet         43-country Yes/No matrix in long format
  assets/catalogue/cross_mapping.parquet        module cross-mapping rulebook (+ parsed filters)
  policy/rate_cards/bp_efforts.parquet          BP_Efforts 'SAP BP' + 'YASH BP', 5-phase person-days
  skills/sap-scope-mapping/reference/cross-mapping-aliases.md   the rulebook as an LLM-readable guide
  skills/sap-scope-mapping/reference/catalogue-structure.md     LOB -> Business Area map with examples
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bidcore.catalogue.crossmap import parse_entry  # noqa: E402

SOURCE = ROOT / "assets" / "source"
CATALOGUE = ROOT / "assets" / "catalogue"
RATE_CARDS = ROOT / "policy" / "rate_cards"
SKILL_REF = ROOT / "skills" / "sap-scope-mapping" / "reference"

PHASES = {
    "Wokshops & Configuration": "workshops_configuration",   # source header typo kept
    "Unit Testing": "unit_testing",
    "Integration Testing": "integration_testing",
    "Documentation, Training core User": "documentation_training",
    "User Acceptance Testing": "user_acceptance_testing",
}


def _s(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def build_catalogue() -> tuple[pd.DataFrame, list[str]]:
    df = pd.read_excel(SOURCE / "BP_ID_LIST.xlsx", sheet_name="Scope", header=1)
    df.index = df.index + 3  # Excel row number (header on row 2) - kept for traceability
    countries = [c for c in df.columns[8:] if isinstance(c, str) and len(c) == 2 and c.isupper()]
    df = df[df["Scope Item ID"].map(_s) != ""]
    items = pd.DataFrame({
        "excel_row": df.index.astype(int),
        "lob": df["LOB"].map(_s),
        "business_area": df["Business Area"].map(_s),
        "scope_item_id": df["Scope Item ID"].map(_s),
        "description": df["Description"].map(_s),
        "cluster": df["Cluster"].map(_s),
        "component": df["Component"].map(_s),
        "prerequisites": df["Prerequisites"].map(_s),
        "master_data": df["Required Master Data (See Master Data Scripts)"].map(_s),
    })
    avail = df[["Scope Item ID", *countries]].melt(id_vars="Scope Item ID", var_name="country", value_name="flag")
    avail = pd.DataFrame({
        "scope_item_id": avail["Scope Item ID"].map(_s),
        "country": avail["country"],
        "available": avail["flag"].map(lambda v: _s(v).upper() == "YES"),
    })
    CATALOGUE.mkdir(parents=True, exist_ok=True)
    items.to_parquet(CATALOGUE / "scope_items.parquet", index=False)
    avail.to_parquet(CATALOGUE / "availability.parquet", index=False)
    assert items["scope_item_id"].is_unique, "duplicate scope item ids in BP_ID_LIST"
    print(f"catalogue: {len(items)} scope items, {items['lob'].nunique()} LOBs, "
          f"{items.groupby(['lob', 'business_area']).ngroups} business areas, {len(countries)} countries")
    return items, countries


def build_rate_card() -> pd.DataFrame:
    frames = []
    for sheet in ("SAP BP", "YASH BP"):
        df = pd.read_excel(SOURCE / "BP_Efforts.xlsx", sheet_name=sheet, header=0)
        df = df[df["Scope ID"].map(_s) != ""]
        out = pd.DataFrame({
            "sheet": sheet,
            "lob": df["Line of Business"].map(_s),
            "business_area": df["Business Area"].map(_s),
            "country_key": df["Country/Region Key"].map(lambda v: _s(v).upper()),
            "scope_id": df["Scope ID"].map(_s),
            "description": df["Scope ID Description"].map(_s),
            "complexity": df["Complexity"].map(_s),
            "comments": df["Comments"].map(_s),
        })
        for src, dst in PHASES.items():
            out[dst] = pd.to_numeric(df[src], errors="coerce").fillna(0.0).astype(float)
        # All five phases count (the old agent's EffortRow.compute_total). The 'SAP BP' sheet's
        # own Total formula omits UAT; that cell is deliberately not imported.
        out["has_effort"] = out[list(PHASES.values())].sum(axis=1) > 0
        frames.append(out)
    rc = pd.concat(frames, ignore_index=True)
    RATE_CARDS.mkdir(parents=True, exist_ok=True)
    rc.to_parquet(RATE_CARDS / "bp_efforts.parquet", index=False)
    for sheet, g in rc.groupby("sheet"):
        print(f"rate card '{sheet}': {len(g)} rows, {int(g['has_effort'].sum())} with effort, "
              f"country keys {sorted(g['country_key'].unique())}")
    return rc


def build_cross_mapping() -> list:
    df = pd.read_excel(SOURCE / "SAP Modules cross mapping_BPID_List 3.xlsx", header=0)
    rows, entries = [], []
    for r in df.itertuples(index=False):
        name, kind, value = _s(r[0]), _s(r[1]), _s(r[2]) if len(r) > 2 else ""
        aliases = [a.strip() for a in (_s(r[3]) if len(r) > 3 else "").split(",") if a.strip()]
        if not name:
            continue
        entry = parse_entry(name, kind, value, aliases)
        entries.append(entry)
        rows.append({
            "module_name": entry.module_name, "mapping_type": entry.mapping_type,
            "mapping_value": entry.mapping_value, "aliases": json.dumps(aliases),
            "is_others": entry.is_others, "others_label": entry.others_label,
            "filters": json.dumps([f.__dict__ for f in entry.filters]),
        })
    pd.DataFrame(rows).to_parquet(CATALOGUE / "cross_mapping.parquet", index=False)
    print(f"cross-mapping: {len(rows)} modules ({sum(e.is_others for e in entries)} 'Others')")
    return entries


def write_alias_guide(entries) -> None:
    lines = [
        "# SAP module cross-mapping (generated - edit the source workbook, then rerun scripts/build_assets.py)",
        "",
        "How a client's module name resolves before any catalogue search. `cross_map_lookup` applies these rows",
        "exactly; this guide is for reasoning about names the lookup does not match verbatim.",
        "",
        "* **Catalogue target** - search only inside these LOB / Business Area filters.",
        "* **Others** - an SAP tool or system with no Best Practice scope items: it goes to `non_catalogue`,",
        "  never to `scope_items`. The label says what kind of tool it is.",
        "",
        "| Module | Aliases | Resolves to |",
        "|---|---|---|",
    ]
    for e in entries:
        aliases = ", ".join(e.aliases) or "-"
        lines.append(f"| {e.module_name} | {aliases} | {e.target_text()} |")
    SKILL_REF.mkdir(parents=True, exist_ok=True)
    (SKILL_REF / "cross-mapping-aliases.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_catalogue_structure(items: pd.DataFrame, countries: list[str]) -> None:
    lines = [
        "# Catalogue structure (generated from BP_ID_LIST - do not edit by hand)",
        "",
        f"{len(items)} scope items in {items['lob'].nunique()} LOBs. Country columns available: {', '.join(countries)}.",
        "Use `catalogue_search` for the actual scope items; this map shows where things live.",
        "",
    ]
    for lob, g in items.groupby("lob", sort=True):
        lines.append(f"## {lob} ({len(g)} items)")
        for ba, gb in g.groupby("business_area", sort=True):
            examples = "; ".join(gb["description"].head(4).tolist())
            lines.append(f"- **{ba}** ({len(gb)}): {examples}")
        lines.append("")
    (SKILL_REF / "catalogue-structure.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    items, countries = build_catalogue()
    build_rate_card()
    entries = build_cross_mapping()
    write_alias_guide(entries)
    write_catalogue_structure(items, countries)
    print("done")
