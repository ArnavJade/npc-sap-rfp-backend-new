"""Specialist workstream sheets (Data Migration, Basis, Security, Analytics): row tables, totals, snapping.

Ported from data_migration_scope.py / basis_scope.py / security_scope.py / analytics_scope.py (the
deterministic parts; extraction, merging and grounding are now the agents' + ledger_write's job).
Totals mirror each old total_effort(), which is what that sheet's Total cell evaluates to:
  * Data Migration - every object's six phase cells, summed over every wave table (one table per
    delivery wave). Status is not consulted: the old sheet wrote every object In Scope and its row
    formula (=SUM(C:H), policy/workbook.yaml) ignores the status column;
  * Basis - every DEV / QA / PRD cell; Out of Scope rows carry none;
  * Security - In Scope rows' man-days only (=IF(status="In Scope", effort, 0));
  * Analytics - per object: count x reference rate[type][metric][complexity] x the Standard factor for
    Standard content; 0 unless In Scope. An excluded workstream forces every row Out of Scope.
The snap helpers are the old sanitisers' coercions, kept for the ledger validators to reuse.
"""

from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping
from typing import Any

from bidcore.effort.models import WorkstreamTables
from bidcore.ledger.sections_effort import (
    AnalyticsObject, AnalyticsScope, BasisActivity, DataMigrationObject, SecurityActivity,
)
from bidcore.policy import Policy, get_policy

IN_SCOPE, OUT_OF_SCOPE = "In Scope", "Out of Scope"
BASIS_KEYS = ("dev", "qa", "prd")
ANALYTICS_METRICS = {"Devlp": "devlp", "Unit Testing": "unit_testing", "QA Testing": "qa_testing"}
EXCLUDED_ANALYTICS_ROW_ID = "analytics:entire-scope"


# ------------------------------------------------------------------ snapping (validators reuse these)
def _number(value: Any) -> float | None:
    try:
        number = float(value) if isinstance(value, (int, float)) else float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return None if number != number else number          # NaN -> None


def dm_snap_effort(value: Any, default: float | None = None, policy: Policy | None = None) -> float | None:
    """Nearest allowed Data Migration value (ties round UP: 1.5 -> 2.0); non-numeric / negative -> default."""
    allowed = (policy or get_policy()).workstreams["data_migration"]["allowed_effort_days"]
    number = _number(value)
    if number is None or number < 0:
        return default
    return float(min(allowed, key=lambda a: (abs(a - number), -a)))


def _whole_days(value: Any, bounds: Iterable[float], default: int | None) -> int | None:
    number = _number(value)
    if number is None:
        return default
    low, high = bounds
    return int(min(high, max(low, round(number))))


def basis_snap(value: Any, default: int | None = None, policy: Policy | None = None) -> int | None:
    """Whole man-days in the Basis range (1..5); non-numeric -> default."""
    return _whole_days(value, (policy or get_policy()).workstreams["basis"]["effort_range"], default)


def security_snap(value: Any, default: int | None = None, policy: Policy | None = None) -> int | None:
    """Whole man-days in the Security range (1..120); non-numeric -> default."""
    return _whole_days(value, (policy or get_policy()).workstreams["security"]["effort_range"], default)


# ------------------------------------------------------------------ analytics maths
def _get(row: Mapping[str, Any] | Any, key: str, default: Any = None) -> Any:
    return row.get(key, default) if isinstance(row, Mapping) else getattr(row, key, default)


def analytics_object_effort(row: Mapping[str, Any] | AnalyticsObject, policy: Policy | None = None) -> dict[str, float]:
    """Person-days of one analytics row at the reference rates: devlp, unit_testing, qa_testing, total."""
    cfg = (policy or get_policy()).workstreams["analytics"]
    out = {key: 0.0 for key in ANALYTICS_METRICS.values()}
    if _get(row, "status") == IN_SCOPE:
        rates = cfg["reference_rates"]
        table = rates.get(_get(row, "object_type")) or rates["Report"]
        levels = list(cfg.get("complexities") or ["Low", "Medium", "High"])
        complexity = _get(row, "complexity")
        level = levels.index(complexity) if complexity in levels else 1
        factor = float(cfg["standard_factor"]) if _get(row, "build") == "Standard" else 1.0
        count = float(_get(row, "no_of_objects") or 0)
        for metric, key in ANALYTICS_METRICS.items():
            out[key] = count * float(table[metric][level]) * factor
    out["total"] = sum(out[key] for key in ANALYTICS_METRICS.values())
    return out


