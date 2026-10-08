"""Deterministic catalogue mapping (old Layer 2/3 parity) and the lenient tool arguments."""

from __future__ import annotations

from bidcore.ledger.models import new_ledger
from bidcore.ledger.sections_effort import BasisActivity, CountryScope, RfpProfile, ScopeItem
from harness.context import RunContext
from harness.tools.catalogue_tools import ensure_finance_core, make_catalogue_tools, make_mapping_tools
from harness.tools.ledger_tools import write_rows
from harness.workspace import BidWorkspace


def _run(tmp_path) -> RunContext:
    ws = BidWorkspace.open("map1", base=tmp_path / "ws")
    led = new_ledger("map1", "ACME")
    led.rfp_profile.data = RfpProfile(countries=[CountryScope(code="SA")])
    ws.ledger.save(led)
    return RunContext(ws=ws, team="effort")


def test_map_scope_area_writes_the_whole_rulebook_selection(tmp_path):
    run = _run(tmp_path)
    [tool] = make_mapping_tools(run, "catalogue-mapper")
    out = tool.invoke({"capability_refs": ["cap-1"], "module_name": "Sales & Distribution (SD)", "countries": ["SA"]})
    rows = run.ledger.load().scope_items.rows
    assert "added" in out and len(rows) > 20 and {r.lob for r in rows} == {"Sales"}
    assert all(r.countries == ["SA"] and r.mapping_basis == "cross_map" and r.capability_refs == ["cap-1"] for r in rows)
    again = tool.invoke({"capability_refs": ["cap-2"], "lob": "Sales", "business_area": rows[0].business_area})
    assert "added 0" in again and run.ledger.load().scope_items.rows[0].capability_refs == ["cap-1", "cap-2"]
    assert "non_catalogue" in tool.invoke({"capability_refs": ["cap-3"], "module_name": "SAP Signavio"})


def test_finance_core_is_completed_deterministically(tmp_path):
    run = _run(tmp_path)
    run.ledger.update(lambda led: led.scope_items.rows.append(
        ScopeItem(row_id="si-1", scope_item_id="J78", lob="Finance", business_area="Treasury Management",
                  countries=["SA"], capability_refs=["cap-1"])), actor="t", action="seed")
    added = ensure_finance_core(run)
    rows = run.ledger.load().scope_items.rows
    assert added and {r.business_area for r in rows if r.mapping_basis == "finance_core"} <= \
        set(run.policy.catalogue.finance_core_business_areas)
    assert "Financial Operations" in {r.business_area for r in rows}
    assert ensure_finance_core(run) == []                       # idempotent


def test_catalogue_search_caps_instead_of_rejecting(tmp_path):
    run = _run(tmp_path)
    search = next(t for t in make_catalogue_tools(run) if t.name == "catalogue_search")
    out = search.invoke({"lob": "Sales", "business_area": "Order and Contract Management", "limit": 500})
    assert "Error" not in out and len(out.splitlines()) > 40


def test_empty_append_on_a_written_section_is_a_no_op(tmp_path):
    run = _run(tmp_path)
    run.ledger.update(lambda led: led.basis.rows.append(BasisActivity(row_id="bas-1", activity="Landscape set-up")),
                      actor="t", action="seed")
    out = write_rows(run, "scope-basis", "basis", [], "append", "nothing more")
    assert out.startswith("Nothing changed") and len(run.ledger.load().basis.rows) == 1
