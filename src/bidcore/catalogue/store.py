"""SAP Best Practice catalogue (BP_ID_LIST) as an in-memory SQLite database.

Built from the parquet assets produced by `scripts/build_assets.py`:
  assets/catalogue/scope_items.parquet       one row per scope item (excel_row kept for traceability)
  assets/catalogue/availability.parquet      long format: scope_item_id x country -> available
  assets/catalogue/cross_mapping.parquet     the module cross-mapping rulebook

Agents query it through deterministic tools (catalogue_search, check_country_availability)
instead of reading a 445 x 43 matrix in a prompt.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from bidcore.catalogue.crossmap import CrossMap, CrossMapEntry, LobBaFilter, parse_entry
from bidcore.paths import catalogue_dir

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


class Catalogue:
    def __init__(self, directory: Path | None = None):
        directory = directory or catalogue_dir()
        items = pd.read_parquet(directory / "scope_items.parquet")
        avail = pd.read_parquet(directory / "availability.parquet")
        cross = pd.read_parquet(directory / "cross_mapping.parquet")

        self._lock = threading.Lock()
        self._db = sqlite3.connect(":memory:", check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        items.to_sql("scope_items", self._db, index=False)
        avail.to_sql("availability", self._db, index=False)
        self._db.executescript(
            """
            CREATE INDEX ix_items_id ON scope_items(scope_item_id);
            CREATE INDEX ix_avail ON availability(scope_item_id, country);
            CREATE VIRTUAL TABLE items_fts USING fts5(
                scope_item_id UNINDEXED, lob, business_area, description, component,
                tokenize='porter unicode61'
            );
            INSERT INTO items_fts SELECT scope_item_id, lob, business_area, description, component FROM scope_items;
            """
        )
        self.countries: list[str] = sorted(avail["country"].unique().tolist())
        self.crossmap = CrossMap([
            parse_entry(r.module_name, r.mapping_type, r.mapping_value, json.loads(r.aliases))
            for r in cross.itertuples()
        ])

    # ------------------------------------------------------------------ queries
    def _rows(self, sql: str, params: Iterable[Any] = ()) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self._db.execute(sql, tuple(params)).fetchall()]

    def lobs(self) -> list[str]:
        return [r["lob"] for r in self._rows("SELECT DISTINCT lob FROM scope_items ORDER BY lob")]

    def business_areas(self, lob: str | None = None) -> list[dict]:
        sql = "SELECT lob, business_area, COUNT(*) AS items FROM scope_items"
        params: list[Any] = []
        if lob:
            sql += " WHERE lower(lob) = lower(?)"
            params.append(lob)
        return self._rows(sql + " GROUP BY lob, business_area ORDER BY lob, business_area", params)

    def get(self, scope_item_ids: Iterable[str]) -> dict[str, dict]:
        ids = [str(i).strip() for i in scope_item_ids if str(i).strip()]
        if not ids:
            return {}
        marks = ",".join("?" * len(ids))
        rows = self._rows(f"SELECT * FROM scope_items WHERE scope_item_id IN ({marks})", ids)
        return {r["scope_item_id"]: r for r in rows}

    def availability(self, scope_item_ids: Iterable[str], countries: Iterable[str]) -> dict[str, dict[str, bool]]:
        ids = [str(i).strip() for i in scope_item_ids if str(i).strip()]
        codes = [str(c).strip().upper() for c in countries if str(c).strip()]
        out: dict[str, dict[str, bool]] = {i: {} for i in ids}
        if not ids or not codes:
            return out
        rows = self._rows(
            f"SELECT scope_item_id, country, available FROM availability "
            f"WHERE scope_item_id IN ({','.join('?' * len(ids))}) AND country IN ({','.join('?' * len(codes))})",
            ids + codes,
        )
        for r in rows:
            out[r["scope_item_id"]][r["country"]] = bool(r["available"])
        return out

    def search(
        self,
        query: str = "",
        lob: str | None = None,
        business_area: str | None = None,
        countries: Iterable[str] | None = None,
        limit: int = 15,
    ) -> list[dict]:
        """Full-text search (bm25) over LOB, BA, description and component, optionally filtered
        by LOB / Business Area; each hit carries its availability in `countries`."""
        tokens = [t.lower() for t in _TOKEN_RE.findall(query or "")]
        where, params = [], []
        if lob:
            where.append("lower(s.lob) = lower(?)")
            params.append(lob)
        if business_area:
            where.append("lower(s.business_area) = lower(?)")
            params.append(business_area)
        if tokens:
            match = " OR ".join(f'"{t}"*' for t in tokens)
            sql = (
                "SELECT s.*, bm25(items_fts) AS score FROM items_fts JOIN scope_items s "
                "ON s.scope_item_id = items_fts.scope_item_id WHERE items_fts MATCH ?"
            )
            params.insert(0, match)
            sql += "".join(f" AND {w}" for w in where) + " ORDER BY score LIMIT ?"
        else:
            sql = "SELECT s.* FROM scope_items s" + (" WHERE " + " AND ".join(where) if where else "")
            sql += " ORDER BY s.lob, s.business_area, s.scope_item_id LIMIT ?"
        params.append(int(limit))
        hits = self._rows(sql, params)
        return self._with_availability(hits, countries)

    def expand(self, f: LobBaFilter, countries: Iterable[str] | None = None) -> list[dict]:
        """Every scope item a cross-mapping filter selects."""
        where, params = [], []
        if f.lob:
            where.append("lower(lob) = lower(?)")
            params.append(f.lob)
        if f.business_area:
            where.append("lower(business_area) = lower(?)")
            params.append(f.business_area)
        if f.description_filter:
            where.append("lower(description) LIKE ?")
            params.append(f"%{f.description_filter.lower()}%")
        if f.component_filter:
            where.append("lower(component) LIKE ?")
            params.append(f"%{f.component_filter.lower()}%")
        sql = "SELECT * FROM scope_items" + (" WHERE " + " AND ".join(where) if where else "")
        return self._with_availability(self._rows(sql + " ORDER BY excel_row", params), countries)

    def resolve_module(self, name: str) -> CrossMapEntry | None:
        return self.crossmap.resolve(name)

    def _with_availability(self, hits: list[dict], countries: Iterable[str] | None) -> list[dict]:
        codes = [c.strip().upper() for c in (countries or []) if c and c.strip()]
        if not codes or not hits:
            return hits
        avail = self.availability([h["scope_item_id"] for h in hits], codes)
        for h in hits:
            flags = avail.get(h["scope_item_id"], {})
            h["availability"] = {c: flags.get(c, False) for c in codes}
            h["available_in"] = [c for c in codes if flags.get(c)]
        return hits


@lru_cache(maxsize=1)
def get_catalogue() -> Catalogue:
    return Catalogue()