# ------------------------------------------------------------------ tables
def _dm_row(row: DataMigrationObject, keys: Iterable[str]) -> dict[str, Any]:
    # Old object_label: the RFP area prefixes the object (the same object recurs across areas) and MDG
    # rows carry their data domain.
    category = row.category.strip()
    parts = [row.module.strip()] if row.module.strip() else []
    if category and category.replace(" ", "").lower() != "masterdata":
        parts.append(category)
    parts.append(row.object.strip())
    label = " - ".join(parts)
    return {"row_id": row.row_id, "object": row.object.strip(), "label": label, "status": row.status,
            "sap_module": row.sap_module.strip(), "category": category, "mm_compulsory": row.mm_compulsory,
            **{key: float(getattr(row, key)) for key in keys}}


def build_workstream_tables(
    data_migration: Iterable[DataMigrationObject],
    basis: Iterable[BasisActivity],
    security: Iterable[SecurityActivity],
    analytics: Iterable[AnalyticsObject],
    analytics_scope: AnalyticsScope | None,
    wave_count: int,
    policy: Policy | None = None,
) -> WorkstreamTables:
    """Row tables of the four specialist sheets (shapes per the WorkstreamTables docstring)."""
    p = policy or get_policy()
    ws = p.workstreams
    dm_keys = list(ws["data_migration"]["effort_keys"])
    dm_rows = [_dm_row(row, dm_keys) for row in data_migration]
    # One table per delivery wave, each its own copy so scope sync can resize one wave independently.
    tables = [copy.deepcopy(dm_rows) for _ in range(max(int(wave_count or 0), 1))]

    basis_rows = [{"row_id": r.row_id, "activity": r.activity.strip(), "status": r.status,
                   **{k: (getattr(r, k) if r.status == IN_SCOPE else None) for k in BASIS_KEYS}}
                  for r in basis]
    security_rows = [{"row_id": r.row_id, "activity": r.activity.strip(), "sap_product": r.sap_product.strip(),
                      "status": r.status, "complexity": r.complexity,
                      "effort_days": r.effort_days if r.status == IN_SCOPE else None}
                     for r in security]

    excluded = bool(analytics_scope and analytics_scope.excluded)
    analytics_rows: list[dict[str, Any]] = []
    for r in analytics:
        row = {"row_id": r.row_id, "object": r.object.strip(), "object_type": r.object_type,
               "build": r.build, "no_of_objects": r.no_of_objects,
               "status": OUT_OF_SCOPE if excluded else r.status, "complexity": r.complexity}
        analytics_rows.append({**row, **analytics_object_effort(row, p)})
    if excluded and not analytics_rows:
        marker = {"row_id": EXCLUDED_ANALYTICS_ROW_ID, "object": ws["analytics"]["excluded_row_label"],
                  "object_type": "", "build": "", "no_of_objects": 1, "status": OUT_OF_SCOPE, "complexity": ""}
        analytics_rows.append({**marker, **analytics_object_effort(marker, p)})

    return WorkstreamTables(data_migration=tables, basis=basis_rows, security=security_rows,
                            analytics=analytics_rows, analytics_excluded=excluded)


def workstream_totals(tables: WorkstreamTables, policy: Policy | None = None) -> dict[str, float]:
    """What each specialist sheet's Total cell evaluates to (old total_effort functions)."""
    p = policy or get_policy()
    dm = p.workstreams["data_migration"]
    defaults = dm["default_effort_days"]
    data_migration = float(sum(
        _number(row.get(key)) if _number(row.get(key)) is not None else float(defaults[key])
        for table in tables.data_migration for row in table for key in dm["effort_keys"]
    ))
    basis = float(sum(_number(row.get(key)) or 0 for row in tables.basis for key in BASIS_KEYS))
    security = float(sum(_number(row.get("effort_days")) or 0
                         for row in tables.security if row.get("status") == IN_SCOPE))
    analytics = float(sum(analytics_object_effort(row, p)["total"] for row in tables.analytics))
    return {"data_migration": data_migration, "basis": basis, "security": security, "analytics": analytics}
