"""Fixtures for the effort engine: a tiny rate card written to a temp parquet (no repo data needed)."""

from __future__ import annotations

import pandas as pd
import pytest

from bidcore.effort.rate_card import RateCard

PHASES = ("workshops_configuration", "unit_testing", "integration_testing", "documentation_training",
          "user_acceptance_testing")


def _row(scope_id: str, country: str, efforts: tuple[float, ...], sheet: str = "SAP BP", lob: str = "Finance",
         area: str = "General Ledger", description: str = "", comments: str = "") -> dict:
    return {"sheet": sheet, "lob": lob, "business_area": area, "country_key": country, "scope_id": scope_id,
            "description": description or f"{scope_id} description", "complexity": "Best Practice",
            "comments": comments, **dict(zip(PHASES, efforts)), "has_effort": sum(efforts) > 0}


RATE_ROWS = [
    _row("A1", "DE", (10, 1, 1, 1, 1)),                      # exact DE row (total 14) ...
    _row("A1", "", (5, 1, 1, 1, 2)),                         # ... and a global row (total 10)
    _row("B2", "US", (4, 2, 2, 1, 1), comments="US only"),   # only another country's row (total 10)
    _row("B2", "GB", (8, 0, 0, 0, 0)),
    _row("C3", "", (2, 2, 2, 2, 2), lob="Sales", area="Order to Cash"),
    _row("D4", "DE", (1, 1, 1, 1, 1)),
    _row("D4", "DE", (3, 3, 3, 3, 3)),                       # repeated key: the last row wins
    _row("Z0", "", (0, 0, 0, 0, 0), comments="priced at zero"),
    _row("A1", "", (99, 0, 0, 0, 0), sheet="YASH BP"),
]


@pytest.fixture
def rate_card_path(tmp_path):
    path = tmp_path / "bp_efforts.parquet"
    pd.DataFrame(RATE_ROWS).to_parquet(path, index=False)
    return path


@pytest.fixture
def card(rate_card_path) -> RateCard:
    return RateCard("SAP BP", rate_card_path)
