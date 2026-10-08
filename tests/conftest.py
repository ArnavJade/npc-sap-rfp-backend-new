"""Shared fixtures: a tiny RFP workspace and a ledger with a profile, for rule tests."""

from __future__ import annotations

import pytest

from bidcore.catalogue.store import get_catalogue
from bidcore.evidence import CorpusIndex
from bidcore.ledger.models import new_ledger
from bidcore.ledger.sections_effort import CountryScope, RfpProfile
from bidcore.ledger.validate import ValidationContext
from bidcore.policy import get_policy

RFP_TEXT = """<!-- page: 1 -->
# Request for Proposal - SAP S/4HANA
The client requires SAP S/4HANA Finance, including cash and liquidity management, for Saudi Arabia.
Wave 1: 44 weeks including 12 weeks Hypercare.
<!-- page: 2 -->
| System | Purpose |
|---|---|
| Kronos | Time and attendance |
| SAP Solution Manager | ALM |
Role design and authorizations for S/4HANA and Fiori are in scope.
Data migration of material master and vendor master is in scope.
"""


@pytest.fixture
def rfp_dir(tmp_path):
    d = tmp_path / "rfp"
    d.mkdir()
    (d / "main.md").write_text(RFP_TEXT, encoding="utf-8")
    (d / "index.md").write_text("# index\n", encoding="utf-8")
    return d


@pytest.fixture
def ledger():
    led = new_ledger("t1", "Client")
    led.rfp_profile.data = RfpProfile(countries=[CountryScope(code="SA", name="Saudi Arabia")])
    led.rfp_profile.state = "written"
    return led


@pytest.fixture
def vctx(ledger, rfp_dir):
    return ValidationContext(get_policy(), get_catalogue(), CorpusIndex.from_dir(rfp_dir), ledger)


def ev(quote: str, page: str = "1") -> dict:
    return {"quote": quote, "file": "rfp/main.md", "page": page}
